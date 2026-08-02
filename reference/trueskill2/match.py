"""Match-result input types.

A match result, per the paper (§2), lists "the players involved, their team
assignments, the start time and length of the match, how long each player
played, and the final score of each team" — plus, for TrueSkill 2, each
player's squad size, kill/death counts and completion status.

Time is in MINUTES throughout (start_time is an absolute timestamp in minutes,
e.g. epoch-milliseconds / 60000).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable, List, Optional, Sequence


@dataclass
class PlayerResult:
    """One player's row in a match result."""

    player_id: Hashable
    #: Minutes this player was in the match (timePlayed_i). None = full match.
    time_played: Optional[float] = None
    #: Size of the pre-made squad the player queued with (§6). 1 = solo.
    squad_size: int = 1
    #: Individual statistics (§8). None = not observed / not used.
    kills: Optional[float] = None
    deaths: Optional[float] = None
    #: Completion status (§9). True = quit / dropped out, False = completed,
    #: None = unknown (no quit observation is added either way).
    quit: Optional[bool] = None

    def play_fraction(self, length: float) -> float:
        """timePlayed_i / L — the partial-play weight of eq (5)."""
        if self.time_played is None:
            return 1.0
        if length <= 0.0:
            return 1.0
        return max(0.0, min(1.0, self.time_played / length))


@dataclass
class Team:
    """A team and its final standing. Lower rank = better; equal ranks = draw."""

    rank: int
    players: List[PlayerResult]


@dataclass
class Match:
    """One match result.

    `mode` is the game-mode key (per-mode parameters and, under §11 mode
    correlation, the per-mode skill offset are looked up by it).
    """

    mode: str
    start_time: float  # absolute minutes
    length: float  # match length L, minutes
    teams: List[Team]
    #: Opaque identifier, carried through for reporting.
    match_id: Optional[str] = None

    def __post_init__(self) -> None:
        if len(self.teams) < 2:
            raise ValueError("a match needs at least two teams")
        if self.length <= 0.0:
            raise ValueError("match length must be positive")
        # Time is MINUTES everywhere (see module docstring). timePlayed_i <= L by
        # definition, so a value well beyond L means the caller mixed units (the
        # classic seconds-vs-minutes mistake, ~60x over) — which play_fraction
        # would otherwise silently clamp to 1.0, quietly disabling partial-play,
        # counts and quit. Fail loudly instead. (A 1% slack absorbs rounding.)
        for p in self.all_players():
            if p.time_played is not None and p.time_played > self.length * 1.01:
                raise ValueError(
                    f"player {p.player_id!r} time_played={p.time_played} exceeds match "
                    f"length={self.length}; times must be in the same unit (minutes)"
                )

    @property
    def end_time(self) -> float:
        return self.start_time + self.length

    def all_players(self) -> List[PlayerResult]:
        return [p for t in self.teams for p in t.players]


def teams_from_standings(
    players: Sequence[PlayerResult], team_of: dict, standing_of: dict
) -> List[Team]:
    """Group players into Teams, ranking each team by its best standing."""
    by_team: dict = {}
    for p in players:
        by_team.setdefault(team_of[p.player_id], []).append(p)
    teams = []
    for tid, members in by_team.items():
        rank = min(standing_of[m.player_id] for m in members)
        teams.append(Team(rank=rank, players=members))
    return teams


__all__ = ["PlayerResult", "Team", "Match", "teams_from_standings"]
