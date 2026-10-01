from typing import Literal

from pydantic import BaseModel, Field


class GeneratedStep(BaseModel):
    action: str = Field(description='One user/system action, phrased for a browser agent.')
    expected: str = Field(default='', description='Observable outcome after the action, or empty.')


class GeneratedCase(BaseModel):
    key: str = Field(description='E2E_1, E2E_2 ... for UI journeys, API_1 ... for API cases')
    title: str
    kind: Literal['ui', 'api']
    priority: Literal['P1', 'P2', 'P3'] = 'P2'
    category: str = Field(default='Happy Path', description='Happy Path | Negative | Edge Case')
    objective: str
    preconditions: str = ''
    steps: list[GeneratedStep] = Field(min_length=1)
    requirement_refs: list[str] = Field(default_factory=list)


class GeneratedSuite(BaseModel):
    cases: list[GeneratedCase]


class StepIssue(BaseModel):
    index: int = Field(description='0-based step index; -1 for the whole case')
    severity: Literal['error', 'warning', 'info']
    issue: str
    suggestion: str = ''


class CaseReview(BaseModel):
    score: int = Field(ge=0, le=10, description='10 = clear, runnable, verifiable')
    runnable: bool = Field(description='Can a browser agent execute this as-is?')
    summary: str
    issues: list[StepIssue] = Field(default_factory=list)
