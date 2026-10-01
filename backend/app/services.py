"""Background jobs (generation, runs, flows) and the pub/sub that feeds the UI over WebSocket.

Channels:
  run:<id>        full Run snapshot after every change (steps, sub-actions, verdicts)
  flow:<id>       full FlowRun snapshot (which case is running, overall status)
  live:run:<id>   browser frames + agent activity for one run
  live:flow:<id>  same, for whichever case of the flow is running (no reconnect between cases)
"""

import asyncio
import copy
import logging
import traceback
from collections import defaultdict
from typing import Any

from playwright.async_api import Page
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, col, select

from .agent.runner import browser_session, initial_steps, new_sandbox, run_steps
from .config import MAX_CONCURRENT_RUNS, RUNS_DIR, UPLOADS_DIR
from .db import engine
from .generate.builtin import generate_cases
from .generate.testteller import generate_with_testteller
from .ingest.repo import build_context, fetch_repo
from .models import Flow, FlowRun, Project, Requirement, Run, TestCase, now

log = logging.getLogger('qa')
_tasks: set[asyncio.Task] = set()
_jobs: dict[str, asyncio.Task] = {}  # 'run:<id>' | 'flow:<id>' -> task, for cancellation
_run_slots = asyncio.Semaphore(MAX_CONCURRENT_RUNS)
ACTIVE = ('queued', 'running')


def _spawn(coro, job: str | None = None) -> None:
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    if job:
        _jobs[job] = t
        t.add_done_callback(lambda _: _jobs.pop(job, None))


# --- pub/sub ---------------------------------------------------------------------------

class Bus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self.last: dict[str, dict[str, Any]] = {}  # last message per (channel, type) for late joiners

    def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subs[channel].add(q)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        self._subs[channel].discard(q)

    def publish(self, channel: str, payload: dict[str, Any], remember: str | None = None) -> None:
        if remember:
            self.last[f'{channel}|{remember}'] = payload
        for q in list(self._subs[channel]):
            if q.full():
                q.get_nowait()  # slow client: drop oldest
            q.put_nowait(payload)

    def replay(self, channel: str) -> list[dict[str, Any]]:
        return [v for k, v in self.last.items() if k.split('|')[0] == channel]


bus = Bus()


class LiveChannel:
    """LiveSink that fans out to the run channel and (optionally) its flow channel."""

    def __init__(self, run_id: int | None = None, flow_run_id: int | None = None) -> None:
        self.run_id = run_id
        self.flow_run_id = flow_run_id

    def _channels(self) -> list[str]:
        out = []
        if self.run_id is not None:
            out.append(f'live:run:{self.run_id}')
        if self.flow_run_id is not None:
            out.append(f'live:flow:{self.flow_run_id}')
        return out

    def frame(self, data_b64: str, meta: dict[str, Any]) -> None:
        for ch in self._channels():
            bus.publish(ch, {'type': 'frame', 'data': data_b64, **meta}, remember='frame')

    def event(self, payload: dict[str, Any]) -> None:
        payload = {**payload, 'run_id': self.run_id}
        remember = payload['type'] if payload['type'] in ('url', 'phase') else None
        for ch in self._channels():
            bus.publish(ch, payload, remember=remember)


def run_to_dict(run: Run) -> dict[str, Any]:
    return run.model_dump(mode='json')


def flow_run_to_dict(session: Session, fr: FlowRun) -> dict[str, Any]:
    runs = {r.id: r for r in session.exec(select(Run).where(col(Run.id).in_(fr.run_ids)))}
    items = []
    for rid in fr.run_ids:
        r = runs.get(rid)
        if not r:
            continue
        items.append({
            'run_id': r.id, 'case_id': r.test_case_id, 'key': r.case_snapshot.get('key'),
            'title': r.case_snapshot.get('title'), 'kind': r.case_snapshot.get('kind'),
            'status': r.status, 'error': r.error,
            'step_count': len(r.steps),
            'done_steps': sum(s['status'] in ('passed', 'failed') for s in r.steps),
            'passed_steps': sum(s['status'] == 'passed' for s in r.steps),
            'current_step': next((s['index'] for s in r.steps if s['status'] == 'running'), None),
            'started_at': r.started_at.isoformat() if r.started_at else None,
            'finished_at': r.finished_at.isoformat() if r.finished_at else None,
        })
    return {**fr.model_dump(mode='json'), 'runs': items}


def _publish_flow(session: Session, flow_run_id: int | None) -> None:
    if flow_run_id is None:
        return
    fr = session.get(FlowRun, flow_run_id)
    if fr:
        bus.publish(f'flow:{flow_run_id}', flow_run_to_dict(session, fr))


