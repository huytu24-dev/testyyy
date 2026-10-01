"""Live view of the sandboxed browser.

Chromium's DevTools protocol can stream the page as JPEG frames (Page.startScreencast).
We forward those frames, plus 'what the agent is doing now' events, to a LiveSink that the
service layer turns into WebSocket messages for the UI.
"""

import asyncio
import re
import time
import weakref
from contextlib import asynccontextmanager
from typing import Any, Protocol

from playwright.async_api import Page

MAX_FPS = 12


class LiveSink(Protocol):
    def frame(self, data_b64: str, meta: dict[str, Any]) -> None: ...
    def event(self, payload: dict[str, Any]) -> None: ...


class NullSink:
    def frame(self, data_b64: str, meta: dict[str, Any]) -> None:
        pass

    def event(self, payload: dict[str, Any]) -> None:
        pass


SCREENCAST_PARAMS = {'format': 'jpeg', 'quality': 60, 'maxWidth': 1280, 'maxHeight': 800, 'everyNthFrame': 1}
_casts: 'weakref.WeakKeyDictionary[Page, Any]' = weakref.WeakKeyDictionary()


@asynccontextmanager
async def screencast_paused(page: Page):
    """Chromium can hang Page.screenshot while a screencast is running: pause it briefly."""
    cdp = _casts.get(page)
    if cdp is None:
        yield
        return
    try:
        await cdp.send('Page.stopScreencast')
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            await cdp.send('Page.startScreencast', SCREENCAST_PARAMS)
        except Exception:
            pass


async def start_screencast(page: Page, sink: LiveSink) -> None:
    """Stream frames of `page` into `sink` until the page closes."""
    try:
        cdp = await page.context.new_cdp_session(page)
    except Exception:
        return  # non-Chromium browser: no live view, screenshots still work
    _casts[page] = cdp
    last = 0.0

    async def ack(session_id: int) -> None:
        try:
            await cdp.send('Page.screencastFrameAck', {'sessionId': session_id})
        except Exception:
            pass

    def on_frame(params: dict[str, Any]) -> None:
        nonlocal last
        asyncio.ensure_future(ack(params['sessionId']))
        now = time.monotonic()
        if now - last < 1 / MAX_FPS:
            return
        last = now
        m = params.get('metadata', {})
        sink.frame(params['data'], {'w': m.get('deviceWidth'), 'h': m.get('deviceHeight')})

    cdp.on('Page.screencastFrame', on_frame)
    page.on('framenavigated', lambda f: sink.event({'type': 'url', 'url': f.url}) if f == page.main_frame else None)
    await cdp.send('Page.startScreencast', SCREENCAST_PARAMS)


_LINE_RE = r'^\s*-\s*(\w+)(?:\s+"([^"]*)")?.*\[ref={ref}\]'


def element_label(snapshot: str, ref: str) -> str:
    """'button "Sign in"' for ref e9, from the aria snapshot line that carries the ref."""
    m = re.search(_LINE_RE.format(ref=re.escape(ref)), snapshot, re.M)
    if not m:
        return ref
    return f'{m.group(1)} "{m.group(2)}"' if m.group(2) else m.group(1)


def action_label(action: Any, snapshot: str) -> str:
    name = type(action).__name__
    ref = getattr(action, 'ref', None)
    target = f' {element_label(snapshot, ref)}' if ref else ''
    match name:
        case 'Fill':
            return f'Type "{action.value}" into{target}'
        case 'Navigate':
            return f'Open {action.url}'
        case 'ApiRequest':
            return f'{action.method} {action.url}'
        case 'PressKey':
            return f'Press {action.key}{target}'
        case 'SelectOption':
            return f'Select "{action.option}" in{target}'
        case 'Assert':
            return f'Check: {action.claim}'
        case 'Wait':
            return f'Wait {action.seconds}s'
        case 'Scroll':
            return f'Scroll {action.direction}{target}'
    return f'{name}{target}'


async def element_box(page: Page, ref: str) -> dict[str, float] | None:
    try:
        return await page.locator(f'aria-ref={ref}').bounding_box(timeout=800)
    except Exception:
        return None
