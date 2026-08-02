"""Batch inference — "TrueSkill Through Time" (§3).

Where the online mode only propagates information forward, batch mode gives
each player a skill variable *per match played* (exactly as the paper: "Each
player had a skill variable skill_i^t for every match they played") connected
in a chain by the dynamics factors:

    x_{k+1} ~ N(x_k + experienceOffset(k), gamma^2 + tau^2 * gap_k)

(eqs (2)/(3)/(8); eqs (15)/(16)/(18)/(19) for the base/offset chains under
mode correlation). EP messages flow both forward and backward through the
chains, and the whole graph is swept repeatedly until convergence, so early
matches inform late skills AND late matches inform early skills.

The implementation is plain EP smoothing: each match stores its evidence
message to every chain node it touches; between sweeps each chain re-runs
forward-backward over (prior, dynamics, stored messages) to produce the next
sweep's cavities.

Two `Params` shims shared with the online engine are honoured here too, so a
batch ladder is comparable to the online one under the same config:
`drift_pre_match` inflates the FIRST node's prior by gamma^2 (the only place the
pre- vs post-match drift convention differs once a chain is smoothed — every
interior edge already carries gamma^2 + tau^2*gap regardless), and `sigma_min`
floors the reported posterior sigma at read-out (an operational display floor,
applied after smoothing so it never perturbs convergence). Both default off, so
the paper-faithful configuration (`paper_params`) is unaffected.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Hashable, List, Optional, Sequence, Tuple

from .factorgraph import MemberPrior, rate_match
from .gaussian import Gaussian, delta
from .match import Match
from .params import Params

_DEFAULT_SWEEPS = 10
_BATCH_TOL = 1e-4
#: EP message damping for the batch smoother — OPT-IN (default off). With
#: performance-anchoring observations (kill/death counts) the smoother is stable
#: and converges exactly, so damping is off by default to preserve that
#: exactness. For win/loss-only batches on near-separable data the ordering-chain
#: messages can otherwise grow across sweeps toward extreme skills; pass e.g.
#: damping=0.5 (and more `sweeps`) to blend each new evidence message with the
#: previous one, stabilizing the iteration onto the SAME fixed point (damping
#: changes only the path, not the solution).
_DEFAULT_DAMPING = 0.0


def _shift(g: Gaussian, mean_shift: float, add_var: float) -> Gaussian:
    """Propagate a (proper) Gaussian through x' = x + mean_shift + N(0, add_var)."""
    if g.pi == 0.0:
        return Gaussian()
    return Gaussian.from_mu_var(g.mu + mean_shift, g.var + add_var)


def _damp(old: Gaussian, new: Gaussian, damping: float) -> Gaussian:
    """Blend a new evidence message with the previous one (natural params)."""
    if damping <= 0.0:
        return new
    return Gaussian(
        damping * old.pi + (1.0 - damping) * new.pi,
        damping * old.tau + (1.0 - damping) * new.tau,
    )


@dataclass
class _Chain:
    """One player's skill (or base/offset) chain across their matches."""

    prior: Gaussian
    #: Per node: mean shift delta_k and added variance q_k on the k -> k+1 edge.
    deltas: List[float] = field(default_factory=list)
    qs: List[float] = field(default_factory=list)
    #: Evidence message from each node's match (starts uniform).
    likes: List[Gaussian] = field(default_factory=list)
    forward: List[Gaussian] = field(default_factory=list)
    backward: List[Gaussian] = field(default_factory=list)

    def add_node(self, mean_shift_after: float, var_after: float) -> int:
        self.deltas.append(mean_shift_after)
        self.qs.append(var_after)
        self.likes.append(Gaussian())
        return len(self.likes) - 1

    def smooth(self) -> None:
        n = len(self.likes)
        self.forward = [Gaussian() for _ in range(n)]
        self.backward = [Gaussian() for _ in range(n)]
        self.forward[0] = self.prior
        for k in range(n - 1):
            self.forward[k + 1] = _shift(self.forward[k].mul(self.likes[k]), self.deltas[k], self.qs[k])
        for k in range(n - 2, -1, -1):
            self.backward[k] = _shift(
                self.backward[k + 1].mul(self.likes[k + 1]), -self.deltas[k], self.qs[k]
            )

    def cavity(self, k: int) -> Gaussian:
        """The chain's belief about node k, excluding node k's own match."""
        return self.forward[k].mul(self.backward[k])

    def posterior(self, k: int) -> Gaussian:
        return self.cavity(k).mul(self.likes[k])


