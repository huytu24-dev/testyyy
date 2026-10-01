"""Verifier: separate, cheaper LLM call that checks a step the planner claims is complete.

Mirrors agent-qa core/src/agent/verifier.ts: output {success, reasoning, is_app_error}.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent

from ..config import VERIFIER_MODEL
from .observer import Observation

INSTRUCTIONS = """\
You verify one step of an automated UI/API test. You get the step, its expected outcome,
the actions the agent took, the screen BEFORE and AFTER (accessibility tree), and a screenshot
of the AFTER state.

- For action steps (click, fill, open...): success if the action plausibly happened and nothing
  contradicts it. No visible change is NOT a failure by itself for input steps.
- For steps with an expected outcome or "Verify ..." steps: require POSITIVE evidence in the
  AFTER state (or the API response) matching the expectation. Quote it in reasoning.
- is_app_error=true only when the application itself is broken (error page, 5xx, crash,
  wrong behaviour that retrying cannot fix). Then success=false.
Be strict but fair; keep reasoning to 1-3 sentences.
"""


class Verdict(BaseModel):
    success: bool
    reasoning: str
    is_app_error: bool = Field(default=False)


verifier = Agent(
    VERIFIER_MODEL, output_type=Verdict, instructions=INSTRUCTIONS, defer_model_check=True, retries=2
)


async def verify(step: str, expected: str, actions_text: str, before: Observation, after: Observation):
    prompt = (
        f'STEP: "{step}"\nEXPECTED: "{expected or "(not specified — the action must have happened)"}"\n\n'
        f'ACTIONS TAKEN:\n{actions_text}\n\n'
        f'--- BEFORE ---\n{before.as_text()[:6000]}\n\n--- AFTER ---\n{after.as_text()}'
    )
    result = await verifier.run([prompt, BinaryContent(data=after.screenshot, media_type='image/jpeg')])
    return result.output, result.usage
