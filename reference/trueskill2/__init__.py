"""TrueSkill 2, in Python, from the original paper.

A from-scratch, pure-standard-library implementation of the full generative
model and inference of:

    Tom Minka, Ryan Cleven, Yordan Zaykov.
    "TrueSkill 2: An improved Bayesian skill rating system."
    Microsoft Research technical report MSR-TR-2018-8, March 2018.

See python/README.md for the paper-section -> module map.
"""

from .batch import BatchResult, batch_rate
from .factorgraph import MemberPrior, MemberPosterior, rate_match
from .fitting import FITTABLE, RpropOptions, fit_mode_params, rprop_maximize
from .gaussian import Gaussian
from .match import Match, PlayerResult, Team
from .metrics import Evaluation, evaluate_online, win_rate_by
from .online import MatchPrediction, OnlineTrueSkill2, PlayerRating
from .params import (
    BaseSkillParams,
    CountModel,
    EXPERIENCE_CAP,
    ModeParams,
    Params,
    QuitModel,
    exponential_experience_offsets,
    halo5_params,
)

__version__ = "1.0.0"

__all__ = [
    "Gaussian",
    "Match",
    "PlayerResult",
    "Team",
    "Params",
    "ModeParams",
    "BaseSkillParams",
    "CountModel",
    "QuitModel",
    "EXPERIENCE_CAP",
    "exponential_experience_offsets",
    "halo5_params",
    "OnlineTrueSkill2",
    "PlayerRating",
    "MatchPrediction",
    "MemberPrior",
    "MemberPosterior",
    "rate_match",
    "batch_rate",
    "BatchResult",
    "evaluate_online",
    "Evaluation",
    "win_rate_by",
    "fit_mode_params",
    "rprop_maximize",
    "RpropOptions",
    "FITTABLE",
]
