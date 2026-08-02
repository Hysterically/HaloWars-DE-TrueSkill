"""The per-match TrueSkill 2 factor graph and its EP schedule.

One call to `rate_match` performs the Bayesian skill update for a single match
(§3's "inference code on the match result"), implementing the full TrueSkill 2
generative model:

  skill_i = w_d * base_i + offset_i                     eq (20)  [optional]
  perf_i ~ N(skill_i + squadOffset(squad size), beta^2) eq (7)   [(4) if solo]
  perf_team = sum_i (timePlayed_i / L) * perf_i         eq (5)
  team ordering via draw margin eps                     §2
  count_i ~ max(0, N((w_p perf_i + w_o perfo_i) T_i,
                     v T_i))                            eq (9)
  perfo_i = weighted mean opposing performance          eqs (10)-(11)
  quit_i  = unrelated OR (related AND under_i)          eqs (12)-(13)

Inference is Expectation Propagation on this graph. With only win/loss
observations the graph is a tree and one sweep is exact (identical to classic
TrueSkill / Herbrich et al. 2007); the count and quit observations introduce
extra likelihood factors on the performance variables, so the schedule sweeps
the whole graph until the messages converge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .gaussian import Gaussian, cdf, delta, hazard, pdf, v_draw, v_win, w_draw, w_win
from .match import Match, PlayerResult
from .params import ModeParams

_CONVERGENCE_TOL = 1e-5
_MAX_SWEEPS = 60
_CHAIN_TOL = 1e-4
_CHAIN_MAX_ITERS = 20
#: Play-time (minutes) below which a count observation carries no information
#: (its variance v*T collapses); such observations are skipped.
_MIN_COUNT_MINUTES = 1e-6


class Variable(Gaussian):
    """A variable node: current marginal plus the last message from each factor."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: Dict[object, Gaussian] = {}

    def attach(self, factor: object) -> None:
        self.messages[factor] = Gaussian()

    def cavity(self, factor: object) -> Gaussian:
        return self.div(self.messages[factor])

    def set_value(self, val: Gaussian) -> float:
        d = delta(self, val)
        self.pi = val.pi
        self.tau = val.tau
        return d

    def update_message(self, factor: object, msg: Gaussian) -> float:
        old = self.messages[factor]
        self.messages[factor] = msg
        return self.set_value(self.div(old).mul(msg))

    def update_value(self, factor: object, val: Gaussian) -> float:
        old = self.messages[factor]
        self.messages[factor] = val.mul(old).div(self)
        return self.set_value(val)


# -----------------------------------------------------------------------------
# Deterministic factors (exact messages).
# -----------------------------------------------------------------------------

def _sum_update(
    target: Variable, factor: object, vals: Sequence[Variable], coeffs: Sequence[float]
) -> float:
    """Message to `target` for the constraint target = sum_i coeffs_i * vals_i."""
    pi_inv = 0.0
    mu = 0.0
    for v, c in zip(vals, coeffs):
        div = v.cavity(factor)
        mu += c * div.mu
        if pi_inv == math.inf:
            continue
        pi_inv = math.inf if div.pi == 0.0 else pi_inv + (c * c) / div.pi
    if pi_inv == 0.0:
        # Every coefficient is zero — e.g. a team all of whose members played
        # 0 minutes (play_fraction 0, eq (5)). Such a team carries no ordering
        # information, so emit a uniform message instead of dividing by zero.
        return target.update_message(factor, Gaussian())
    pi = 1.0 / pi_inv
    return target.update_message(factor, Gaussian(pi, pi * mu))


def sum_down(sum_var: Variable, factor: object, terms: Sequence[Variable], coeffs: Sequence[float]) -> float:
    return _sum_update(sum_var, factor, terms, coeffs)


def sum_up(
    factor: object,
    sum_var: Variable,
    terms: Sequence[Variable],
    coeffs: Sequence[float],
    index: int,
) -> float:
    """Message to terms[index], rearranging sum = sum_i c_i t_i for that term."""
    c = coeffs[index]
    if c == 0.0:
        # The term doesn't participate (e.g. w_d = 0: "mode d has no
        # correlation with any other mode", §11) — no information flows to it.
        return 0.0
    new_coeffs = [1.0 / c if x == index else -cc / c for x, cc in enumerate(coeffs)]
    vals = list(terms)
    vals[index] = sum_var
    return _sum_update(terms[index], factor, vals, new_coeffs)


