"""Run test cases in a sandboxed browser. Mirrors agent-qa core/src/agent/runner.ts `runTest`.

Sandbox = a fresh Playwright BrowserContext per case (own cookies/storage), or one shared
context for a flow whose cases continue from each other.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ..config import HEADLESS, PREVIOUS_STEP_COUNT, STEP_TIMEOUT_S, VIEWPORT
from .live import LiveSink, NullSink, start_screencast
from .loop import Usage, execute_step
from .planner import StepContext

Emit = Callable[[], Awaitable[None]]


def initial_steps(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            'index': i, 'action': s.get('action', ''), 'expected': s.get('expected', ''),
            'status': 'pending', 'sub_actions': [], 'heal_count': 0,
            'error': None, 'reasoning': None, 'final_screenshot': None, 'duration_ms': None,
        }
        for i, s in enumerate(case.get('steps', []))
    ]


@asynccontextmanager
async def browser_session() -> AsyncIterator[Browser]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        try:
            yield browser
        finally:
            await browser.close()


async def new_sandbox(browser: Browser, live: LiveSink) -> tuple[BrowserContext, Page]:
    context = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True)
    page = await context.new_page()
    await start_screencast(page, live)
    return context, page


async def run_steps(
    page: Page,
    case: dict[str, Any],
    base_url: str,
    steps: list[dict[str, Any]],
    artifacts_dir: Path,
    artifacts_url: str,
    emit: Emit,
    live: LiveSink | None = None,
    open_base_url: bool = True,
) -> tuple[bool, str | None, dict[str, int]]:
    """Executes steps in order on `page`; stops at the first failure. Returns (passed, error, usage)."""
    live = live or NullSink()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    usage = Usage()

    def save_shot(data: bytes, name: str) -> str:
        (artifacts_dir / f'{name}.jpg').write_bytes(data)
        return f'{artifacts_url}/{name}.jpg'

    if open_base_url and case.get('kind', 'ui') == 'ui':
        live.event({'type': 'phase', 'phase': 'navigate', 'step': None, 'label': f'Open {base_url}'})
        await page.goto(base_url, wait_until='domcontentloaded', timeout=30_000)

    previous: list[dict[str, str]] = []
    for i, state in enumerate(steps):
        state['status'] = 'running'
        state['_t0'] = time.time()
        await emit()
        ctx = StepContext(
            case_title=case.get('title', ''), objective=case.get('objective', ''),
            base_url=base_url, step_index=i, step=state['action'],
            expected=state['expected'], previous_steps=previous[-PREVIOUS_STEP_COUNT:],
        )
        try:
            ok = await asyncio.wait_for(
                execute_step(page, ctx, state, save_shot, emit, usage, live), timeout=STEP_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            state['status'], state['error'] = 'failed', f'Step timed out after {STEP_TIMEOUT_S:.0f}s'
            ok = False
        state.pop('_t0', None)
        await emit()
        if not ok:
            for rest in steps[i + 1 :]:
                rest['status'] = 'skipped'
            await emit()
            return False, f'Step {i + 1} failed: {state["error"]}', usage.as_dict()
        previous.append({'action': state['action'], 'outcome': state.get('reasoning') or 'done'})
    return True, None, usage.as_dict()


async def run_case(
    case: dict[str, Any],
    base_url: str,
    steps: list[dict[str, Any]],
    artifacts_dir: Path,
    artifacts_url: str,
    emit: Emit,
    live: LiveSink | None = None,
) -> tuple[bool, str | None, dict[str, int]]:
    """One case in its own browser + sandbox."""
    live = live or NullSink()
    async with browser_session() as browser:
        _, page = await new_sandbox(browser, live)
        return await run_steps(page, case, base_url, steps, artifacts_dir, artifacts_url, emit, live)
