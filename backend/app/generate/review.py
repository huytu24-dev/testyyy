"""AI review of a test case before it is approved: is every step executable and verifiable?"""

from pydantic_ai import Agent

from ..config import MODEL
from .schema import CaseReview

INSTRUCTIONS = """\
You review test cases that will be executed literally by an AI browser agent. The agent sees
only the page's accessibility tree and a screenshot, does one action per step, and judges each
step against its `expected` text.

Flag, per step (0-based index):
- error: ambiguous target ("click the button"), several actions in one step, CSS selectors,
  missing test data the agent cannot know, expected outcome that is not observable.
- warning: vague expected text ("works correctly"), missing verification of the objective,
  dependency on state created by another test case.
- info: small wording improvements.
Give a concrete rewrite in `suggestion`. Use index -1 for case-level problems.
Score 10 only if every step is unambiguous and the objective is actually verified.
"""

reviewer = Agent(
    MODEL, output_type=CaseReview, instructions=INSTRUCTIONS, defer_model_check=True, retries=2
)


async def review_case(case: dict, base_url: str) -> CaseReview:
    steps = '\n'.join(
        f'{i}. action: {s.get("action", "")}\n   expected: {s.get("expected", "") or "(none)"}'
        for i, s in enumerate(case.get('steps', []))
    )
    prompt = (
        f'App URL: {base_url}\nKind: {case.get("kind")}\nTitle: {case.get("title")}\n'
        f'Objective: {case.get("objective")}\nPreconditions: {case.get("preconditions") or "-"}\n'
        f'Steps:\n{steps}'
    )
    return (await reviewer.run(prompt)).output
