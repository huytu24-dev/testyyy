import asyncio
import logging
import re
import shutil
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlmodel import Session, col, delete, select

from . import config
from .db import engine, get_session, init_db
from .generate.review import review_case
from .generate.testteller import testteller_bin
from .ingest.excel import parse_requirements
from .models import Flow, FlowRun, Project, Requirement, Run, TestCase, now
from .services import (
    ACTIVE, bus, cancel, create_flow_run, create_run, flow_run_to_dict, run_to_dict, start_generation,
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # Runs that were in flight when the server stopped will never finish.
    with Session(engine) as s:
        for r in s.exec(select(Run).where(col(Run.status).in_(['queued', 'running']))):
            r.status, r.error = 'error', 'Server restarted while running'
            s.add(r)
        for fr in s.exec(select(FlowRun).where(col(FlowRun.status).in_(['queued', 'running']))):
            fr.status, fr.error = 'error', 'Server restarted while running'
            s.add(fr)
        for p in s.exec(select(Project).where(Project.gen_status == 'running')):
            p.gen_status, p.gen_message = 'error', 'Server restarted while generating'
            s.add(p)
        s.commit()
    yield


app = FastAPI(title='Mini QA Agent', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173'], allow_methods=['*'], allow_headers=['*'])
app.mount('/artifacts', StaticFiles(directory=config.DATA_DIR), name='artifacts')

DB = Depends(get_session)


def _get(session: Session, model, id_: int):
    obj = session.get(model, id_)
    if not obj:
        raise HTTPException(404, f'{model.__name__} {id_} not found')
    return obj


@app.get('/api/health')
def health() -> dict[str, Any]:
    return {
        'ok': True,
        'llm_ready': config.has_api_key(),
        'provider': config.PROVIDER,
        'missing_keys': config.missing_keys(),
        'model': config.MODEL,
        'verifier_model': config.VERIFIER_MODEL,
        'testteller_installed': testteller_bin() is not None,
    }


# --- projects --------------------------------------------------------------------------

@app.get('/api/projects')
def list_projects(session: Session = DB) -> list[dict[str, Any]]:
    out = []
    for p in session.exec(select(Project).order_by(col(Project.id).desc())):
        cases = session.exec(select(TestCase).where(TestCase.project_id == p.id)).all()
        out.append({
            **p.model_dump(mode='json'),
            'case_count': len(cases),
            'approved_count': sum(c.status == 'approved' for c in cases),
            'passed_count': sum(c.last_run_status == 'passed' for c in cases),
            'failed_count': sum(c.last_run_status in ('failed', 'error') for c in cases),
        })
    return out


@app.post('/api/projects')
async def create_project(
    name: str = Form(...),
    base_url: str = Form(...),
    repo_url: str = Form(''),
    requirements: UploadFile | None = File(None),
    session: Session = DB,
) -> dict[str, Any]:
    project = Project(name=name.strip(), base_url=base_url.strip().rstrip('/'), repo_url=repo_url.strip() or None)
    session.add(project)
    session.commit()
    session.refresh(project)
    reqs: list[dict] = []
    if requirements and requirements.filename:
        safe = re.sub(r'[^\w.\-]', '_', requirements.filename)
        dest = config.UPLOADS_DIR / f'{project.id}-{safe}'
        with dest.open('wb') as f:
            shutil.copyfileobj(requirements.file, f)
        try:
            reqs = await asyncio.to_thread(parse_requirements, dest)
        except Exception as e:
            session.delete(project)
            session.commit()
            raise HTTPException(400, f'Cannot read Excel file: {e}')
        project.requirements_file = str(dest)
        for r in reqs:
            session.add(Requirement(project_id=project.id, **r))
        session.add(project)
        session.commit()
    return {**project.model_dump(mode='json'), 'requirement_count': len(reqs)}


@app.get('/api/projects/{project_id}')
def get_project(project_id: int, session: Session = DB) -> dict[str, Any]:
    p = _get(session, Project, project_id)
    reqs = session.exec(select(Requirement).where(Requirement.project_id == project_id)).all()
    return {**p.model_dump(mode='json'), 'requirements': [r.model_dump() for r in reqs]}


class ProjectUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    repo_url: str | None = None


@app.put('/api/projects/{project_id}')
def update_project(project_id: int, body: ProjectUpdate, session: Session = DB) -> dict[str, Any]:
    p = _get(session, Project, project_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v.rstrip('/') if k == 'base_url' and v else v)
    session.add(p)
    session.commit()
    return p.model_dump(mode='json')


@app.delete('/api/projects/{project_id}')
def delete_project(project_id: int, session: Session = DB) -> dict[str, bool]:
    p = _get(session, Project, project_id)
    for model in (Run, FlowRun, Flow, TestCase, Requirement):
        session.exec(delete(model).where(model.project_id == project_id))
    session.delete(p)
    session.commit()
    return {'ok': True}


class GenerateBody(BaseModel):
    generator: Literal['builtin', 'testteller'] = 'builtin'
    max_cases: int = Field(default=8, ge=1, le=30)


@app.post('/api/projects/{project_id}/generate')
async def generate(project_id: int, body: GenerateBody, session: Session = DB) -> dict[str, Any]:
    p = _get(session, Project, project_id)
    if p.gen_status == 'running':
        raise HTTPException(409, 'Generation already running')
    if body.generator == 'builtin' and not config.has_api_key():
        raise HTTPException(400, config.missing_key_message())
    p.gen_status, p.gen_message = 'running', 'Starting…'
    session.add(p)
    session.commit()
    start_generation(project_id, body.generator, body.max_cases)
    return {'ok': True}


# --- test cases ------------------------------------------------------------------------

class StepIn(BaseModel):
    action: str
    expected: str = ''


class CaseIn(BaseModel):
    key: str | None = None
    title: str
    kind: Literal['ui', 'api'] = 'ui'
    priority: Literal['P1', 'P2', 'P3'] = 'P2'
    category: str = ''
    objective: str = ''
    preconditions: str = ''
    steps: list[StepIn] = Field(default_factory=list)
    status: Literal['draft', 'approved', 'rejected'] | None = None


@app.get('/api/projects/{project_id}/cases')
def list_cases(project_id: int, session: Session = DB) -> list[dict[str, Any]]:
    cases = session.exec(select(TestCase).where(TestCase.project_id == project_id).order_by(col(TestCase.id)))
    return [c.model_dump(mode='json') for c in cases]


@app.post('/api/projects/{project_id}/cases')
def create_case(project_id: int, body: CaseIn, session: Session = DB) -> dict[str, Any]:
    _get(session, Project, project_id)
    count = len(session.exec(select(TestCase.id).where(TestCase.project_id == project_id)).all())
    data = body.model_dump(exclude={'status'})
    data['key'] = body.key or f'TC_{count + 1}'
    case = TestCase(project_id=project_id, source='manual', **data)
    session.add(case)
    session.commit()
    session.refresh(case)
    return case.model_dump(mode='json')


@app.get('/api/cases/{case_id}')
def get_case(case_id: int, session: Session = DB) -> dict[str, Any]:
    case = _get(session, TestCase, case_id)
    runs = session.exec(select(Run).where(Run.test_case_id == case_id).order_by(col(Run.id).desc()).limit(20))
    return {
        **case.model_dump(mode='json'),
        'runs': [r.model_dump(mode='json', include={'id', 'status', 'error', 'created_at', 'finished_at'}) for r in runs],
    }


@app.put('/api/cases/{case_id}')
def update_case(case_id: int, body: CaseIn, session: Session = DB) -> dict[str, Any]:
    case = _get(session, TestCase, case_id)
    data = body.model_dump(exclude_unset=True)
    steps_changed = 'steps' in data and data['steps'] != case.steps
    for k, v in data.items():
        if v is not None:
            setattr(case, k, v)
    if steps_changed:
        case.review = None  # review no longer matches the steps
        if body.status is None and case.status == 'approved':
            case.status = 'draft'  # edited cases need re-approval
    case.updated_at = now()
    session.add(case)
    session.commit()
    session.refresh(case)
    return case.model_dump(mode='json')


@app.delete('/api/cases/{case_id}')
def delete_case(case_id: int, session: Session = DB) -> dict[str, bool]:
    case = _get(session, TestCase, case_id)
    session.exec(delete(Run).where(Run.test_case_id == case_id))
    session.delete(case)
    session.commit()
    return {'ok': True}


@app.post('/api/cases/{case_id}/review')
async def review(case_id: int, session: Session = DB) -> dict[str, Any]:
    if not config.has_api_key():
        raise HTTPException(400, config.missing_key_message())
    case = _get(session, TestCase, case_id)
    project = _get(session, Project, case.project_id)
    result = await review_case(case.model_dump(mode='json'), project.base_url)
    case.review = result.model_dump()
    session.add(case)
    session.commit()
    return case.review


# --- runs ------------------------------------------------------------------------------

@app.post('/api/cases/{case_id}/run')
async def run_case(case_id: int, session: Session = DB) -> dict[str, Any]:
    if not config.has_api_key():
        raise HTTPException(400, config.missing_key_message())
    case = _get(session, TestCase, case_id)
    if not case.steps:
        raise HTTPException(400, 'Test case has no steps')
    return run_to_dict(create_run(session, case))


class RunManyBody(BaseModel):
    case_ids: list[int] | None = None  # None = all approved cases


@app.post('/api/projects/{project_id}/runs')
async def run_many(project_id: int, body: RunManyBody, session: Session = DB) -> list[dict[str, Any]]:
    if not config.has_api_key():
        raise HTTPException(400, config.missing_key_message())
    q = select(TestCase).where(TestCase.project_id == project_id)
    q = q.where(col(TestCase.id).in_(body.case_ids)) if body.case_ids else q.where(TestCase.status == 'approved')
    cases = [c for c in session.exec(q).all() if c.steps]
    if not cases:
        raise HTTPException(400, 'No runnable cases (approve some cases first)')
    return [run_to_dict(create_run(session, c)) for c in cases]


@app.get('/api/projects/{project_id}/runs')
def list_runs(project_id: int, session: Session = DB) -> list[dict[str, Any]]:
    runs = session.exec(select(Run).where(Run.project_id == project_id).order_by(col(Run.id).desc()).limit(100))
    return [
        {
            **r.model_dump(mode='json', include={'id', 'test_case_id', 'flow_run_id', 'status', 'error', 'created_at', 'started_at', 'finished_at', 'usage'}),
            'case_key': r.case_snapshot.get('key'), 'case_title': r.case_snapshot.get('title'),
            'step_count': len(r.steps), 'passed_steps': sum(s['status'] == 'passed' for s in r.steps),
        }
        for r in runs
    ]


@app.get('/api/runs/{run_id}')
def get_run(run_id: int, session: Session = DB) -> dict[str, Any]:
    return run_to_dict(_get(session, Run, run_id))


@app.post('/api/runs/{run_id}/cancel')
async def cancel_run(run_id: int, session: Session = DB) -> dict[str, bool]:
    run = _get(session, Run, run_id)
    if run.flow_run_id is not None:
        return {'ok': cancel(f'flow:{run.flow_run_id}')}
    return {'ok': cancel(f'run:{run_id}')}


# --- flows -----------------------------------------------------------------------------

class FlowIn(BaseModel):
    name: str
    description: str = ''
    case_ids: list[int] = Field(default_factory=list)
    shared_session: bool = True
    stop_on_fail: bool = True


def _flow_dict(session: Session, flow: Flow) -> dict[str, Any]:
    last = session.exec(
        select(FlowRun).where(FlowRun.flow_id == flow.id).order_by(col(FlowRun.id).desc()).limit(1)
    ).first()
    return {
        **flow.model_dump(mode='json'),
        'last_run': last.model_dump(mode='json', include={'id', 'status', 'created_at'}) if last else None,
    }


@app.get('/api/projects/{project_id}/flows')
def list_flows(project_id: int, session: Session = DB) -> list[dict[str, Any]]:
    flows = session.exec(select(Flow).where(Flow.project_id == project_id).order_by(col(Flow.id)))
    return [_flow_dict(session, f) for f in flows]


@app.post('/api/projects/{project_id}/flows')
def create_flow(project_id: int, body: FlowIn, session: Session = DB) -> dict[str, Any]:
    _get(session, Project, project_id)
    flow = Flow(project_id=project_id, **body.model_dump())
    session.add(flow)
    session.commit()
    session.refresh(flow)
    return _flow_dict(session, flow)


@app.get('/api/flows/{flow_id}')
def get_flow(flow_id: int, session: Session = DB) -> dict[str, Any]:
    flow = _get(session, Flow, flow_id)
    runs = session.exec(select(FlowRun).where(FlowRun.flow_id == flow_id).order_by(col(FlowRun.id).desc()).limit(20))
    return {**_flow_dict(session, flow), 'runs': [r.model_dump(mode='json') for r in runs]}


@app.put('/api/flows/{flow_id}')
def update_flow(flow_id: int, body: FlowIn, session: Session = DB) -> dict[str, Any]:
    flow = _get(session, Flow, flow_id)
    for k, v in body.model_dump().items():
        setattr(flow, k, v)
    session.add(flow)
    session.commit()
    session.refresh(flow)
    return _flow_dict(session, flow)


@app.delete('/api/flows/{flow_id}')
def delete_flow(flow_id: int, session: Session = DB) -> dict[str, bool]:
    flow = _get(session, Flow, flow_id)
    session.exec(delete(FlowRun).where(FlowRun.flow_id == flow_id))
    session.delete(flow)
    session.commit()
    return {'ok': True}


@app.post('/api/flows/{flow_id}/run')
async def run_flow(flow_id: int, session: Session = DB) -> dict[str, Any]:
    if not config.has_api_key():
        raise HTTPException(400, config.missing_key_message())
    flow = _get(session, Flow, flow_id)
    if not flow.case_ids:
        raise HTTPException(400, 'Flow has no test cases')
    fr = create_flow_run(session, flow)
    return flow_run_to_dict(session, fr)


@app.get('/api/projects/{project_id}/flow-runs')
def list_flow_runs(project_id: int, session: Session = DB) -> list[dict[str, Any]]:
    frs = session.exec(select(FlowRun).where(FlowRun.project_id == project_id).order_by(col(FlowRun.id).desc()).limit(50))
    return [flow_run_to_dict(session, fr) for fr in frs]


@app.get('/api/flow-runs/{flow_run_id}')
def get_flow_run(flow_run_id: int, session: Session = DB) -> dict[str, Any]:
    return flow_run_to_dict(session, _get(session, FlowRun, flow_run_id))


@app.post('/api/flow-runs/{flow_run_id}/cancel')
async def cancel_flow_run(flow_run_id: int, session: Session = DB) -> dict[str, bool]:
    _get(session, FlowRun, flow_run_id)
    return {'ok': cancel(f'flow:{flow_run_id}')}


# --- websockets ------------------------------------------------------------------------

async def _close(ws: WebSocket) -> None:
    try:
        await ws.close()
    except Exception:
        pass


async def _stream_state(ws: WebSocket, channel: str, load) -> None:
    """Send the current snapshot, then every update until the job is no longer active."""
    await ws.accept()
    q = bus.subscribe(channel)
    try:
        with Session(engine) as s:
            current = load(s)
        if current is None:
            return
        await ws.send_json(current)
        if current['status'] not in ACTIVE:
            return
        while True:
            payload = await q.get()
            await ws.send_json(payload)
            if payload['status'] not in ACTIVE:
                break
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(channel, q)
        await _close(ws)


@app.websocket('/api/runs/{run_id}/ws')
async def run_ws(ws: WebSocket, run_id: int) -> None:
    await _stream_state(ws, f'run:{run_id}', lambda s: (r := s.get(Run, run_id)) and run_to_dict(r))


@app.websocket('/api/flow-runs/{flow_run_id}/ws')
async def flow_run_ws(ws: WebSocket, flow_run_id: int) -> None:
    await _stream_state(
        ws, f'flow:{flow_run_id}', lambda s: (fr := s.get(FlowRun, flow_run_id)) and flow_run_to_dict(s, fr)
    )


@app.websocket('/api/live/{kind}/{obj_id}')
async def live_ws(ws: WebSocket, kind: Literal['run', 'flow'], obj_id: int) -> None:
    """Browser frames + agent activity. Replays the last frame/url/phase for late joiners."""
    await ws.accept()
    channel = f'live:{kind}:{obj_id}'
    q = bus.subscribe(channel)
    try:
        for msg in bus.replay(channel):
            await ws.send_json(msg)
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=15)
            except asyncio.TimeoutError:
                payload = {'type': 'ping'}  # also detects closed sockets
            await ws.send_json(payload)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        bus.unsubscribe(channel, q)
        await _close(ws)
