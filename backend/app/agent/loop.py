"""The step loop: observe -> plan -> execute -> (verify), up to MAX_SUB_ACTIONS turns.

Mirrors agent-qa core/src/agent/loop.ts `executeStep`. There is no separate 'healing'
module: a failed action is recorded in the history + failure_context, the page is
observed again, and the planner re-plans. Too many consecutive failures fail the step.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from playwright.async_api import Page

from ..config import MAX_ATTEMPTS, MAX_SUB_ACTIONS
from .actions import Assert, StepFailed, describe
from .executor import execute
from .live import LiveSink, NullSink, action_label, element_box
from .observer import Observation, observe
from .planner import StepContext, SubActionRecord, _history_text, plan
from .verifier import verify

SaveShot = Callable[[bytes, str], str]  # (jpeg bytes, name) -> public URL
Emit = Callable[[], Awaitable[None]]


class Usage:
    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.requests = 0

    def add(self, u: Any) -> None:
        self.input_tokens += getattr(u, 'input_tokens', 0) or 0
        self.output_tokens += getattr(u, 'output_tokens', 0) or 0
        self.requests += getattr(u, 'requests', 0) or 0

    def as_dict(self) -> dict[str, int]:
        return {'input_tokens': self.input_tokens, 'output_tokens': self.output_tokens, 'requests': self.requests}


async def execute_step(
    page: Page,
    ctx: StepContext,
    state: dict[str, Any],
    save_shot: SaveShot,
    emit: Emit,
    usage: Usage,
    live: LiveSink | None = None,
) -> bool:
    """Runs one test step. Mutates `state` (shown live in the UI). Returns pass/fail."""
    live = live or NullSink()
    step_no = ctx.step_index

    def phase(name: str, **extra: Any) -> None:
        live.event({'type': 'phase', 'phase': name, 'step': step_no, **extra})

    consecutive_failures = 0
    step_before: Observation | None = None
    prev_hash: str | None = None

    def finish(ok: bool, reason: str) -> bool:
        state['status'] = 'passed' if ok else 'failed'
        state['reasoning' if ok else 'error'] = reason
        state['duration_ms'] = int((time.time() - state['_t0']) * 1000)
        live.event({'type': 'step_done', 'step': step_no, 'ok': ok, 'reason': reason})
        return ok

    for n in range(MAX_SUB_ACTIONS):
        # 1. OBSERVE
        phase('observe')
        obs = await observe(page)
        step_before = step_before or obs
        if ctx.history and prev_hash is not None:
            ctx.history[-1].screen_changed = obs.screen_hash != prev_hash
            state['sub_actions'][-1]['screen_changed'] = ctx.history[-1].screen_changed
        prev_hash = obs.screen_hash
        shot_url = save_shot(obs.screenshot, f'step{ctx.step_index + 1}-{n + 1}')

        # 2. PLAN
        phase('plan')
        action, u = await plan(ctx, obs)
        usage.add(u)
        if isinstance(action, StepFailed):
            phase('gave_up', label=action.reasoning)
            state['sub_actions'].append({
                'n': n + 1, 'action': {'type': 'StepFailed'}, 'reasoning': action.reasoning,
                'ok': False, 'screenshot': shot_url,
            })
            await emit()
            return finish(False, f'Agent gave up: {action.reasoning}')

        # 3. EXECUTE (tell the live view what we are about to do and where)
        label = action_label(action, obs.snapshot)
        ref = getattr(action, 'ref', None)
        box = await element_box(page, ref) if ref and f'[ref={ref}]' in obs.snapshot else None
        phase('act', label=label, box=box, reasoning=action.reasoning)
        if box:
            await asyncio.sleep(0.35)  # let the viewer see the highlight before the click lands
        result = await execute(page, action, ctx.base_url, obs.snapshot)
        live.event({'type': 'result', 'step': step_no, 'ok': result.ok, 'label': label, 'error': result.error})
        record = SubActionRecord(
            action=describe(action), reasoning=action.reasoning, ok=result.ok,
            error=result.error, data=result.data,
        )
        ctx.history.append(record)
        sub = {
            'n': n + 1, 'action': record.action, 'label': label, 'reasoning': record.reasoning,
            'ok': result.ok, 'error': result.error, 'data': result.data, 'screenshot': shot_url,
        }
        state['sub_actions'].append(sub)

        # 4. SELF-HEAL on failure: feed the error back and re-plan on a fresh observation
        if not result.ok:
            consecutive_failures += 1
            state['heal_count'] += 1
            ctx.failure_context = (
                f'Sub-action {n + 1} failed: {result.error}\nFailed action: {record.action}\n'
                'Adapt your approach — try a different element or strategy.'
            )
            await emit()
            if consecutive_failures >= MAX_ATTEMPTS:
                return finish(False, f'{consecutive_failures} consecutive actions failed. Last: {result.error}')
            continue
        consecutive_failures = 0
        ctx.failure_context = None
        await emit()

        if not action.step_complete:
            continue

        # 5. VERIFY (Assert without visual evidence still goes to the verifier: cheap + safer)
        phase('verify')
        after = obs if isinstance(action, Assert) else await observe(page)
        verdict, vu = await verify(
            ctx.step, ctx.expected, _history_text(ctx.history), step_before, after
        )
        usage.add(vu)
        sub['verifier'] = verdict.model_dump()
        live.event({'type': 'verdict', 'step': step_no, **verdict.model_dump()})
        state['final_screenshot'] = save_shot(after.screenshot, f'step{ctx.step_index + 1}-final')
        await emit()
        if verdict.success:
            return finish(True, verdict.reasoning)
        if verdict.is_app_error:
            return finish(False, f'App error: {verdict.reasoning}')
        record.verifier_rejection = verdict.reasoning
        state['heal_count'] += 1

    return finish(False, f'Step not completed within {MAX_SUB_ACTIONS} actions.')
