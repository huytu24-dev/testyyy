"""Action vocabulary of the planner.

Like agent-qa's tools/builder.ts: each action is its own tool (here: a Pydantic output type,
which pydantic-ai exposes to Claude as one output tool per class), and every action carries
the plan fields `reasoning` and `step_complete`.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class _Plan(BaseModel):
    reasoning: str = Field(description='Why this action, based on what you see now. One or two sentences.')
    step_complete: bool = Field(
        description='True if the CURRENT STEP will be fully done once this action succeeds.'
    )


class Click(_Plan):
    """Click an element from the accessibility tree."""
    ref: str = Field(description='Element ref from the snapshot, e.g. "e12". Never invent refs.')


class Fill(_Plan):
    """Clear a text input and type a value into it."""
    ref: str
    value: str = Field(description='Text to type. Keep {{env:NAME}} placeholders literally.')


class SelectOption(_Plan):
    """Choose an option in a <select>/combobox by its visible label."""
    ref: str
    option: str


class PressKey(_Plan):
    """Press a keyboard key (Enter, Tab, Escape, ArrowDown...), optionally focused on an element."""
    key: str
    ref: str | None = None


class Navigate(_Plan):
    """Open a URL. Relative paths ("/login") are resolved against the app base URL."""
    url: str


class Scroll(_Plan):
    """Scroll the page (or into an element) to reveal content outside the viewport."""
    direction: Literal['up', 'down'] = 'down'
    ref: str | None = Field(default=None, description='Scroll this element into view instead.')


class Hover(_Plan):
    """Move the mouse over an element (menus, tooltips)."""
    ref: str


class Wait(_Plan):
    """Wait for the page to update (loading, animations). Max 5 seconds."""
    seconds: float = Field(default=1.0, ge=0.2, le=5)


class Assert(_Plan):
    """No browser action: state that the current screen satisfies a verification step.
    Use for "Verify ..." steps when the evidence is already visible."""
    claim: str = Field(description='What you see that proves the step, quoting visible text.')


class ApiRequest(_Plan):
    """Send an HTTP request (shares the browser cookies). Relative URLs use the app base URL."""
    method: Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] = 'GET'
    url: str
    headers: dict[str, str] | None = None
    json_body: Any | None = None


class StepFailed(BaseModel):
    """Give up on the current step: the needed element/behaviour does not exist, the app shows
    an error, or the step is too ambiguous to perform."""
    reasoning: str


ACTIONS = [Click, Fill, SelectOption, PressKey, Navigate, Scroll, Hover, Wait, Assert, ApiRequest]
PlannerOutput = Click | Fill | SelectOption | PressKey | Navigate | Scroll | Hover | Wait | Assert | ApiRequest | StepFailed


def describe(action: BaseModel) -> dict[str, Any]:
    """Action as a dict for logs/UI, without the plan fields."""
    data = action.model_dump(exclude={'reasoning', 'step_complete'}, exclude_none=True)
    return {'type': type(action).__name__, **data}
