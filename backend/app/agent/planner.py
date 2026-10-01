"""Planner: one LLM call per sub-action -> exactly one action (forced tool use).

Mirrors agent-qa core/src/agent/planner.ts + prompts.ts (buildSystemPrompt / buildStepPrompt).
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, BinaryContent

from ..config import MODEL
from .actions import ACTIONS, StepFailed
from .observer import Observation

SYSTEM_PROMPT = """\
You are a QA automation agent driving a real web browser to execute a test case, one step
at a time. Each turn you receive the current step, what you already did for it, and the
current screen (accessibility tree with [ref=eN] markers + a screenshot). You answer with
exactly ONE action.

Rules:
1. Use only refs that appear in the CURRENT snapshot. Refs change between turns.
2. Do the step literally. Do not skip ahead to later steps or do extra work.
3. If an element is not visible, scroll or wait before concluding it does not exist.
4. Set step_complete=true on the action that finishes the step (for input steps: the fill;
   for click steps: the click). A verifier will check the screen afterwards.
5. "Verify/Check ..." steps: if the evidence is visible, answer Assert with step_complete=true,
   quoting the visible text. If it is clearly NOT there, answer StepFailed.
6. If your previous action failed or the screen did not change, try a DIFFERENT element or
   strategy. Never repeat the same failing action.
7. If the verifier rejected your completion, address its reason; do not just claim again.
8. Values like {{env:NAME}} are placeholders: pass them through literally in Fill/ApiRequest.
9. API steps ("Send GET /api/..."): use ApiRequest. The response is shown to you and the
   verifier in the history.
10. Answer StepFailed if the app shows an error that blocks the step, the required element
    does not exist after reasonable search, or the step is ambiguous. Do not guess.
"""

planner = Agent(
    MODEL,
    output_type=[*ACTIONS, StepFailed],
    instructions=SYSTEM_PROMPT,
    defer_model_check=True,
    retries=2,
)


@dataclass
class SubActionRecord:
    action: dict[str, Any]
    reasoning: str
    ok: bool
    error: str | None = None
    data: dict[str, Any] | None = None
    screen_changed: bool | None = None
    verifier_rejection: str | None = None


@dataclass
class StepContext:
    case_title: str
    objective: str
    base_url: str
    step_index: int
    step: str
    expected: str
    previous_steps: list[dict[str, str]] = field(default_factory=list)
    history: list[SubActionRecord] = field(default_factory=list)
    failure_context: str | None = None


def _history_text(history: list[SubActionRecord]) -> str:
    if not history:
        return '(none yet)'
    lines = []
    for i, h in enumerate(history, 1):
        mark = '✓' if h.ok else '✗'
        line = f'{i}. {mark} {h.action} — {h.reasoning}'
        if h.error:
            line += f'\n   FAILED: {h.error}'
        if h.data:
            line += f'\n   RESULT: {h.data}'
        if h.screen_changed is False:
            line += '\n   NOTE: the screen did NOT change after this action.'
        if h.verifier_rejection:
            line += f'\n   VERIFIER REJECTED COMPLETION: {h.verifier_rejection}'
        lines.append(line)
    last_two = [str(h.action) for h in history[-2:]]
    if len(last_two) == 2 and last_two[0] == last_two[1]:
        lines.append('WARNING: you repeated the same action twice. Change strategy.')
    return '\n'.join(lines)


def build_step_prompt(ctx: StepContext, obs: Observation) -> str:
    prev = '\n'.join(
        f'- {p["action"]} → {p["outcome"]}' for p in ctx.previous_steps
    ) or '(this is the first step)'
    parts = [
        f'Test case: {ctx.case_title}\nObjective: {ctx.objective}\nApp base URL: {ctx.base_url}',
        f'Previous steps (already passed):\n{prev}',
        f'Actions already taken for the current step:\n{_history_text(ctx.history)}',
    ]
    if ctx.failure_context:
        parts.append(f'PREVIOUS ACTION FAILED:\n{ctx.failure_context}')
    parts.append(
        f'CURRENT STEP {ctx.step_index + 1}: "{ctx.step}"'
        + (f'\nExpected after this step: "{ctx.expected}"' if ctx.expected else '')
    )
    parts.append(f'Current screen state:\n{obs.as_text()}')
    return '\n\n'.join(parts)


async def plan(ctx: StepContext, obs: Observation):
    """Returns (action_or_StepFailed, usage)."""
    prompt = build_step_prompt(ctx, obs)
    result = await planner.run(
        [prompt, BinaryContent(data=obs.screenshot, media_type='image/jpeg')]
    )
    return result.output, result.usage
