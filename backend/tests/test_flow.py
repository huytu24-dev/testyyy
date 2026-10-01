"""Flows through the service layer: chained cases, shared vs isolated sandbox, live frames."""

import asyncio

from pydantic_ai.models.function import FunctionModel
from sqlmodel import Session

from app import services
from app.agent.planner import planner
from app.agent.verifier import verifier
from app.db import engine, init_db
from app.models import Flow, FlowRun, Project, Run, TestCase
from test_agent_loop import scripted_planner, scripted_verifier

LOGIN = [
    {'action': 'Fill the Email field with {{env:TEST_USER}}', 'expected': ''},
    {'action': 'Fill the Password field with {{env:TEST_PASSWORD}}', 'expected': ''},
    {'action': 'Click the "Sign in" button', 'expected': 'The todo page opens'},
]
# Only works if the browser is already signed in (i.e. continues from LOGIN).
CONTINUE = [
    {'action': 'Verify the "My todos" heading is visible', 'expected': 'My todos heading'},
    {'action': 'Send GET /api/todos', 'expected': 'status 200'},
]


def _make_flow(base_url: str, shared: bool) -> int:
    init_db()
    with Session(engine) as s:
        p = Project(name='t', base_url=base_url)
        s.add(p)
        s.flush()
        a = TestCase(project_id=p.id, key='A', title='Login', steps=LOGIN)
        b = TestCase(project_id=p.id, key='B', title='Todos', steps=CONTINUE)
        s.add_all([a, b])
        s.flush()
        f = Flow(project_id=p.id, name='login -> todos', case_ids=[a.id, b.id], shared_session=shared)
        s.add(f)
        s.commit()
        return f.id


def _run_flow(flow_id: int) -> tuple[dict, list[dict]]:
    received: list[dict] = []

    async def main():
        with Session(engine) as s:
            fr = services.create_flow_run(s, s.get(Flow, flow_id))
            fr_id = fr.id
        q = services.bus.subscribe(f'live:flow:{fr_id}')
        await asyncio.gather(*services._tasks)
        while not q.empty():
            received.append(q.get_nowait())
        with Session(engine) as s:
            return services.flow_run_to_dict(s, s.get(FlowRun, fr_id))

    with planner.override(model=FunctionModel(scripted_planner)), \
         verifier.override(model=FunctionModel(scripted_verifier)):
        return asyncio.run(main()), received


def test_flow_shared_session_chains_cases(demo_url, monkeypatch):
    monkeypatch.setenv('TEST_USER', 'demo@example.com')
    monkeypatch.setenv('TEST_PASSWORD', 'demo1234')
    flow, live = _run_flow(_make_flow(demo_url, shared=True))

    assert flow['status'] == 'passed', flow
    assert [r['status'] for r in flow['runs']] == ['passed', 'passed']
    assert flow['runs'][1]['passed_steps'] == 2
    types = {m['type'] for m in live}
    assert 'frame' in types and 'phase' in types  # browser frames were streamed
    acts = [m for m in live if m['type'] == 'phase' and m['phase'] == 'act']
    assert any('button "Sign in"' in m['label'] and m['box'] for m in acts)  # highlight box for the click


def test_flow_isolated_sandbox_and_stop_on_fail(demo_url, monkeypatch):
    monkeypatch.setenv('TEST_USER', 'demo@example.com')
    monkeypatch.setenv('TEST_PASSWORD', 'demo1234')
    flow_id = _make_flow(demo_url, shared=False)
    with Session(engine) as s:  # put the failing case first: B needs a session it won't have
        f = s.get(Flow, flow_id)
        f.case_ids = list(reversed(f.case_ids))
        s.add(f)
        s.commit()
    flow, _ = _run_flow(flow_id)

    assert flow['status'] == 'failed'
    assert [r['status'] for r in flow['runs']] == ['failed', 'skipped']
    with Session(engine) as s:
        assert s.get(Run, flow['runs'][1]['run_id']).steps[0]['status'] == 'skipped'


def test_run_endpoints_spawn_background_jobs(demo_url, monkeypatch):
    """Endpoints that start jobs must run on the event loop (regression: sync def -> no running loop)."""
    from fastapi.testclient import TestClient

    from app.main import app

    started: list[str] = []

    async def fake_flow(fr_id, *_):
        started.append(f'flow:{fr_id}')
        await asyncio.sleep(30)  # stays "running" until cancelled

    async def fake_single(run_id):
        started.append(f'run:{run_id}')
        await asyncio.sleep(30)

    monkeypatch.setattr('app.config.has_api_key', lambda: True)
    monkeypatch.setattr(services, '_execute_flow', fake_flow)
    monkeypatch.setattr(services, '_execute_single', fake_single)
    flow_id = _make_flow(demo_url, shared=True)
    with TestClient(app) as client:
        r = client.post(f'/api/flows/{flow_id}/run')
        assert r.status_code == 200, r.text
        fr = r.json()
        r2 = client.post(f'/api/cases/{fr["runs"][0]["case_id"]}/run')
        assert r2.status_code == 200, r2.text
        assert client.post(f'/api/flow-runs/{fr["id"]}/cancel').json() == {'ok': True}
        assert client.post(f'/api/runs/{r2.json()["id"]}/cancel').json() == {'ok': True}
    assert started == [f'flow:{fr["id"]}', f'run:{r2.json()["id"]}']
