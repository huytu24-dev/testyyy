"""Runs the real agent loop (Playwright + demo app) with scripted LLMs instead of Claude.

Proves observe -> plan -> execute -> self-heal -> verify works end to end, for free.
Needs Chromium (see README). Run: .venv/bin/pytest tests/test_agent_loop.py
"""

import asyncio
import json
import re

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agent.planner import planner
from app.agent.runner import initial_steps, run_case
from app.agent.verifier import verifier


def _prompt_text(messages) -> str:
    return '\n'.join(
        p.content if isinstance(p.content, str) else ' '.join(c for c in p.content if isinstance(c, str))
        for m in messages for p in getattr(m, 'parts', []) if hasattr(p, 'content')
    )


def _ref(snapshot: str, role: str, name: str) -> str:
    m = re.search(rf'{role} "{re.escape(name)}"[^\n]*\[ref=(\w+)\]', snapshot)
    assert m, f'{role} "{name}" not in snapshot'
    return m.group(1)


def _call(info: AgentInfo, cls: str, **args) -> ModelResponse:
    tools = info.output_tools
    tool = tools[0] if len(tools) == 1 else next(t for t in tools if t.name.endswith(f'_{cls}'))
    return ModelResponse(parts=[ToolCallPart(tool.name, json.dumps(args))])




def scripted_planner(messages, info: AgentInfo) -> ModelResponse:
    text = _prompt_text(messages)
    step = re.findall(r'^CURRENT STEP \d+: "(.*)"$', text, re.M)[-1]
    snap = text.split('Current screen state:')[-1]
    base = {'reasoning': 'scripted', 'step_complete': True}
    if 'Email' in step:
        return _call(info, 'Fill', ref=_ref(snap, 'textbox', 'Email'), value='{{env:TEST_USER}}', **base)
    if 'Password' in step:
        return _call(info, 'Fill', ref=_ref(snap, 'textbox', 'Password'), value='{{env:TEST_PASSWORD}}', **base)
    if 'Sign in' in step:
        first_try = 'Actions already taken for the current step:\n(none yet)' in text
        if first_try:  # a bogus ref -> executor error -> the loop must re-plan
            return _call(info, 'Click', ref='e9999', **base)
        assert 'PREVIOUS ACTION FAILED' in text  # the failure was fed back to the planner
        assert 'demo1234' not in text  # the password value is masked in the snapshot
        return _call(info, 'Click', ref=_ref(snap, 'button', 'Sign in'), **base)
    if step.startswith('Verify'):
        return _call(info, 'Assert', claim='heading "My todos" is visible', **base)
    if step.startswith('Send GET'):
        return _call(info, 'ApiRequest', method='GET', url='/api/todos', **base)
    return _call(info, 'StepFailed', reasoning='unknown step')


def scripted_verifier(messages, info: AgentInfo) -> ModelResponse:
    text = _prompt_text(messages)
    after = text.split('--- AFTER ---')[-1]
    step = re.search(r'^STEP: "(.*)"$', text, re.M).group(1)
    if step.startswith('Verify'):
        ok = 'My todos' in after
    elif step.startswith('Send GET'):
        ok = "'status': 200" in text
    else:
        ok = True
    return _call(info, 'Verdict', success=ok, reasoning='scripted check', is_app_error=False)


CASE = {
    'title': 'Login then read todos', 'kind': 'ui', 'objective': 'User can sign in',
    'steps': [
        {'action': 'Fill the Email field with {{env:TEST_USER}}', 'expected': ''},
        {'action': 'Fill the Password field with {{env:TEST_PASSWORD}}', 'expected': ''},
        {'action': 'Click the "Sign in" button', 'expected': 'The todo page opens'},
        {'action': 'Verify the "My todos" heading is visible', 'expected': 'My todos heading'},
        {'action': 'Send GET /api/todos', 'expected': 'status 200'},
    ],
}


def test_agent_runs_case_with_self_healing(demo_url, tmp_path, monkeypatch):
    monkeypatch.setenv('TEST_USER', 'demo@example.com')
    monkeypatch.setenv('TEST_PASSWORD', 'demo1234')
    steps = initial_steps(CASE)
    events = 0

    async def emit():
        nonlocal events
        events += 1

    with planner.override(model=FunctionModel(scripted_planner)), \
         verifier.override(model=FunctionModel(scripted_verifier)):
        passed, error, usage = asyncio.run(
            run_case(CASE, demo_url, steps, tmp_path, '/artifacts/x', emit)
        )

    assert passed, error
    assert [s['status'] for s in steps] == ['passed'] * 5
    sign_in = steps[2]
    assert sign_in['heal_count'] == 1
    assert sign_in['sub_actions'][0]['ok'] is False and sign_in['sub_actions'][1]['ok'] is True
    # secret placeholder reached the browser, not the planner log
    assert sign_in['sub_actions'][0]['action']['type'] == 'Click'
    assert steps[0]['sub_actions'][0]['action']['value'] == '{{env:TEST_USER}}'
    assert steps[4]['sub_actions'][0]['data']['status'] == 200
    assert any(tmp_path.glob('step3-*.jpg'))
    assert events > 10