def likelihood_down(skill: Variable, perf: Variable, factor: object, beta2: float, offset: float) -> float:
    """perf = skill + offset + N(0, beta^2): message skill -> perf."""
    msg = skill.cavity(factor)
    a = 1.0 / (1.0 + beta2 * msg.pi)
    return perf.update_message(factor, Gaussian(a * msg.pi, a * (msg.tau + offset * msg.pi)))


def likelihood_up(skill: Variable, perf: Variable, factor: object, beta2: float, offset: float) -> float:
    """perf = skill + offset + N(0, beta^2): message perf -> skill."""
    msg = perf.cavity(factor)
    a = 1.0 / (1.0 + beta2 * msg.pi)
    return skill.update_message(factor, Gaussian(a * msg.pi, a * (msg.tau - offset * msg.pi)))


def trunc_update(var: Variable, factor: object, margin: float, drawn: bool) -> float:
    """Win/draw ordering observation on a team-performance difference."""
    div = var.cavity(factor)
    if div.pi <= 0.0:
        # The difference carries no information (e.g. a team all of whose
        # members played 0 minutes gives an infinite-variance performance).
        # An uninformative cavity can't be standardized — leave it untouched.
        return 0.0
    sqrt_pi = math.sqrt(div.pi)
    t = div.tau / sqrt_pi
    m = margin * sqrt_pi
    if drawn:
        v = v_draw(t, m)
        w = w_draw(t, m)
    else:
        v = v_win(t, m)
        w = w_win(t, m)
    denom = 1.0 - w
    if denom < 1e-10:
        # w -> 1 (a near-certain truncation, e.g. an extreme upset deep in the
        # tail): the posterior collapses onto the margin. Keep the update finite
        # instead of dividing by zero.
        denom = 1e-10
    pi = div.pi / denom
    tau = (div.tau + sqrt_pi * v) / denom
    return var.update_value(factor, Gaussian(pi, tau))


# -----------------------------------------------------------------------------
# Moment-matched likelihood factors on a linear combination of variables.
#
# Each observation t(d), with d = sum_k a_k x_k, is handled generically: given
# the Gaussian cavity of d ~ N(m, V), the family supplies the first and second
# derivatives (L1, L2) of log Z(m) = log ∫ N(d; m, V) t(d) dd with respect to
# m. The tilted marginal of each x_k is then
#     mean  m_k + V_k a_k L1,     variance  V_k + V_k^2 a_k^2 L2
# (x_k enters t only through d, so the chain rule gives the per-variable
# derivatives directly). This one mechanism covers the positive count
# observation (exact Gaussian), the zero count (probit truncation) and the
# quit observation (probit mixture).
# -----------------------------------------------------------------------------

DerivFn = Callable[[float, float], Tuple[float, float]]


def gaussian_obs_derivs(y: float, noise_var: float) -> DerivFn:
    """t(d) = N(y; d, noise_var) — a count observed strictly above zero."""

    def derivs(m: float, v: float) -> Tuple[float, float]:
        s = noise_var + v
        return (y - m) / s, -1.0 / s

    return derivs


def probit_nonpositive_derivs(noise_var: float) -> DerivFn:
    """t(d) = P(d + N(0, noise_var) <= 0) — a count observed as exactly zero.

    Under eq (9) a zero count means the underlying Gaussian was truncated:
    N((...), v T_i) fell at or below zero.
    """

    def derivs(m: float, v: float) -> Tuple[float, float]:
        s = math.sqrt(noise_var + v)
        z = -m / s
        r = hazard(z)
        l1 = -r / s
        l2 = -r * (z + r) / (s * s)
        return l1, l2

    return derivs


def quit_derivs(quit: bool, mq: float, vq: float, pu: float, pr: float) -> DerivFn:
    """The quit observation, eqs (12)-(13), on d = perf_i - perfo_i.

        P(quit | d) = p_u + (1 - p_u) p_r Phi((m_q - d) / sqrt(v_q))
    """
    amp = (1.0 - pu) * pr

    def derivs(m: float, v: float) -> Tuple[float, float]:
        s = math.sqrt(vq + v)
        u = (mq - m) / s
        phi_u = pdf(u)
        if quit:
            z = pu + amp * cdf(u)
            zp = -amp * phi_u / s
            zpp = -amp * u * phi_u / (s * s)
        else:
            z = 1.0 - pu - amp * cdf(u)
            zp = amp * phi_u / s
            zpp = amp * u * phi_u / (s * s)
        z = max(z, 1e-300)
        l1 = zp / z
        l2 = zpp / z - l1 * l1
        return l1, l2

    return derivs


