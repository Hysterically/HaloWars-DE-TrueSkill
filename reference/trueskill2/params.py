"""Model parameters for TrueSkill 2.

Every tunable named in the paper (Minka, Cleven & Zaykov 2018) lives here,
grouped the way the paper groups them:

  * classic per-mode parameters (m0, v0, gamma, tau, beta, eps)      — §2, §4
  * squad offsets, one per squad size                                — §6, eq (7)
  * experience offsets, an array indexed by games played (cap 200)   — §7, eq (8)
  * individual-statistic count models (w_p, w_o, v per count type)   — §8, eq (9)
  * quit model (m_q, v_q, p_u, p_r)                                  — §9, eqs (12)-(13)
  * mode-correlation parameters (v_b, gamma_b, tau_b, m_d, v_d, w_d) — §11, eqs (14)-(20)

Conventions:
  * v0 / vb / vd / count.variance / quit variance are VARIANCES (the paper's
    v_0 etc.), not standard deviations. gamma / tau are standard deviations,
    matching the paper's gamma^2 / tau^2 usage in eqs (2)-(3).
  * Time is measured in MINUTES (the paper quotes tau per minute).
  * beta is fixed to 1 by the paper to resolve the scale ambiguity (§2); it is
    kept as a parameter so the engine can also run on the classic
    TrueSkill scale (mu0=25, beta=25/6) used elsewhere in this repo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, FrozenSet, Hashable, Optional, Sequence, Tuple

from .gaussian import ppf

#: The paper caps the experience effect at 200 games (§7).
EXPERIENCE_CAP = 200


@dataclass(frozen=True)
class CountModel:
    """Parameters of one individual-statistic count type — eq (9).

        count_i ~ max(0, N((w_p*perf_i + w_o*perfo_i) * timePlayed_i,
                           v * timePlayed_i))

    `weight_perf` is w_p (own performance), `weight_opp` is w_o (average
    opposing performance, eq (11)), and `variance` is v, the count variance per
    minute of play. "Typically, w_p and w_o have different signs. For kill
    count, w_p > 0 and w_o < 0. For death count, w_p < 0 and w_o > 0." (§8)
    """

    weight_perf: float
    weight_opp: float
    variance: float

    def __post_init__(self) -> None:
        if self.variance <= 0.0:
            raise ValueError("count variance must be positive")


@dataclass(frozen=True)
class QuitModel:
    """Parameters of the quit model — eqs (12)-(13).

        under_i ~ (N(perf_i - perfo_i - m_q, v_q) < 0)               (12)
        quit_i  = unrelated_i OR (related_i AND under_i)             (13)

    where P(unrelated) = p_unrelated and P(related) = p_related. The paper
    forces m_q <= 0 during estimation.

    `normalized` selects between the two variants of §9: the normalized model
    observes completion status for every player (used for parameter learning);
    the unnormalized model — what the paper ships for online updating — adds
    the observation only when a player actually quits, so a match with no
    quitters costs and behaves exactly like classic TrueSkill.
    """

    mean: float = 0.0  # m_q (<= 0)
    variance: float = 1.0  # v_q
    p_unrelated: float = 0.05  # p_u
    p_related: float = 0.9  # p_r
    normalized: bool = False

    def __post_init__(self) -> None:
        if self.mean > 0.0:
            raise ValueError("quit model mean m_q must be <= 0 (paper §9)")
        if self.variance <= 0.0:
            raise ValueError("quit model variance must be positive")
        for p in (self.p_unrelated, self.p_related):
            if not 0.0 <= p <= 1.0:
                raise ValueError("quit model probabilities must be in [0, 1]")


def exponential_experience_offsets(
    max_offset: float, scale: float, n: int = EXPERIENCE_CAP + 1
) -> Tuple[float, ...]:
    """A decaying-exponential experienceOffset array.

    The paper learns the 200-entry array from data (§7). With little data a
    smooth parametric shape is a practical stand-in: offset(e) =
    max_offset * exp(-e / scale). This mirrors the approximation used by this
    repo's TypeScript engine.
    """
    return tuple(max_offset * math.exp(-e / scale) for e in range(n))


@dataclass(frozen=True)
class ModeParams:
    """Per-game-mode parameters.

    Defaults are the paper's typical Halo 5 values (§4):
    m0=3, v0=1.6, gamma=1e-3, tau=1e-8 per minute, beta=1, eps=1e-3.

    (The count and quit models have no published values — the paper learns
    them per title — so they default to None, i.e. feature off.)
    """

    m0: float = 3.0  # prior mean skill, eq (1); doubles as m_d in eq (17)
    v0: float = 1.6  # prior VARIANCE, eq (1); doubles as v_d in eq (17)
    beta: float = 1.0  # performance noise std-dev, eq (4); fixed to 1 in paper
    gamma: float = 1e-3  # per-match skill drift std-dev, eq (2)/(8)
    tau: float = 1e-8  # between-match drift std-dev per sqrt(minute), eq (3)

    # Team-ordering draw margin. Either a fixed eps (the paper's epsilon), or —
    # for compatibility with classic TrueSkill implementations, including this
    # repo's TypeScript engine — derived from an assumed draw probability as
    # ppf((p+1)/2) * sqrt(n_1 + n_2) * beta per adjacent team pair.
    draw_margin: float = 1e-3  # the paper's eps
    draw_probability: Optional[float] = None  # when set, overrides draw_margin

    # §6, eq (7): squadOffset(size). Index s-1 is the offset for squad size s;
    # squadOffset(1) is fixed to 0. Sizes beyond the array reuse the last entry.
    squad_offsets: Tuple[float, ...] = (0.0,)

    # §7, eq (8): experienceOffset(min(experience, 200)).
    experience_offsets: Tuple[float, ...] = ()

    # §8, eq (9): individual statistics. None = signal not used.
    kill: Optional[CountModel] = None
    death: Optional[CountModel] = None

    # §9, eqs (12)-(13). None = quits not modelled.
    quit: Optional[QuitModel] = None

    # §11, eq (20): skill = w_d * base + offset. Only used when Params
    # enables mode correlation. The paper forces w_d >= 0.
    mode_weight: float = 1.0

    def __post_init__(self) -> None:
        if self.squad_offsets and self.squad_offsets[0] != 0.0:
            raise ValueError("squadOffset(1) is fixed to 0 (paper §6)")
        if self.mode_weight < 0.0:
            raise ValueError("mode weight w_d must be >= 0 (paper §11)")
        if self.v0 <= 0.0 or self.beta <= 0.0:
            raise ValueError("v0 and beta must be positive")
        if self.draw_probability is not None and not 0.0 < self.draw_probability < 1.0:
            raise ValueError("draw_probability must be in (0, 1)")

    # -- derived quantities ----------------------------------------------------

    def squad_offset(self, size: int) -> float:
        """squadOffset(size) with sizes beyond the array reusing the last entry."""
        if size <= 1 or not self.squad_offsets:
            return 0.0
        return self.squad_offsets[min(size, len(self.squad_offsets)) - 1]

    def experience_offset(self, experience: int) -> float:
        """experienceOffset(min(experience, 200)) — eq (8). 0 if not configured."""
        if not self.experience_offsets:
            return 0.0
        return self.experience_offsets[min(experience, EXPERIENCE_CAP, len(self.experience_offsets) - 1)]

    def pair_margin(self, weight_sum: float) -> float:
        """Draw margin for one adjacent pair in the team-ordering chain.

        `weight_sum` is the total play-time weight of the two teams (equal to
        the player count when everyone plays the full match), used only in the
        draw-probability form (Herbrich et al. 2007 convention).
        """
        if self.draw_probability is None:
            return self.draw_margin
        return ppf((self.draw_probability + 1.0) / 2.0) * math.sqrt(weight_sum) * self.beta


@dataclass(frozen=True)
class BaseSkillParams:
    """Parameters of the shared base skill — §11, eqs (14)-(16).

        base_{t0}  ~ N(0, v_b)                                       (14)
        base_{t+L} ~ N(base_t, gamma_b^2)   after a match             (15)
        base_{t'}  ~ N(base_t, tau_b^2 (t'-t))   between matches      (16)
    """

    vb: float = 1.6
    gamma: float = 1e-3
    tau: float = 1e-8

    def __post_init__(self) -> None:
        if self.vb <= 0.0:
            raise ValueError("vb must be positive")


@dataclass
class Params:
    """Full model configuration: per-mode parameters plus global switches."""

    #: Per-mode parameters; modes absent from the dict get `default_mode`.
    modes: Dict[str, ModeParams] = field(default_factory=dict)
    default_mode: ModeParams = field(default_factory=ModeParams)

    #: §11 mode correlation. When True, each player has one base skill plus a
    #: per-mode offset and skill = w_d * base + offset (eq 20). When False,
    #: each mode keeps an independent skill (classic behaviour, m0/v0 priors).
    mode_correlation: bool = False
    base: BaseSkillParams = field(default_factory=BaseSkillParams)

    #: Operational floor on posterior skill std-dev, applied when storing a
    #: rating. NOT part of the paper — provided for compatibility with this
    #: repo's TypeScript engine (which floors sigma at 1.0). 0 disables.
    sigma_min: float = 0.0

    #: The paper applies the per-match drift gamma AFTER the match (eq 2/8;
    #: §3 step (d)). Some implementations — including this repo's TypeScript
    #: engine — instead inflate the prior right BEFORE the match. The two only
    #: differ in whether a player's very first match is played at variance v0
    #: or v0 + gamma^2. True replicates the before-match convention.
    drift_pre_match: bool = False

    #: §12: player ids whose skill is CONSTANT over time (e.g. bots). The
    #: eq-(2)/(3) drift and eq-(8) experience bias are NOT applied to them
    #: ("a bot's skill is assumed constant over time. This means that the
    #: updates (8) and (3) are not applied to bot skills"), so they form a
    #: fixed baseline that humans in the same mode/match are measured against.
    #: Their skill can still shift as match evidence refines it, then converges.
    constant_skill_players: FrozenSet[Hashable] = field(default_factory=frozenset)

    def mode(self, name: str) -> ModeParams:
        return self.modes.get(name, self.default_mode)

    def is_constant(self, player_id: Hashable) -> bool:
        """§12: whether this player's skill is held constant over time (a bot)."""
        return player_id in self.constant_skill_players

    def with_mode(self, name: str, mp: ModeParams) -> "Params":
        modes = dict(self.modes)
        modes[name] = mp
        return replace(self, modes=modes)


def halo5_params() -> Params:
    """The paper's published typical Halo 5 parameter values (§4)."""
    return Params()


__all__ = [
    "EXPERIENCE_CAP",
    "CountModel",
    "QuitModel",
    "ModeParams",
    "BaseSkillParams",
    "Params",
    "exponential_experience_offsets",
    "halo5_params",
]
