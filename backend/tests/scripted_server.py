"""Dev server with a scripted 'LLM' instead of Claude — to demo the sandbox/flow UI for free.

Run from the repo root:  backend/.venv/bin/python backend/tests/scripted_server.py
Understands steps like:  Fill the Email field with {{env:TEST_USER}} / Click the "Add" button /
                         Verify "Buy milk" is visible / Send GET /api/todos
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
os.environ.setdefault('QA_PROVIDER', 'openai')
os.environ['OPENAI_API_KEY'] = os.environ['ANTHROPIC_API_KEY'] = 'scripted-no-real-calls'
os.environ.setdefault('TEST_USER', 'demo@example.com')
os.environ.setdefault('TEST_PASSWORD', 'demo1234')

import uvicorn  # noqa: E402
from pydantic_ai.messages import ModelResponse, ToolCallPart  # noqa: E402
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402

from app.agent.planner import planner  # noqa: E402
from app.agent.verifier import verifier  # noqa: E402
from app.main import app  # noqa: E402

THINK_S = 0.7


def _text(messages) -> str:
    return '\n'.join(
        p.content if isinstance(p.content, str) else ' '.join(c for c in p.content if isinstance(c, str))
        for m in messages for p in getattr(m, 'parts', []) if hasattr(p, 'content')
    )


def _call(info: AgentInfo, cls: str, **args) -> ModelResponse:
    tools = info.output_tools
    tool = tools[0] if len(tools) == 1 else next(t for t in tools if t.name.endswith(f'_{cls}'))
    return ModelResponse(parts=[ToolCallPart(tool.name, json.dumps(args))])


def _ref(snap: str, roles: str, name: str) -> str | None:
    m = re.search(rf'(?:{roles}) "{re.escape(name)}"[^\n]*\[ref=(\w+)\]', snap, re.I)
    return m.group(1) if m else None


async def scripted_planner(messages, info: AgentInfo) -> ModelResponse:
    await asyncio.sleep(THINK_S)
    text = _text(messages)
    step = re.findall(r'^CURRENT STEP \d+: "(.*)"$', text, re.M)[-1]
    snap = text.split('Current screen state:')[-1]
    first_try = 'Actions already taken for the current step:\n(none yet)' in text
    done = {'reasoning': f'Scripted: performing "{step}"', 'step_complete': True}

    if m := re.match(r'(?:Open|Navigate to|Go to) (?:the )?(\S+)', step, re.I):
        url = m.group(1) if m.group(1).startswith('/') or m.group(1).startswith('http') else '/'
        return _call(info, 'Navigate', url=url, **done)
    if m := re.match(r'Fill (?:the )?"?(.+?)"? field with "?(.+?)"?$', step, re.I):
        ref = _ref(snap, 'textbox', m.group(1))
        if ref:
            return _call(info, 'Fill', ref=ref, value=m.group(2), **done)
    if m := re.match(r'Click (?:the )?"(.+?)"', step, re.I):
        if first_try and m.group(1) == 'Sign in':  # demo a self-heal: bad ref first
            return _call(info, 'Click', ref='e999', reasoning='Scripted: trying a stale ref on purpose', step_complete=True)
        ref = _ref(snap, 'button|link', m.group(1))
        if ref:
            return _call(info, 'Click', ref=ref, **done)
    if m := re.match(r'Send (GET|POST|DELETE) (\S+)(?: with JSON (.+))?', step, re.I):
        body = json.loads(m.group(3)) if m.group(3) else None
        return _call(info, 'ApiRequest', method=m.group(1).upper(), url=m.group(2), json_body=body, **done)
    if step.lower().startswith(('verify', 'check')):
        quoted = re.findall(r'"([^"]+)"', step)
        return _call(info, 'Assert', claim=f'I can see {quoted[0] if quoted else "the expected state"}', **done)
    return _call(info, 'StepFailed', reasoning=f'Scripted planner does not understand: {step}')


async def scripted_verifier(messages, info: AgentInfo) -> ModelResponse:
    await asyncio.sleep(THINK_S / 2)
    text = _text(messages)
    step = re.search(r'^STEP: "(.*)"$', text, re.M).group(1)
    after = text.split('--- AFTER ---')[-1]
    if step.lower().startswith(('verify', 'check')):
        quoted = re.findall(r'"([^"]+)"', step)
        ok = all(q in after for q in quoted)
        why = f'Found {quoted} on screen' if ok else f'Could not find {quoted} on screen'
    elif step.lower().startswith('send'):
        m = re.search(r"'status': (\d+)", text)
        ok = bool(m and int(m.group(1)) < 400)
        why = f'HTTP {m.group(1) if m else "?"}'
    else:
        ok, why = True, 'Action performed'
    return _call(info, 'Verdict', success=ok, reasoning=why, is_app_error=False)


if __name__ == '__main__':
    with planner.override(model=FunctionModel(scripted_planner)), \
         verifier.override(model=FunctionModel(scripted_verifier)):
        uvicorn.run(app, port=int(os.getenv('PORT', '8000')))
