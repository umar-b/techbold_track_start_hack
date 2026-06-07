"""Request body shapes for the technician API.

Most responses are plain run dictionaries from the in-memory store, so only the
incoming POST bodies need Pydantic models here.
"""
from typing import List, Optional

from pydantic import BaseModel


class StartRunIn(BaseModel):
    """Body used when the technician starts a run for one ticket."""

    ticket_id: int


class PlanStepIn(BaseModel):
    """One editable command in an approved fix plan."""

    command: str
    rationale: str = ""
    expected: str = ""


class ApproveIn(BaseModel):
    """Optional edits the technician can send before approving a plan."""

    # Kept for simple command approval experiments; the current UI sends plan steps.
    command: Optional[str] = None
    steps: Optional[List[PlanStepIn]] = None


class RejectIn(BaseModel):
    """Optional free-text steer when rejecting / refining a plan.

    Empty -> a plain replan. With text -> the agent is told to incorporate the
    technician's feedback into the next plan (a lightweight "discuss" loop).
    """

    feedback: Optional[str] = None


class SubmitActivityIn(BaseModel):
    """The final activity text that gets written back to Phoenix ERP."""

    summary: str = ""
    root_cause: str = ""
    actions_taken: str = ""
    commands_summary: str = ""
    validation_result: str = ""
    set_done: bool = True
