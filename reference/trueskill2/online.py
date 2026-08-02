"""Online skill rating — §3's forward-only mode.

Implements the update loop of §3 verbatim:

  1. Initialize player skills to the prior (eq (1); eqs (14)+(17) when mode
     correlation is on).
  2. For each match in order of start time:
     (a) look up current skill distributions,
     (b) inflate variances for time elapsed since each player's last match
         (eq (3); eqs (16)+(19)),
     (c) run the per-match inference (factorgraph.rate_match),
     (d) inflate variances for having played a match, with the
         experience-biased mean shift (eq (8); eqs (15)+(18)),
     (e) store the new distributions.

Under §11 mode correlation the stored state per player is one base-skill
Gaussian plus one offset Gaussian per game mode; a player's skill in mode d is
skill = w_d * base + offset (eq (20)). Otherwise the state is an independent
skill Gaussian per (player, mode).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Hashable, List, Optional, Tuple

from .factorgraph import MemberPrior, rate_match
from .gaussian import Gaussian, cdf
from .match import Match
from .params import ModeParams, Params


@dataclass
class _State:
    """One Gaussian piece of player state, with its own dynamics clock."""

    mean: float
    var: float
    last_time: Optional[float] = None  # end of the last match, minutes

    def decayed(self, tau: float, now: float) -> Tuple[float, float]:
        """Apply eq (3)/(16)/(19): var += tau^2 * (elapsed minutes)."""
        if self.last_time is None or now <= self.last_time or tau == 0.0:
            return self.mean, self.var
        return self.mean, self.var + tau * tau * (now - self.last_time)


@dataclass
class PlayerRating:
    """A player's rating in one mode, as reported to callers."""

    player_id: Hashable
    mu: float
    sigma: float
    games: int

    @property
    def conservative(self) -> float:
        """mu - 3*sigma — a conservative point estimate for ORDERING players.

        The TrueSkill 2 paper takes the Gaussian MEAN as a player's skill
        rating (§3: "the mean of that Gaussian is taken as the player's skill
        rating"); it never uses mu - 3*sigma. This conservative estimate is the
        classic Herbrich et al. 2007 convention, kept here because the repo's
        CSR display ranks by it. Read `mu` for the paper's rating itself.
        """
        return self.mu - 3.0 * self.sigma


@dataclass
class TeamPrediction:
    team_index: int
    win_prob: float


@dataclass
class MatchPrediction:
    """Pre-match forecast, computed from team composition + squads only (§5)."""

    teams: List[TeamPrediction]
    draw_prob: float

    def predicted_winner(self) -> Optional[int]:
        """Index of the team predicted to win, or None for a predicted draw."""
        best = max(self.teams, key=lambda t: t.win_prob)
        if self.draw_prob > best.win_prob:
            return None
        return best.team_index