@dataclass
class BatchResult:
    """Posteriors from a batch run."""

    #: (player, mode) -> chronological [(match_index, skill posterior Gaussian)].
    trajectories: Dict[Tuple[Hashable, str], List[Tuple[int, Gaussian]]]
    #: (player, mode) -> skill posterior at the player's last match in the mode.
    final: Dict[Tuple[Hashable, str], Gaussian]
    sweeps_run: int
    converged: bool


def batch_rate(
    matches: Sequence[Match],
    params: Optional[Params] = None,
    sweeps: int = _DEFAULT_SWEEPS,
    tol: float = _BATCH_TOL,
    damping: float = _DEFAULT_DAMPING,
) -> BatchResult:
    """Run TrueSkill Through Time over `matches` (must be in start-time order)."""
    params = params or Params()
    matches = list(matches)
    for a, b in zip(matches, matches[1:]):
        if b.start_time < a.start_time:
            raise ValueError("matches must be sorted by start time")

    correlated = params.mode_correlation

    # ---- build the chains ----
    # Independent form: chains[(player, mode)]; node per appearance.
    # Correlated form: base_chains[player] over ALL matches, offset chains per mode.
    skill_chains: Dict[Tuple[Hashable, str], _Chain] = {}
    base_chains: Dict[Hashable, _Chain] = {}
    # For each match: player -> (chain keys and node indices).
    node_of: List[Dict[Hashable, Tuple[int, int]]] = []  # (skill/offset node, base node)

    last_end: Dict[Tuple[Hashable, object], float] = {}  # per chain key: last match end

    for mi, match in enumerate(matches):
        mp = params.mode(match.mode)
        assignment: Dict[Hashable, Tuple[int, int]] = {}
        for p in match.all_players():
            pid = p.player_id
            gap_key = (pid, match.mode)
            # §12: constant-skill players (bots) get frozen dynamics — every
            # chain edge carries gamma=tau=0 (no drift) and no experience offset,
            # so all their nodes share one constant skill inferred from all data.
            const = params.is_constant(pid)
            m_gamma = 0.0 if const else mp.gamma
            m_tau = 0.0 if const else mp.tau
            b_gamma = 0.0 if const else params.base.gamma
            b_tau = 0.0 if const else params.base.tau
            # drift_pre_match: the first match is played at v0+gamma^2 (prior
            # inflated BEFORE the match), matching online.py. Interior edges are
            # identical either way, so this first-node bump is the whole effect.
            pre = params.drift_pre_match and not const
            b_pre = b_gamma * b_gamma if pre else 0.0
            o_pre = m_gamma * m_gamma if pre else 0.0
            if correlated:
                bchain = base_chains.get(pid)
                if bchain is None:
                    bchain = _Chain(prior=Gaussian.from_mu_var(0.0, params.base.vb + b_pre))  # eq (14)
                    base_chains[pid] = bchain
                ochain = skill_chains.get(gap_key)
                if ochain is None:
                    ochain = _Chain(prior=Gaussian.from_mu_var(mp.m0, mp.v0 + o_pre))  # eq (17)
                    skill_chains[gap_key] = ochain
                # dynamics on the edge AFTER this node; the between-match gap is
                # filled in when the next appearance is seen.
                exp = len(ochain.likes)  # experience before this match, per mode
                exp_off = 0.0 if const else mp.experience_offset(exp)
                b_gap = _gap(last_end, (pid, "__base__"), match)
                o_gap = _gap(last_end, gap_key, match)
                bnode = bchain.add_node(0.0, b_gamma ** 2 + b_tau ** 2 * b_gap)
                onode = ochain.add_node(exp_off, m_gamma ** 2 + m_tau ** 2 * o_gap)
                _fix_previous_gap(bchain, b_tau, b_gamma, b_gap)
                _fix_previous_gap(ochain, m_tau, m_gamma, o_gap)
                assignment[pid] = (onode, bnode)
            else:
                chain = skill_chains.get(gap_key)
                if chain is None:
                    chain = _Chain(prior=Gaussian.from_mu_var(mp.m0, mp.v0 + o_pre))  # eq (1)
                    skill_chains[gap_key] = chain
                exp = len(chain.likes)
                exp_off = 0.0 if const else mp.experience_offset(exp)
                gap = _gap(last_end, gap_key, match)
                node = chain.add_node(exp_off, m_gamma ** 2 + m_tau ** 2 * gap)
                _fix_previous_gap(chain, m_tau, m_gamma, gap)
                assignment[pid] = (node, -1)
            last_end[(p.player_id, "__base__")] = match.end_time
            last_end[gap_key] = match.end_time
        node_of.append(assignment)

    for chain in skill_chains.values():
        chain.smooth()
    for chain in base_chains.values():
        chain.smooth()

    # ---- sweep ----
    sweeps_run = 0
    converged = False
    for sweep in range(sweeps):
        sweeps_run = sweep + 1
        max_d = 0.0
        for mi, match in enumerate(matches):
            mp = params.mode(match.mode)
            priors: Dict[Hashable, MemberPrior] = {}
            for p in match.all_players():
                pid = p.player_id
                onode, bnode = node_of[mi][pid]
                if correlated:
                    priors[pid] = MemberPrior(
                        base=base_chains[pid].cavity(bnode),
                        offset=skill_chains[(pid, match.mode)].cavity(onode),
                    )
                else:
                    priors[pid] = MemberPrior(skill=skill_chains[(pid, match.mode)].cavity(onode))
            posts = rate_match(match, priors, mp)
            for p in match.all_players():
                pid = p.player_id
                onode, bnode = node_of[mi][pid]
                post = posts[pid]
                if correlated:
                    bchain = base_chains[pid]
                    ochain = skill_chains[(pid, match.mode)]
                    max_d = max(max_d, delta(bchain.likes[bnode], post.msg_to_base))
                    max_d = max(max_d, delta(ochain.likes[onode], post.msg_to_offset))
                    bchain.likes[bnode] = _damp(bchain.likes[bnode], post.msg_to_base, damping)
                    ochain.likes[onode] = _damp(ochain.likes[onode], post.msg_to_offset, damping)
                else:
                    chain = skill_chains[(pid, match.mode)]
                    max_d = max(max_d, delta(chain.likes[onode], post.msg_to_skill))
                    chain.likes[onode] = _damp(chain.likes[onode], post.msg_to_skill, damping)
        for chain in skill_chains.values():
            chain.smooth()
        for chain in base_chains.values():
            chain.smooth()
        if max_d <= tol:
            converged = True
            break

    # ---- read out skill posteriors per appearance ----
    floor = params.sigma_min * params.sigma_min if params.sigma_min > 0.0 else 0.0

    def _readout(g: Gaussian) -> Gaussian:
        # sigma_min is an operational display floor (online.py applies the same),
        # imposed only at read-out so it never perturbs the smoothing fixed point.
        if floor > 0.0 and g.pi > 0.0 and g.var < floor:
            return Gaussian.from_mu_var(g.mu, floor)
        return g

    trajectories: Dict[Tuple[Hashable, str], List[Tuple[int, Gaussian]]] = {}
    final: Dict[Tuple[Hashable, str], Gaussian] = {}
    for mi, match in enumerate(matches):
        mp = params.mode(match.mode)
        for p in match.all_players():
            pid = p.player_id
            onode, bnode = node_of[mi][pid]
            if correlated:
                b = base_chains[pid].posterior(bnode)
                o = skill_chains[(pid, match.mode)].posterior(onode)
                w = mp.mode_weight
                g = Gaussian.from_mu_var(w * b.mu + o.mu, w * w * b.var + o.var)
            else:
                g = skill_chains[(pid, match.mode)].posterior(onode)
            g = _readout(g)
            key = (pid, match.mode)
            trajectories.setdefault(key, []).append((mi, g))
            final[key] = g
    return BatchResult(trajectories=trajectories, final=final, sweeps_run=sweeps_run, converged=converged)


def _gap(last_end: Dict, key, match: Match) -> float:
    """Idle minutes between the previous appearance's end and this match."""
    prev = last_end.get(key)
    if prev is None:
        return 0.0
    return max(0.0, match.start_time - prev)


def _fix_previous_gap(chain: _Chain, tau: float, gamma: float, gap: float) -> None:
    """Stamp the between-match drift onto the edge LEADING INTO the newest node.

    add_node stores dynamics on the edge after each node; when node k+1 is
    created we know the idle gap since node k ended, so re-write edge k's
    variance as gamma^2 (post-match, eq (2)) + tau^2*gap (idle time, eq (3)).
    """
    if len(chain.likes) < 2:
        return
    k = len(chain.likes) - 2
    chain.qs[k] = gamma * gamma + tau * tau * gap


__all__ = ["batch_rate", "BatchResult"]
