"""Adapter for TestTeller (https://github.com/iAviPro/testteller-agent).

TestTeller is a CLI: ingest-docs -> ingest-code -> generate (markdown). We run it as a
subprocess, then parse its markdown into GeneratedCase objects with `parse_spec`.

Needs: `pip install testteller` (Python >= 3.11) in this venv or on PATH, `testteller configure`
done once, and an embedding provider key (OpenAI or Gemini) because Claude has no embeddings.
"""

import asyncio
import re
import shutil
import sys
from pathlib import Path

from .schema import GeneratedCase, GeneratedStep, GeneratedSuite


def testteller_bin() -> str | None:
    venv_bin = Path(sys.executable).parent / 'testteller'
    return str(venv_bin) if venv_bin.exists() else shutil.which('testteller')


async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    out, _ = await proc.communicate()
    text = out.decode(errors='replace')
    if proc.returncode != 0:
        raise RuntimeError(f'{" ".join(args[:2])} failed:\n{text[-2000:]}')
    return text


async def generate_with_testteller(
    requirements_file: str | None, repo_dir: Path | None, out_file: Path, collection: str
) -> GeneratedSuite:
    exe = testteller_bin()
    if not exe:
        raise RuntimeError(
            'testteller is not installed. Run `.venv/bin/pip install testteller` '
            '(Python >= 3.11) and `testteller configure`, or use the builtin generator.'
        )
    c = ['-c', collection]
    if requirements_file:
        await _run(exe, 'ingest-docs', requirements_file, *c)
    if repo_dir:
        await _run(exe, 'ingest-code', str(repo_dir), *c)
    await _run(
        exe, 'generate', 'End-to-end UI journeys and API integration tests for the application',
        *c, '-f', 'md', '-o', str(out_file),
    )
    return parse_spec(out_file.read_text())


# --- TestTeller markdown parser -------------------------------------------------------
# Format (from testteller/generator_agent/prompts.py):
#   ### Test Case E2E_1
#   **Feature:** User Login Flow
#   **Type:** Journey/Flow
#   **Category:** Happy Path
#   #### Objective
#   ...
#   #### Prerequisites & Setup
#   - **System State:** ...
#   #### Test Steps
#   1. **Action:** Navigate to login page and enter credentials
#      - **Technical Details:** Form submission to `/api/v1/auth/login`
#   2. **Validation:** Success message displayed
#   #### Expected Final State
#   - **UI/Frontend:** ...

CASE_RE = re.compile(r'^###\s+Test Case\s+([A-Za-z0-9]+_\d+)\s*$', re.M)
SECTION_RE = re.compile(r'^####\s+(.+?)\s*$', re.M)
FIELD_RE = re.compile(r'^\*\*(.+?):\*\*\s*(.+)$', re.M)
STEP_RE = re.compile(r'^\s*\d+\.\s+\*\*(Action|Validation):\*\*\s*(.+)$', re.M)
ENDPOINT_RE = re.compile(r'\b(GET|POST|PUT|PATCH|DELETE)\b\s+`?(/[^\s`]+)', re.I)


def _sections(body: str) -> dict[str, str]:
    parts = SECTION_RE.split(body)
    return {parts[i].strip().lower(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def parse_spec(md: str) -> GeneratedSuite:
    cases: list[GeneratedCase] = []
    chunks = CASE_RE.split(md)
    for i in range(1, len(chunks) - 1, 2):
        key, body = chunks[i].strip(), chunks[i + 1]
        head = SECTION_RE.split(body)[0]
        fields = {k.strip().lower(): v.strip() for k, v in FIELD_RE.findall(head)}
        sec = _sections(body)

        steps: list[GeneratedStep] = []
        for kind, text in STEP_RE.findall(sec.get('test steps', '')):
            text = text.strip()
            if kind == 'Action' or not steps:
                steps.append(GeneratedStep(action=text))
            elif steps[-1].expected:
                steps.append(GeneratedStep(action=f'Verify {text[0].lower()}{text[1:]}'))
            else:
                steps[-1].expected = text
        if not steps:
            continue

        prefix = key.split('_')[0].upper()
        technical = sec.get('test steps', '')
        is_api = prefix in {'INT', 'INTEGRATION', 'API'} and bool(ENDPOINT_RE.search(technical))
        if prefix not in {'E2E'} and not is_api:
            continue  # technical / mocked tests are not executable by the browser agent

        feature = fields.get('feature') or fields.get('integration') or fields.get('technical area') or key
        cases.append(GeneratedCase(
            key=key,
            title=feature,
            kind='api' if is_api else 'ui',
            category=fields.get('category', ''),
            objective=sec.get('objective', '').split('\n')[0],
            preconditions=sec.get('prerequisites & setup', ''),
            steps=steps,
        ))
    return GeneratedSuite(cases=cases)