class LinearLikelihood:
    """EP factor for an observation t(d) on d = sum_k coeffs_k * vars_k."""

    def __init__(self, variables: Sequence[Variable], coeffs: Sequence[float], derivs: DerivFn) -> None:
        self.vars = list(variables)
        self.coeffs = list(coeffs)
        self.derivs = derivs
        for v in self.vars:
            v.attach(self)

    def update(self) -> float:
        cavities = [v.cavity(self) for v in self.vars]
        # A non-positive cavity precision means another factor currently owns
        # more precision than the marginal — skip this pass; EP will revisit.
        if any(c.pi <= 0.0 for c in cavities):
            return 0.0
        m_d = 0.0
        v_d = 0.0
        for c, a in zip(cavities, self.coeffs):
            m_d += a * c.mu
            v_d += (a * a) * c.var
        l1, l2 = self.derivs(m_d, v_d)
        max_delta = 0.0
        for var, c, a in zip(self.vars, cavities, self.coeffs):
            vk = c.var
            new_mean = c.mu + vk * a * l1
            new_var = vk + vk * vk * a * a * l2
            if new_var <= 1e-12:
                continue  # numerically degenerate — leave this variable alone
            max_delta = max(max_delta, var.update_value(self, Gaussian.from_mu_var(new_mean, new_var)))
        return max_delta


# -----------------------------------------------------------------------------
# The per-match graph.
# -----------------------------------------------------------------------------

@dataclass
class MemberPrior:
    """Pre-match state of one player, in whichever form the model uses.

    Either `skill` (independent per-mode skills, classic §2 layout), or
    `base` + `offset` (mode correlation, §11) — exactly one form must be set.
    """

    skill: Optional[Gaussian] = None
    base: Optional[Gaussian] = None
    offset: Optional[Gaussian] = None

    def __post_init__(self) -> None:
        correlated = self.base is not None and self.offset is not None
        if correlated == (self.skill is not None):
            raise ValueError("provide either skill, or base and offset")

    @property
    def correlated(self) -> bool:
        return self.base is not None


@dataclass
class MemberPosterior:
    """Post-match state of one player, plus the match's evidence messages
    (posterior ÷ prior), which batch inference stores on its chains."""

    skill: Gaussian
    perf: Gaussian
    base: Optional[Gaussian] = None
    offset: Optional[Gaussian] = None
    msg_to_skill: Optional[Gaussian] = None
    msg_to_base: Optional[Gaussian] = None
    msg_to_offset: Optional[Gaussian] = None


