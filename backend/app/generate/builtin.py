"""Built-in generator: plays the role of TestTeller's `generate`, using Claude directly.

Output has the same shape TestTeller produces (objective, prerequisites, steps with
action + validation), but is returned as structured data instead of markdown.
"""

from pydantic_ai import Agent

from ..config import MODEL
from .schema import GeneratedSuite

INSTRUCTIONS = """\
You are a senior QA engineer. From product requirements and a code-repository summary,
design test cases that an AI browser agent will execute against the running app.

Rules for cases:
- Cover every requirement with at least one case; prefer the acceptance criteria.
- Mix Happy Path, Negative and Edge Case. Most important flows are P1.
- kind="ui" for user journeys through the web UI; kind="api" for HTTP endpoint checks.
- requirement_refs lists the requirement ids the case covers.

Rules for steps (they are executed literally, one at a time, by an agent that sees the
page's accessibility tree and a screenshot):
- One user action per step: "Open the login page", "Fill the Email field with ...",
  "Click the \"Sign in\" button". Refer to elements by their visible label or role,
  never by CSS selectors or ids.
- The first UI step should open the relevant page (relative path such as "/login" is fine).
- `expected` describes what is visible on screen (or in the API response) after the step.
  Leave it empty for pure input steps. Put verification-only checks in their own step,
  starting with "Verify ...".
- Use only test data stated in the requirements or the repo. For credentials or secrets
  write placeholders like {{env:TEST_USER}} and {{env:TEST_PASSWORD}}.
- API steps: "Send GET /api/todos" / "Send POST /api/todos with JSON {\"title\": \"Milk\"}";
  expected: status code and key fields of the JSON body.
- Keep cases independent: each case starts from a fresh browser with no session.
"""

generator = Agent(
    MODEL, output_type=GeneratedSuite, instructions=INSTRUCTIONS, defer_model_check=True, retries=2
)


def _format_requirements(reqs: list[dict]) -> str:
    lines = []
    for r in reqs:
        line = f'- [{r["ref"]}]'
        if r.get('feature'):
            line += f' ({r["feature"]})'
        line += f' {r["text"]}'
        if r.get('acceptance'):
            line += f'\n  Acceptance: {r["acceptance"]}'
        if r.get('priority'):
            line += f'\n  Priority: {r["priority"]}'
        lines.append(line)
    return '\n'.join(lines)


async def generate_cases(
    requirements: list[dict], repo_context: str, base_url: str, max_cases: int
) -> GeneratedSuite:
    prompt = (
        f'App under test is running at: {base_url}\n'
        f'Generate at most {max_cases} test cases.\n\n'
        f'# Requirements\n{_format_requirements(requirements) or "(none provided)"}\n\n'
        f'# Repository summary\n{repo_context or "(no repository provided)"}'
    )
    result = await generator.run(prompt)
    suite = result.output
    suite.cases = suite.cases[:max_cases]
    return suite
