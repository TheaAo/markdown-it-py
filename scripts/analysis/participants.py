"""Participant metadata shared by the Phase 1 and Phase 2 analyses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Phase1Group = Literal["AI", "Manual"]


@dataclass(frozen=True)
class Participant:
    """Experiment participation and assignment metadata."""

    number: int
    phase1_group: Phase1Group
    participated_in_phase2: bool


PARTICIPANTS: tuple[Participant, ...] = (
    Participant(number=1, phase1_group="Manual", participated_in_phase2=False),
    Participant(number=2, phase1_group="AI", participated_in_phase2=True),
    Participant(number=3, phase1_group="AI", participated_in_phase2=True),
    Participant(number=4, phase1_group="Manual", participated_in_phase2=True),
    Participant(number=5, phase1_group="Manual", participated_in_phase2=True),
    Participant(number=7, phase1_group="AI", participated_in_phase2=True),
    Participant(number=8, phase1_group="Manual", participated_in_phase2=True),
    Participant(number=9, phase1_group="Manual", participated_in_phase2=True),
    Participant(number=10, phase1_group="AI", participated_in_phase2=False),
    Participant(number=11, phase1_group="AI", participated_in_phase2=False),
    Participant(number=12, phase1_group="AI", participated_in_phase2=True),
    Participant(number=14, phase1_group="Manual", participated_in_phase2=False),
    Participant(number=16, phase1_group="Manual", participated_in_phase2=False),
)

PARTICIPANTS_BY_NUMBER = {participant.number: participant for participant in PARTICIPANTS}