# --- generation ------------------------------------------------------------------------

def start_generation(project_id: int, generator: str, max_cases: int) -> None:
    _spawn(_generate(project_id, generator, max_cases))


def _set_gen(project_id: int, status: str, message: str | None) -> None:
    with Session(engine) as s:
        p = s.get(Project, project_id)
        if p:
            p.gen_status, p.gen_message = status, message
            s.add(p)
            s.commit()


async def _generate(project_id: int, generator: str, max_cases: int) -> None:
    try:
        with Session(engine) as s:
            p = s.get(Project, project_id)
            assert p
            reqs = [r.model_dump() for r in s.exec(select(Requirement).where(Requirement.project_id == project_id))]
            existing = {c.key for c in s.exec(select(TestCase).where(TestCase.project_id == project_id))}
            repo_url, base_url, req_file = p.repo_url, p.base_url, p.requirements_file

        repo_dir, repo_ctx = None, ''
        if repo_url:
            _set_gen(project_id, 'running', 'Fetching repository…')
            repo_dir = await fetch_repo(repo_url)
            repo_ctx = await asyncio.to_thread(build_context, repo_dir)

        _set_gen(project_id, 'running', f'Generating test cases with {generator}…')
        if generator == 'testteller':
            suite = await generate_with_testteller(
                req_file, repo_dir, UPLOADS_DIR / f'spec-{project_id}.md', f'project-{project_id}'
            )
        else:
            suite = await generate_cases(reqs, repo_ctx, base_url, max_cases)

        with Session(engine) as s:
            for c in suite.cases:
                key, n = c.key, 1
                while key in existing:  # keep keys unique across regenerations
                    n += 1
                    key = f'{c.key}_{n}'
                existing.add(key)
                s.add(TestCase(
                    project_id=project_id, key=key, title=c.title, kind=c.kind, priority=c.priority,
                    category=c.category, objective=c.objective, preconditions=c.preconditions,
                    steps=[st.model_dump() for st in c.steps], requirement_refs=c.requirement_refs,
                    source=generator,
                ))
            s.commit()
        _set_gen(project_id, 'done', f'Generated {len(suite.cases)} test cases.')
    except Exception as e:
        log.exception('generation failed')
        _set_gen(project_id, 'error', f'{e.__class__.__name__}: {e}')


# --- runs ------------------------------------------------------------------------------

def _new_run(session: Session, case: TestCase, flow_run_id: int | None = None) -> Run:
    snapshot = case.model_dump(mode='json', include={'id', 'key', 'title', 'kind', 'objective', 'steps'})
    run = Run(
        project_id=case.project_id, test_case_id=case.id, flow_run_id=flow_run_id,
        case_snapshot=snapshot, steps=initial_steps(snapshot),
    )
    session.add(run)
    case.last_run_status = 'queued'
    session.add(case)
    session.flush()
    return run


def create_run(session: Session, case: TestCase) -> Run:
    run = _new_run(session, case)
    session.commit()
    session.refresh(run)
    _spawn(_execute_single(run.id), job=f'run:{run.id}')
    return run


def _persist_run(run_id: int, steps: list[dict] | None = None, **fields: Any) -> None:
    with Session(engine) as s:
        r = s.get(Run, run_id)
        if not r:
            return
        if steps is not None:
            r.steps = copy.deepcopy(steps)
            flag_modified(r, 'steps')
        for k, v in fields.items():
            setattr(r, k, v)
        s.add(r)
        if 'status' in fields:
            tc = s.get(TestCase, r.test_case_id)
            if tc:
                tc.last_run_status = fields['status']
                s.add(tc)
        s.commit()
        s.refresh(r)
        bus.publish(f'run:{run_id}', run_to_dict(r))
        _publish_flow(s, r.flow_run_id)


async def _run_on_page(run_id: int, page: Page, live: LiveChannel, open_base_url: bool) -> bool:
    """Execute one Run row on an existing page. Returns passed."""
    with Session(engine) as s:
        run = s.get(Run, run_id)
        project = s.get(Project, run.project_id)
        case, base_url, steps = copy.deepcopy(run.case_snapshot), project.base_url, copy.deepcopy(run.steps)

    live.run_id = run_id
    live.event({'type': 'case', 'key': case.get('key'), 'title': case.get('title')})

    async def emit() -> None:
        _persist_run(run_id, steps)

    _persist_run(run_id, steps, status='running', started_at=now())
    try:
        passed, error, usage = await run_steps(
            page, case, base_url, steps, RUNS_DIR / str(run_id), f'/artifacts/runs/{run_id}',
            emit, live, open_base_url,
        )
        _persist_run(run_id, steps, status='passed' if passed else 'failed', error=error, usage=usage, finished_at=now())
        return passed
    except asyncio.CancelledError:
        for st in steps:
            if st['status'] in ('running', 'pending'):
                st['status'] = 'skipped'
        _persist_run(run_id, steps, status='cancelled', error='Cancelled by user', finished_at=now())
        raise
    except Exception as e:
        log.exception('run %s crashed', run_id)
        _persist_run(run_id, steps, status='error', error=traceback.format_exception_only(e)[-1].strip(), finished_at=now())
        return False


