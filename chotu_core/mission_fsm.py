"""Mission state machine for one AtomQuest cleaning run.

Dock -> undock -> 360° mapping scan -> boustrophedon coverage -> spot clean /
frontier fill -> return to dock -> docking -> docked.  Stuck recovery can be
entered from any driving state and returns to the state it interrupted.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set


class MissionState(str, Enum):
    IDLE = "IDLE"
    UNDOCK = "UNDOCK"
    SCAN = "SCAN"
    COVER = "COVER"
    SPOT_CLEAN = "SPOT_CLEAN"
    STUCK_RECOVERY = "STUCK_RECOVERY"
    RETURN_TO_DOCK = "RETURN_TO_DOCK"
    DOCKING = "DOCKING"
    DOCKED = "DOCKED"
    ABORTED = "ABORTED"


S = MissionState
DRIVING = {S.UNDOCK, S.SCAN, S.COVER, S.SPOT_CLEAN, S.RETURN_TO_DOCK, S.DOCKING}

ALLOWED: Dict[MissionState, Set[MissionState]] = {
    S.IDLE: {S.UNDOCK, S.ABORTED},
    S.UNDOCK: {S.SCAN, S.STUCK_RECOVERY, S.RETURN_TO_DOCK, S.ABORTED},
    S.SCAN: {S.COVER, S.RETURN_TO_DOCK, S.ABORTED},
    S.COVER: {S.SPOT_CLEAN, S.STUCK_RECOVERY, S.RETURN_TO_DOCK, S.ABORTED},
    S.SPOT_CLEAN: {S.STUCK_RECOVERY, S.RETURN_TO_DOCK, S.ABORTED},
    S.STUCK_RECOVERY: {S.UNDOCK, S.COVER, S.SPOT_CLEAN, S.RETURN_TO_DOCK, S.ABORTED},
    S.RETURN_TO_DOCK: {S.DOCKING, S.STUCK_RECOVERY, S.ABORTED},
    S.DOCKING: {S.DOCKED, S.RETURN_TO_DOCK, S.ABORTED},
    S.DOCKED: {S.UNDOCK},
    S.ABORTED: set(),
}


class InvalidTransition(RuntimeError):
    pass


@dataclass
class Transition:
    t: float
    src: MissionState
    dst: MissionState
    reason: str


class MissionFSM:
    def __init__(self) -> None:
        self.state = S.IDLE
        self.entered_at = 0.0
        self.history: List[Transition] = []
        self.resume_state: Optional[MissionState] = None

    def transition(self, dst: MissionState, t: float, reason: str = "") -> None:
        if dst == self.state:
            return
        if dst not in ALLOWED[self.state]:
            raise InvalidTransition(f"{self.state.value} -> {dst.value} ({reason})")
        if dst == S.STUCK_RECOVERY:
            self.resume_state = self.state
        self.history.append(Transition(t, self.state, dst, reason))
        self.state = dst
        self.entered_at = t

    def time_in_state(self, t: float) -> float:
        return t - self.entered_at

    @property
    def is_driving(self) -> bool:
        return self.state in DRIVING
