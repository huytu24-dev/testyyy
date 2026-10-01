"""What the agent 'sees': accessibility snapshot with refs + screenshot.

agent-qa (web/src/observer.ts) calls ariaSnapshot() and tags interactive nodes with
[ref=eN] itself. Playwright >= 1.55 does that for us with mode="ai", and the refs resolve
with the `aria-ref=eN` selector.
"""

import asyncio
import hashlib
import re
from dataclasses import dataclass

from playwright.async_api import Page

from .live import screencast_paused

MAX_SNAPSHOT_CHARS = 14_000
REF_RE = re.compile(r'\s*\[ref=\w+\]')


@dataclass
class Observation:
    url: str
    title: str
    snapshot: str
    screenshot: bytes

    @property
    def screen_hash(self) -> str:
        # Refs can be renumbered between snapshots; compare structure + text only.
        return hashlib.sha1(REF_RE.sub('', self.snapshot).encode()).hexdigest()

    def as_text(self) -> str:
        snap = self.snapshot
        if len(snap) > MAX_SNAPSHOT_CHARS:
            snap = snap[:MAX_SNAPSHOT_CHARS] + '\n... (snapshot truncated; scroll to see more)'
        return f'Current page: {self.url}\nTitle: {self.title}\n\n{snap}'


async def wait_for_ready(page: Page) -> None:
    """Rough equivalent of agent-qa's smart-wait: DOM loaded, network quiet (best effort)."""
    try:
        await page.wait_for_load_state('domcontentloaded', timeout=5_000)
        await page.wait_for_load_state('networkidle', timeout=3_000)
    except Exception:
        pass


PASSWORD_VALUE_RE = re.compile(r'^(\s*- textbox "[^"]*(?:password|mật khẩu|pin)[^"]*".*?:\s).+$', re.I | re.M)


def redact(snapshot: str) -> str:
    """The AI snapshot includes input values. Never let secrets reach the LLM."""
    from .executor import SECRET_VALUES

    snapshot = PASSWORD_VALUE_RE.sub(r'\1••••••', snapshot)
    for value in sorted(SECRET_VALUES, key=len, reverse=True):
        snapshot = snapshot.replace(value, '••••••')
    return snapshot


async def _screenshot(page: Page, attempts: int = 4) -> bytes:
    for i in range(attempts):
        try:
            async with screencast_paused(page):
                return await page.screenshot(type='jpeg', quality=60, timeout=10_000)
        except Exception:
            # Chromium sometimes refuses right after the screencast stops; retry shortly.
            if i == attempts - 1:
                raise
            await asyncio.sleep(0.15 * (i + 1))
    raise AssertionError('unreachable')


async def observe(page: Page) -> Observation:
    await wait_for_ready(page)
    try:
        snapshot = redact(await page.locator(':root').aria_snapshot(mode='ai', timeout=5_000))
    except Exception as e:  # about:blank, navigation in progress...
        snapshot = f'(no accessibility snapshot: {e.__class__.__name__})'
    screenshot = await _screenshot(page)
    try:
        title = await page.title()
    except Exception:
        title = ''
    return Observation(url=page.url, title=title, snapshot=snapshot, screenshot=screenshot)
