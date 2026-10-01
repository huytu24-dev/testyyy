"""Execute a planned action with Playwright. Errors are returned, never raised —
the loop feeds them back to the planner (that is the 'self-healing')."""

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import Page

from .actions import (
    ApiRequest, Assert, Click, Fill, Hover, Navigate, PressKey, Scroll, SelectOption, Wait,
)

ACTION_TIMEOUT_MS = 6_000
ENV_RE = re.compile(r'\{\{env:(\w+)\}\}')


@dataclass
class ExecResult:
    ok: bool
    error: str | None = None
    data: dict[str, Any] | None = None  # e.g. API response
    secrets_used: list[str] = field(default_factory=list)


# Values of secret-looking {{env:...}} vars; the observer masks them in snapshots sent to the LLM.
SECRET_VALUES: set[str] = set()
SECRET_NAME_RE = re.compile(r'PASS|SECRET|TOKEN|KEY|PIN|OTP|CREDENTIAL', re.I)


def resolve_env(value: Any, used: list[str]) -> Any:
    """Replace {{env:NAME}} at execution time, so secret values never reach the LLM."""
    if isinstance(value, str):
        def sub(m: re.Match) -> str:
            used.append(m.group(1))
            resolved = os.getenv(m.group(1))
            if resolved is None:
                return m.group(0)
            if SECRET_NAME_RE.search(m.group(1)) and len(resolved) >= 3:
                SECRET_VALUES.add(resolved)
            return resolved
        return ENV_RE.sub(sub, value)
    if isinstance(value, dict):
        return {k: resolve_env(v, used) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env(v, used) for v in value]
    return value


def _short_error(e: Exception) -> str:
    msg = str(e).split('Call log:')[0].strip()
    return f'{e.__class__.__name__}: {msg[:400]}'


async def execute(page: Page, action: Any, base_url: str, snapshot: str | None = None) -> ExecResult:
    used: list[str] = []
    ref = getattr(action, 'ref', None)
    if ref and snapshot is not None and f'[ref={ref}]' not in snapshot:
        # Like agent-qa's action-validator: fail fast instead of waiting for a locator timeout.
        return ExecResult(ok=False, error=f'Ref "{ref}" is not in the current snapshot. Use a ref you can see.')
    loc = lambda ref: page.locator(f'aria-ref={ref}')  # noqa: E731
    try:
        match action:
            case Click():
                await loc(action.ref).click(timeout=ACTION_TIMEOUT_MS)
            case Fill():
                await loc(action.ref).fill(resolve_env(action.value, used), timeout=ACTION_TIMEOUT_MS)
            case SelectOption():
                target = loc(action.ref)
                try:
                    await target.select_option(label=action.option, timeout=ACTION_TIMEOUT_MS)
                except Exception:
                    await target.select_option(action.option, timeout=ACTION_TIMEOUT_MS)
            case PressKey():
                if action.ref:
                    await loc(action.ref).press(action.key, timeout=ACTION_TIMEOUT_MS)
                else:
                    await page.keyboard.press(action.key)
            case Navigate():
                url = urljoin(base_url.rstrip('/') + '/', resolve_env(action.url, used).lstrip('/')) \
                    if not action.url.startswith('http') else resolve_env(action.url, used)
                await page.goto(url, wait_until='domcontentloaded', timeout=20_000)
            case Scroll():
                if action.ref:
                    await loc(action.ref).scroll_into_view_if_needed(timeout=ACTION_TIMEOUT_MS)
                else:
                    await page.mouse.wheel(0, 600 if action.direction == 'down' else -600)
                    await asyncio.sleep(0.3)
            case Hover():
                await loc(action.ref).hover(timeout=ACTION_TIMEOUT_MS)
            case Wait():
                await asyncio.sleep(action.seconds)
            case Assert():
                pass
            case ApiRequest():
                url = resolve_env(action.url, used)
                if not url.startswith('http'):
                    url = urljoin(base_url.rstrip('/') + '/', url.lstrip('/'))
                kwargs: dict[str, Any] = {'method': action.method, 'timeout': 20_000}
                if action.headers:
                    kwargs['headers'] = resolve_env(action.headers, used)
                if action.json_body is not None:
                    kwargs['data'] = json.dumps(resolve_env(action.json_body, used))
                    kwargs.setdefault('headers', {})['content-type'] = 'application/json'
                resp = await page.request.fetch(url, **kwargs)
                body = await resp.text()
                return ExecResult(
                    ok=True,
                    data={'status': resp.status, 'url': url, 'body': body[:3000]},
                    secrets_used=used,
                )
            case _:
                return ExecResult(ok=False, error=f'Unknown action {type(action).__name__}')
    except Exception as e:
        return ExecResult(ok=False, error=_short_error(e), secrets_used=used)
    return ExecResult(ok=True, secrets_used=used)
