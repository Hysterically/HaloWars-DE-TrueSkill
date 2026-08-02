"""Metric-driven evaluation — the §5 protocol.

"As each match was processed, we asked the model to predict the winning team
and give a probability for this event. When making this prediction, only the
team composition and squad membership are used ... Then we updated the skills
using the online updater with all of the information available at the end of
the match."

`evaluate_online` runs exactly that loop and returns per-player records so the
paper's subpopulation tables (win rate by squad size, experience, previous
kill rate, previous outcome — §§6-9) can be reproduced with `win_rate_by`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, Hashable, List, Optional, Sequence, Tuple

from .match import Match
from .online import OnlineTrueSkill2
from .params import Params


@dataclass
class PlayerRecord:
    """One player's slice of one evaluated match (for subpopulation metrics)."""

    match_index: int
    player_id: Hashable
    team_index: int
    predicted_team_win_prob: float
    team_won: bool
    drawn: bool
    #: Features at prediction time, à la the paper's tables:
    experience: int  # matches previously played in ANY mode (§7 metric, page 13)
    squad_size: int  # §6
    prev_kill_rate: Optional[float]  # kills/minute in the previous match (§8)
    prev_outcome: Optional[str]  # "win"/"loss"/"draw" (+ " quit"), §9


@dataclass
class Evaluation:
    accuracy: float
    log_loss: float
    n_matches: int
    records: List[PlayerRecord]


def evaluate_online(
    matches: Sequence[Match], params: Optional[Params] = None,
    rater: Optional[OnlineTrueSkill2] = None,
) -> Evaluation:
    """Run the §5 train-as-you-predict loop over `matches` (chronological)."""
    rater = rater or OnlineTrueSkill2(params)
    correct = 0
    log_loss = 0.0
    n = 0
    records: List[PlayerRecord] = []
    prev_kill_rate: Dict[Hashable, float] = {}
    prev_outcome: Dict[Hashable, str] = {}

    def any_mode_experience(pid: Hashable) -> int:
        """§7's metric experience: matches previously played in ANY mode.

        Distinct from the model's per-mode experienceOffset input (eq (8)/(18),
        which correctly stays keyed by (player, mode)). The paper's §7 table
        (page 13) partitions by matches "previously played in any game mode".
        Read before rater.update(match), so it excludes the current match.
        """
        return sum(c for (p_id, _mode), c in rater.experience.items() if p_id == pid)

    for mi, match in enumerate(matches):
        pred = rater.predict(match)
        best_rank = min(t.rank for t in match.teams)
        winners = [ti for ti, t in enumerate(match.teams) if t.rank == best_rank]
        drawn = len(winners) > 1

        # Winner-identity accuracy: predict the winning team, or "draw" (§5).
        predicted = pred.predicted_winner()
        actual: Optional[int] = None if drawn else winners[0]
        if predicted == actual:
            correct += 1
        p_actual = pred.draw_prob if drawn else pred.teams[winners[0]].win_prob
        log_loss += -math.log(max(p_actual, 1e-12))
        n += 1

        for ti, team in enumerate(match.teams):
            for p in team.players:
                records.append(
                    PlayerRecord(
                        match_index=mi,
                        player_id=p.player_id,
                        team_index=ti,
                        predicted_team_win_prob=pred.teams[ti].win_prob,
                        team_won=(ti in winners) and not drawn,
                        drawn=drawn,
                        experience=any_mode_experience(p.player_id),
                        squad_size=p.squad_size,
                        prev_kill_rate=prev_kill_rate.get(p.player_id),
                        prev_outcome=prev_outcome.get(p.player_id),
                    )
                )

        rater.update(match)

        for ti, team in enumerate(match.teams):
            outcome = "draw" if drawn else ("win" if ti in winners else "loss")
            for p in team.players:
                if p.kills is not None:
                    minutes = p.time_played if p.time_played is not None else match.length
                    if minutes and minutes > 0:
                        prev_kill_rate[p.player_id] = p.kills / minutes
                prev_outcome[p.player_id] = outcome + (" quit" if p.quit else "")

    return Evaluation(
        accuracy=correct / n if n else 0.0,
        log_loss=log_loss / n if n else 0.0,
        n_matches=n,
        records=records,
    )


def win_rate_by(
    records: Sequence[PlayerRecord], key: Callable[[PlayerRecord], object]
) -> Dict[object, Tuple[float, float, int]]:
    """The paper's table shape: bucket -> (actual win %, expected win %, n).

    Expected win rate is the mean predicted team-win probability of the
    players in the bucket; actual is their observed win rate — exactly how
    §§5-9 tabulate model fit.
    """
    buckets: Dict[object, List[PlayerRecord]] = {}
    for r in records:
        k = key(r)
        if k is None:
            continue
        buckets.setdefault(k, []).append(r)
    out: Dict[object, Tuple[float, float, int]] = {}
    for k, rs in buckets.items():
        actual = sum(1.0 for r in rs if r.team_won) / len(rs)
        expected = sum(r.predicted_team_win_prob for r in rs) / len(rs)
        out[k] = (100.0 * actual, 100.0 * expected, len(rs))
    return out


__all__ = ["evaluate_online", "Evaluation", "PlayerRecord", "win_rate_by"]