def rate_match(
    match: Match,
    priors: Dict[object, MemberPrior],
    params: ModeParams,
) -> Dict[object, MemberPosterior]:
    """Run EP on one match and return each player's posterior.

    `priors` maps player_id -> MemberPrior. The caller is responsible for the
    dynamics (eqs (2)-(3), (8), (15)-(19)) — this function sees the pre-match
    state and produces the during-match posterior, nothing more.
    """
    L = match.length
    beta2 = params.beta * params.beta

    # Sort teams best-first (ascending rank), keeping the original player_ids.
    order = sorted(range(len(match.teams)), key=lambda i: match.teams[i].rank)
    teams = [match.teams[i] for i in order]
    ranks = [t.rank for t in teams]
    T = len(teams)

    flat: List[PlayerResult] = [p for t in teams for p in t.players]
    team_of: Dict[int, int] = {}
    idx = 0
    team_member_idx: List[List[int]] = []
    for ti, t in enumerate(teams):
        idxs = []
        for _ in t.players:
            team_of[idx] = ti
            idxs.append(idx)
            idx += 1
        team_member_idx.append(idxs)

    n = len(flat)
    weights = [p.play_fraction(L) for p in flat]  # timePlayed_i / L, eq (5)

    # ---- variables ----
    skill = [Variable() for _ in range(n)]
    perf = [Variable() for _ in range(n)]
    team_perf = [Variable() for _ in range(T)]
    team_diff = [Variable() for _ in range(T - 1)]
    base: List[Optional[Variable]] = [None] * n
    offset: List[Optional[Variable]] = [None] * n

    # ---- prior factors (and, under mode correlation, eq (20) sum factors) ----
    correlated = priors[flat[0].player_id].correlated
    prior_factors: List[Tuple[object, Variable, Gaussian]] = []
    combine_factors: List[Tuple[object, int]] = []  # skill = w_d*base + offset
    for i, p in enumerate(flat):
        pr = priors[p.player_id]
        if pr.correlated != correlated:
            raise ValueError("all players must use the same prior form")
        if correlated:
            base[i] = Variable()
            offset[i] = Variable()
            for var, g in ((base[i], pr.base), (offset[i], pr.offset)):
                f = object()
                var.attach(f)
                prior_factors.append((f, var, g))
            f = object()
            skill[i].attach(f)
            base[i].attach(f)
            offset[i].attach(f)
            combine_factors.append((f, i))
        else:
            f = object()
            skill[i].attach(f)
            prior_factors.append((f, skill[i], pr.skill))

    # ---- performance likelihoods, eq (7) (squad offset shifts the mean) ----
    like_factors: List[Tuple[object, int, float]] = []
    for i, p in enumerate(flat):
        f = object()
        skill[i].attach(f)
        perf[i].attach(f)
        like_factors.append((f, i, params.squad_offset(p.squad_size)))

    # ---- team performance sums, eq (5) ----
    team_factors: List[Tuple[object, int]] = []
    for ti, idxs in enumerate(team_member_idx):
        f = object()
        team_perf[ti].attach(f)
        for i in idxs:
            perf[i].attach(f)
        team_factors.append((f, ti))

    # ---- ordering chain: diff_k = team_perf_k - team_perf_{k+1} ----
    diff_factors: List[object] = []
    trunc_specs: List[Tuple[object, float, bool]] = []
    for k in range(T - 1):
        f = object()
        team_perf[k].attach(f)
        team_perf[k + 1].attach(f)
        team_diff[k].attach(f)
        diff_factors.append(f)
        tf = object()
        team_diff[k].attach(tf)
        weight_sum = sum(weights[i] for i in team_member_idx[k]) + sum(
            weights[i] for i in team_member_idx[k + 1]
        )
        margin = params.pair_margin(weight_sum)
        drawn = ranks[k] == ranks[k + 1]
        trunc_specs.append((tf, margin, drawn))

    # ---- individual statistics (eq 9) and quit (eqs 12-13) factors ----
    # opposing_i (eq 10) and the perfo_i weights (eq 11) are shared.
    opposing = [0.0] * n
    for i in range(n):
        opposing[i] = sum(weights[j] for j in range(n) if team_of[j] != team_of[i])

    def perfo_terms(i: int) -> Tuple[List[Variable], List[float]]:
        vs: List[Variable] = []
        cs: List[float] = []
        for j in range(n):
            if team_of[j] == team_of[i] or opposing[j] <= 0.0:
                continue
            vs.append(perf[j])
            cs.append(weights[j] / opposing[j])
        return vs, cs

    obs_factors: List[LinearLikelihood] = []
    for i, p in enumerate(flat):
        t_i = weights[i] * L  # timePlayed_i in minutes
        for cm, count in ((params.kill, p.kills), (params.death, p.deaths)):
            if cm is None or count is None or t_i < _MIN_COUNT_MINUTES:
                continue
            opp_vars, opp_coeffs = perfo_terms(i)
            if not opp_vars:
                continue
            variables = [perf[i]] + opp_vars
            coeffs = [cm.weight_perf * t_i] + [cm.weight_opp * t_i * c for c in opp_coeffs]
            noise = cm.variance * t_i
            if count > 0.0:
                derivs = gaussian_obs_derivs(count, noise)
            else:
                derivs = probit_nonpositive_derivs(noise)
            obs_factors.append(LinearLikelihood(variables, coeffs, derivs))
        qm = params.quit
        if qm is not None and p.quit is not None and (p.quit or qm.normalized):
            opp_vars, opp_coeffs = perfo_terms(i)
            if opp_vars:
                variables = [perf[i]] + opp_vars
                coeffs = [1.0] + [-c for c in opp_coeffs]
                obs_factors.append(
                    LinearLikelihood(
                        variables,
                        coeffs,
                        quit_derivs(bool(p.quit), qm.mean, qm.variance, qm.p_unrelated, qm.p_related),
                    )
                )

    # ---- EP schedule ----
    for f, var, g in prior_factors:
        var.update_value(f, g)

    def chain_iterate() -> float:
        """The ordering-chain schedule of Herbrich et al. 2007 (as one pass)."""
        d = 0.0
        if T == 2:
            sum_down(team_diff[0], diff_factors[0], [team_perf[0], team_perf[1]], [1.0, -1.0])
            tf, margin, drawn = trunc_specs[0]
            d = trunc_update(team_diff[0], tf, margin, drawn)
        else:
            for _ in range(_CHAIN_MAX_ITERS):
                dd = 0.0
                for k in range(T - 2):
                    sum_down(team_diff[k], diff_factors[k], [team_perf[k], team_perf[k + 1]], [1.0, -1.0])
                    tf, margin, drawn = trunc_specs[k]
                    dd = max(dd, trunc_update(team_diff[k], tf, margin, drawn))
                    sum_up(diff_factors[k], team_diff[k], [team_perf[k], team_perf[k + 1]], [1.0, -1.0], 1)
                for k in range(T - 2, 0, -1):
                    sum_down(team_diff[k], diff_factors[k], [team_perf[k], team_perf[k + 1]], [1.0, -1.0])
                    tf, margin, drawn = trunc_specs[k]
                    dd = max(dd, trunc_update(team_diff[k], tf, margin, drawn))
                    sum_up(diff_factors[k], team_diff[k], [team_perf[k], team_perf[k + 1]], [1.0, -1.0], 0)
                d = max(d, dd)
                if dd <= _CHAIN_TOL:
                    break
        # Push the chain's information out to the end team-perf variables.
        sum_up(diff_factors[0], team_diff[0], [team_perf[0], team_perf[1]], [1.0, -1.0], 0)
        sum_up(
            diff_factors[T - 2],
            team_diff[T - 2],
            [team_perf[T - 2], team_perf[T - 1]],
            [1.0, -1.0],
            1,
        )
        return d

    for sweep in range(_MAX_SWEEPS):
        d = 0.0
        if correlated:
            for f, i in combine_factors:
                d = max(d, sum_down(skill[i], f, [base[i], offset[i]], [params.mode_weight, 1.0]))
        for f, i, sq_off in like_factors:
            d = max(d, likelihood_down(skill[i], perf[i], f, beta2, sq_off))
        for fac in obs_factors:
            d = max(d, fac.update())
        for f, ti in team_factors:
            idxs = team_member_idx[ti]
            d = max(d, sum_down(team_perf[ti], f, [perf[i] for i in idxs], [weights[i] for i in idxs]))
        d = max(d, chain_iterate())
        for f, ti in team_factors:
            idxs = team_member_idx[ti]
            members = [perf[i] for i in idxs]
            coeffs = [weights[i] for i in idxs]
            for m in range(len(idxs)):
                d = max(d, sum_up(f, team_perf[ti], members, coeffs, m))
        for f, i, sq_off in like_factors:
            d = max(d, likelihood_up(skill[i], perf[i], f, beta2, sq_off))
        if correlated:
            for f, i in combine_factors:
                d = max(d, sum_up(f, skill[i], [base[i], offset[i]], [params.mode_weight, 1.0], 0))
                d = max(d, sum_up(f, skill[i], [base[i], offset[i]], [params.mode_weight, 1.0], 1))
        if d <= _CONVERGENCE_TOL and sweep >= 1:
            break

    # ---- read out ----
    out: Dict[object, MemberPosterior] = {}
    prior_of: Dict[int, Gaussian] = {}
    base_prior_of: Dict[int, Gaussian] = {}
    offset_prior_of: Dict[int, Gaussian] = {}
    pf_iter = iter(prior_factors)
    for i, p in enumerate(flat):
        if correlated:
            _, _, gb = next(pf_iter)
            _, _, go = next(pf_iter)
            base_prior_of[i] = gb
            offset_prior_of[i] = go
        else:
            _, _, g = next(pf_iter)
            prior_of[i] = g
    for i, p in enumerate(flat):
        if correlated:
            out[p.player_id] = MemberPosterior(
                skill=Gaussian(skill[i].pi, skill[i].tau),
                perf=Gaussian(perf[i].pi, perf[i].tau),
                base=Gaussian(base[i].pi, base[i].tau),
                offset=Gaussian(offset[i].pi, offset[i].tau),
                msg_to_base=Gaussian(base[i].pi, base[i].tau).div(base_prior_of[i]),
                msg_to_offset=Gaussian(offset[i].pi, offset[i].tau).div(offset_prior_of[i]),
            )
        else:
            out[p.player_id] = MemberPosterior(
                skill=Gaussian(skill[i].pi, skill[i].tau),
                perf=Gaussian(perf[i].pi, perf[i].tau),
                msg_to_skill=Gaussian(skill[i].pi, skill[i].tau).div(prior_of[i]),
            )
    return out


__all__ = [
    "Variable",
    "MemberPrior",
    "MemberPosterior",
    "rate_match",
    "LinearLikelihood",
    "gaussian_obs_derivs",
    "probit_nonpositive_derivs",
    "quit_derivs",
]