class OnlineTrueSkill2:
    """The online updater. Feed matches in chronological order via `update`."""

    def __init__(self, params: Optional[Params] = None) -> None:
        self.params = params or Params()
        # Mode-correlated state: player -> base, (player, mode) -> offset.
        self._base: Dict[Hashable, _State] = {}
        self._offset: Dict[Tuple[Hashable, str], _State] = {}
        # Independent state: (player, mode) -> skill.
        self._skill: Dict[Tuple[Hashable, str], _State] = {}
        #: experience_{i,d}: matches played in the mode before now (§7).
        self.experience: Dict[Tuple[Hashable, str], int] = {}

    # -- state access ----------------------------------------------------------

    def _base_state(self, player: Hashable) -> _State:
        st = self._base.get(player)
        if st is None:
            st = _State(0.0, self.params.base.vb)  # eq (14)
            self._base[player] = st
        return st

    def _offset_state(self, player: Hashable, mode: str, mp: ModeParams) -> _State:
        st = self._offset.get((player, mode))
        if st is None:
            st = _State(mp.m0, mp.v0)  # eq (17)
            self._offset[(player, mode)] = st
        return st

    def _skill_state(self, player: Hashable, mode: str, mp: ModeParams) -> _State:
        st = self._skill.get((player, mode))
        if st is None:
            st = _State(mp.m0, mp.v0)  # eq (1)
            self._skill[(player, mode)] = st
        return st

    def skill(self, player: Hashable, mode: str, at_time: Optional[float] = None) -> Gaussian:
        """Current skill belief for a player in a mode (eq (20) if correlated).

        `at_time` applies the between-match drift up to that timestamp
        (minutes); None reads the state as stored.
        """
        mp = self.params.mode(mode)
        # §12 constant-skill players get no between-match (eq 3) drift.
        base_tau = 0.0 if self.params.is_constant(player) else self.params.base.tau
        mode_tau = 0.0 if self.params.is_constant(player) else mp.tau
        if self.params.mode_correlation:
            bs = self._base_state(player)
            os = self._offset_state(player, mode, mp)
            bm, bv = (bs.mean, bs.var) if at_time is None else bs.decayed(base_tau, at_time)
            om, ov = (os.mean, os.var) if at_time is None else os.decayed(mode_tau, at_time)
            w = mp.mode_weight
            return Gaussian.from_mu_var(w * bm + om, w * w * bv + ov)
        st = self._skill_state(player, mode, mp)
        m, v = (st.mean, st.var) if at_time is None else st.decayed(mode_tau, at_time)
        return Gaussian.from_mu_var(m, v)

    def rating(self, player: Hashable, mode: str) -> PlayerRating:
        g = self.skill(player, mode)
        return PlayerRating(
            player_id=player,
            mu=g.mu,
            sigma=g.sigma,
            games=self.experience.get((player, mode), 0),
        )

    def leaderboard(self, mode: str) -> List[PlayerRating]:
        """Ratings of everyone who has played the mode, best first by mu-3sigma."""
        players = {p for (p, m) in (self._offset if self.params.mode_correlation else self._skill) if m == mode}
        rows = [self.rating(p, mode) for p in players]
        rows.sort(key=lambda r: r.conservative, reverse=True)
        return rows

    # -- prediction (§5 protocol: composition + squads only) --------------------

    def predict(self, match: Match) -> MatchPrediction:
        """Pre-match winner forecast using only team composition and squads.

        Exact for two teams. For more teams, each team's win probability is
        approximated by the product of its pairwise beat-probabilities,
        normalized — the standard factorized approximation.
        """
        mp = self.params.mode(match.mode)
        beta2 = mp.beta * mp.beta
        stats = []  # (mean, var, weight_sum) of each team's performance
        for team in match.teams:
            m = 0.0
            v = 0.0
            wsum = 0.0
            for p in team.players:
                g = self.skill(p.player_id, match.mode, at_time=match.start_time)
                m += g.mu + mp.squad_offset(p.squad_size)
                v += g.var + beta2
                wsum += 1.0
            stats.append((m, v, wsum))

        if len(stats) == 2:
            (m1, v1, w1), (m2, v2, w2) = stats
            eps = mp.pair_margin(w1 + w2)
            s = math.sqrt(v1 + v2)
            d = m1 - m2
            # cdf((d-eps)/s) rather than 1-cdf((eps-d)/s): identical
            # analytically, but keeps relative precision when p1 is tiny.
            p1 = cdf((d - eps) / s)
            p2 = cdf((-d - eps) / s)
            draw = max(0.0, cdf((eps - d) / s) - cdf((-eps - d) / s))
            return MatchPrediction(
                teams=[TeamPrediction(0, p1), TeamPrediction(1, p2)], draw_prob=draw
            )

        # scores[a] = P(team a beats every other team by eps) — the factorized
        # probability that a is the SOLE winner. The leftover mass 1 - sum is
        # the probability that no team clearly wins, i.e. a tie for first place:
        # §5's "draw" option, so a match of N teams offers N+1 outcomes.
        scores = []
        for a, (ma, va, wa) in enumerate(stats):
            prod = 1.0
            for b, (mb, vb, wb) in enumerate(stats):
                if a == b:
                    continue
                eps = mp.pair_margin(wa + wb)
                prod *= cdf(((ma - mb) - eps) / math.sqrt(va + vb))
            scores.append(prod)
        total = sum(scores)
        if total > 1.0:
            # The independence approximation overcounted (sole-winner
            # probabilities summed above 1): renormalize, leaving no draw room.
            return MatchPrediction(
                teams=[TeamPrediction(i, s / total) for i, s in enumerate(scores)],
                draw_prob=0.0,
            )
        return MatchPrediction(
            teams=[TeamPrediction(i, s) for i, s in enumerate(scores)],
            draw_prob=1.0 - total,
        )

    # -- the update loop ---------------------------------------------------------

    def update(self, match: Match) -> Dict[Hashable, Gaussian]:
        """Process one match result; returns each player's during-match skill
        posterior (before the post-match drift is applied to stored state)."""
        params = self.params
        mp = params.mode(match.mode)
        gamma2 = mp.gamma * mp.gamma
        base_gamma2 = params.base.gamma * params.base.gamma

        # (b) between-match drift up to the match start, eq (3)/(16)/(19);
        # optionally fold the per-match drift into the prior instead of the
        # posterior (drift_pre_match compatibility mode).
        priors: Dict[Hashable, MemberPrior] = {}
        for p in match.all_players():
            pid = p.player_id
            # §12: a constant-skill player gets no between-match (eq 3) drift and
            # no per-match (eq 2) drift — its clocks and variances are frozen.
            const = params.is_constant(pid)
            base_tau = 0.0 if const else params.base.tau
            mode_tau = 0.0 if const else mp.tau
            g2 = 0.0 if const else gamma2
            bg2 = 0.0 if const else base_gamma2
            if params.mode_correlation:
                bs = self._base_state(pid)
                os = self._offset_state(pid, match.mode, mp)
                bm, bv = bs.decayed(base_tau, match.start_time)
                om, ov = os.decayed(mode_tau, match.start_time)
                if params.drift_pre_match:
                    bv += bg2
                    ov += g2
                priors[pid] = MemberPrior(
                    base=Gaussian.from_mu_var(bm, bv), offset=Gaussian.from_mu_var(om, ov)
                )
            else:
                st = self._skill_state(pid, match.mode, mp)
                m, v = st.decayed(mode_tau, match.start_time)
                if params.drift_pre_match:
                    v += g2
                priors[pid] = MemberPrior(skill=Gaussian.from_mu_var(m, v))

        # (c) the per-match inference.
        posteriors = rate_match(match, priors, mp)

        # (d)+(e) post-match drift with the experience bias, then store.
        out: Dict[Hashable, Gaussian] = {}
        for p in match.all_players():
            pid = p.player_id
            post = posteriors[pid]
            exp_key = (pid, match.mode)
            # §12: constant-skill players get no experience bias (eq 8) and no
            # per-match variance inflation (eq 2/15/18).
            const = params.is_constant(pid)
            exp_offset = 0.0 if const else mp.experience_offset(self.experience.get(exp_key, 0))
            g2 = 0.0 if const else gamma2
            bg2 = 0.0 if const else base_gamma2
            if params.mode_correlation:
                bs = self._base_state(pid)
                os = self._offset_state(pid, match.mode, mp)
                bs.mean, bs.var = post.base.mu, post.base.var
                os.mean, os.var = post.offset.mu, post.offset.var
                os.mean += exp_offset  # eq (18)
                if not params.drift_pre_match:
                    bs.var += bg2  # eq (15)
                    os.var += g2  # eq (18)
                if params.sigma_min > 0.0:
                    floor = params.sigma_min * params.sigma_min
                    bs.var = max(bs.var, floor)
                    os.var = max(os.var, floor)
                bs.last_time = os.last_time = match.end_time
            else:
                st = self._skill_state(pid, match.mode, mp)
                st.mean, st.var = post.skill.mu, post.skill.var
                st.mean += exp_offset  # eq (8)
                if not params.drift_pre_match:
                    st.var += g2  # eq (2)/(8)
                if params.sigma_min > 0.0:
                    st.var = max(st.var, params.sigma_min * params.sigma_min)
                st.last_time = match.end_time
            self.experience[exp_key] = self.experience.get(exp_key, 0) + 1
            out[pid] = post.skill
        return out


__all__ = ["OnlineTrueSkill2", "PlayerRating", "MatchPrediction", "TeamPrediction"]
