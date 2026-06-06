"""Request schemas for the technician API. Responses are run dicts from the store."""
from typing import List, Optional

from pydantic import BaseModel


class StartRunIn(BaseModel):
    ticket_id: int


class PlanStepIn(BaseModel):
    command: str
    rationale: str = ""
    expected: str = ""


class ApproveIn(BaseModel):
    # Optionally edit a single pending command, or replace the plan's steps before running.
    command: Optional[str] = None
    steps: Optional[List[PlanStepIn]] = None


class SubmitActivityIn(BaseModel):
    summary: str = ""
    root_cause: str = ""
    actions_taken: str = ""
    commands_summary: str = ""
    validation_result: str = ""
    set_done: bool = True
