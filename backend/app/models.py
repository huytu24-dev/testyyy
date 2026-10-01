from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    base_url: str
    repo_url: str | None = None
    requirements_file: str | None = None
    # generation job state: idle | running | done | error
    gen_status: str = 'idle'
    gen_message: str | None = None
    created_at: datetime = Field(default_factory=now)


class Requirement(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key='project.id', index=True)
    ref: str
    feature: str = ''
    text: str
    acceptance: str = ''
    priority: str = ''


class TestCase(SQLModel, table=True):
    __test__ = False  # keep pytest from collecting this class

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key='project.id', index=True)
    key: str
    title: str
    kind: str = 'ui'  # ui | api
    priority: str = 'P2'
    category: str = ''
    objective: str = ''
    preconditions: str = ''
    # [{"action": "...", "expected": "..."}]
    steps: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    requirement_refs: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = 'draft'  # draft | approved | rejected
    source: str = 'manual'  # builtin | testteller | manual
    review: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    last_run_status: str | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Flow(SQLModel, table=True):
    """An ordered chain of test cases, e.g. Login -> Add todo -> Delete todo."""

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key='project.id', index=True)
    name: str
    description: str = ''
    case_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    # Keep the same browser page between cases (case 2 continues where case 1 ended).
    shared_session: bool = True
    stop_on_fail: bool = True
    created_at: datetime = Field(default_factory=now)


class FlowRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key='project.id', index=True)
    flow_id: int = Field(foreign_key='flow.id', index=True)
    flow_name: str = ''
    status: str = 'queued'  # queued | running | passed | failed | error | cancelled
    run_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    current_index: int | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Run(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key='project.id', index=True)
    test_case_id: int = Field(foreign_key='testcase.id', index=True)
    flow_run_id: int | None = Field(default=None, index=True)
    # queued | running | passed | failed | error | cancelled | skipped
    status: str = 'queued'
    error: str | None = None
    case_snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    steps: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    usage: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