async def _execute_single(run_id: int) -> None:
    live = LiveChannel(run_id=run_id)
    try:
        async with _run_slots:
            async with browser_session() as browser:
                _, page = await new_sandbox(browser, live)
                await _run_on_page(run_id, page, live, open_base_url=True)
    except asyncio.CancelledError:
        if _run_status(run_id) in ACTIVE:  # cancelled while still waiting for a slot
            _persist_run(run_id, status='cancelled', error='Cancelled by user', finished_at=now())
    except Exception as e:  # e.g. browser failed to launch
        log.exception('run %s failed to start', run_id)
        _persist_run(run_id, status='error', error=f'{e.__class__.__name__}: {e}', finished_at=now())
    finally:
        live.event({'type': 'phase', 'phase': 'done', 'step': None})


def _run_status(run_id: int) -> str | None:
    with Session(engine) as s:
        r = s.get(Run, run_id)
        return r.status if r else None


# --- flows -----------------------------------------------------------------------------

def create_flow_run(session: Session, flow: Flow) -> FlowRun:
    cases = {c.id: c for c in session.exec(select(TestCase).where(col(TestCase.id).in_(flow.case_ids)))}
    fr = FlowRun(project_id=flow.project_id, flow_id=flow.id, flow_name=flow.name)
    session.add(fr)
    session.flush()
    fr.run_ids = [_new_run(session, cases[cid], fr.id).id for cid in flow.case_ids if cid in cases and cases[cid].steps]
    session.add(fr)
    session.commit()
    session.refresh(fr)
    _spawn(_execute_flow(fr.id, flow.shared_session, flow.stop_on_fail), job=f'flow:{fr.id}')
    return fr


def _set_flow(flow_run_id: int, **fields: Any) -> None:
    with Session(engine) as s:
        fr = s.get(FlowRun, flow_run_id)
        for k, v in fields.items():
            setattr(fr, k, v)
        s.add(fr)
        s.commit()
        _publish_flow(s, flow_run_id)


def _skip_rest(run_ids: list[int], reason: str) -> None:
    for rid in run_ids:
        if _run_status(rid) in ACTIVE:
            with Session(engine) as s:
                r = s.get(Run, rid)
                for st in r.steps:
                    st['status'] = 'skipped'
            _persist_run(rid, r.steps, status='skipped', error=reason, finished_at=now())


async def _execute_flow(flow_run_id: int, shared_session: bool, stop_on_fail: bool) -> None:
    with Session(engine) as s:
        run_ids = list(s.get(FlowRun, flow_run_id).run_ids)
    live = LiveChannel(flow_run_id=flow_run_id)
    all_passed = True
    try:
        async with _run_slots:
            _set_flow(flow_run_id, status='running', started_at=now())
            async with browser_session() as browser:
                context = page = None
                for i, rid in enumerate(run_ids):
                    if not all_passed and stop_on_fail:
                        _skip_rest(run_ids[i:], 'Skipped: an earlier case in the flow failed')
                        break
                    _set_flow(flow_run_id, current_index=i)
                    fresh = page is None or not shared_session
                    if fresh:
                        if context:
                            await context.close()
                        context, page = await new_sandbox(browser, live)
                    passed = await _run_on_page(rid, page, live, open_base_url=fresh)
                    all_passed = all_passed and passed
        _set_flow(flow_run_id, status='passed' if all_passed else 'failed', finished_at=now())
    except asyncio.CancelledError:
        _skip_rest(run_ids, 'Cancelled by user')
        _set_flow(flow_run_id, status='cancelled', error='Cancelled by user', finished_at=now())
    except Exception as e:
        log.exception('flow run %s crashed', flow_run_id)
        _skip_rest(run_ids, 'Flow crashed')
        _set_flow(flow_run_id, status='error', error=f'{e.__class__.__name__}: {e}', finished_at=now())
    finally:
        live.event({'type': 'phase', 'phase': 'done', 'step': None})


def cancel(job: str) -> bool:
    task = _jobs.get(job)
    if not task:
        return False
    task.cancel()
    return True
