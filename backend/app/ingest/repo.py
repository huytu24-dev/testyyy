"""Turn a GitHub repo (or local folder) into a compact text context for the generator.

This is "RAG-lite": no vector DB, just the parts of a repo that tell you what the UI and
API look like (routes, visible strings, README), capped to a character budget.
"""

import asyncio
import hashlib
import re
from pathlib import Path

from ..config import REPOS_DIR

SKIP_DIRS = {
    'node_modules', '.git', 'dist', 'build', '.next', '.venv', 'venv', '__pycache__',
    'coverage', '.turbo', '.cache', 'vendor', 'target', '.idea', '.vscode',
}
CODE_EXT = {'.py', '.js', '.jsx', '.ts', '.tsx', '.vue', '.svelte', '.html', '.go', '.java', '.rb', '.php'}
UI_EXT = {'.jsx', '.tsx', '.vue', '.svelte', '.html', '.jinja', '.j2'}

ROUTE_RE = re.compile(
    r"""(@(app|router|bp|api)\.(get|post|put|patch|delete|route)\(\s*['"][^'"]+['"]"""
    r"""|\b(app|router)\.(get|post|put|patch|delete|use)\(\s*['"][^'"]+['"]"""
    r"""|path\(\s*['"][^'"]*['"]"""
    r"""|<Route[^>]*path=['"][^'"]+['"]"""
    r"""|\bpath:\s*['"][^'"]+['"])""",
    re.I,
)
UI_TEXT_RE = re.compile(
    r""">\s*([A-Za-zÀ-ỹ][^<>{}\n]{1,60}?)\s*<"""
    r"""|(?:placeholder|aria-label|label|title|alt)=['"]([^'"]{2,60})['"]"""
)


async def fetch_repo(repo: str) -> Path:
    """Clone a git URL (shallow) or return a local directory."""
    local = Path(repo).expanduser()
    if local.is_dir():
        return local.resolve()
    dest = REPOS_DIR / hashlib.sha1(repo.encode()).hexdigest()[:12]
    if (dest / '.git').exists():
        proc = await asyncio.create_subprocess_exec(
            'git', '-C', str(dest), 'pull', '--ff-only', '-q',
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return dest
    proc = await asyncio.create_subprocess_exec(
        'git', 'clone', '--depth', '1', '-q', repo, str(dest),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f'git clone failed: {err.decode(errors="replace").strip()}')
    return dest


def _walk(root: Path):
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS or part.startswith('.') and part not in {'.github'} for part in rel.parts):
            continue
        if p.is_file() and p.stat().st_size < 400_000:
            yield p, rel


def build_context(root: Path, budget: int = 60_000) -> str:
    files = list(_walk(root))
    sections: list[str] = []

    tree = '\n'.join(str(rel) for _, rel in files[:400])
    sections.append(f'## File tree\n{tree}')

    for name in ('README.md', 'readme.md', 'README.rst', 'README'):
        if (root / name).exists():
            sections.append(f'## README\n{(root / name).read_text(errors="replace")[:6000]}')
            break

    for name in ('package.json', 'pyproject.toml', 'requirements.txt'):
        if (root / name).exists():
            sections.append(f'## {name}\n{(root / name).read_text(errors="replace")[:2500]}')

    for p, rel in files:
        name = p.name.lower()
        if p.suffix in {'.yaml', '.yml', '.json'} and ('openapi' in name or 'swagger' in name):
            sections.append(f'## API spec {rel}\n{p.read_text(errors="replace")[:12000]}')

    routes: list[str] = []
    ui_text: dict[str, set[str]] = {}
    for p, rel in files:
        if p.suffix not in CODE_EXT and p.suffix not in UI_EXT:
            continue
        try:
            src = p.read_text(errors='replace')
        except OSError:
            continue
        for line in src.splitlines():
            if ROUTE_RE.search(line):
                routes.append(f'{rel}: {line.strip()[:160]}')
        if p.suffix in UI_EXT or p.suffix == '.py':
            found = {(a or b).strip() for a, b in UI_TEXT_RE.findall(src)}
            found = {t for t in found if len(t) > 1 and not t.startswith(('http', '/', '.', '#'))}
            if found:
                ui_text[str(rel)] = found

    if routes:
        sections.append('## Routes / endpoints\n' + '\n'.join(routes[:300]))
    if ui_text:
        lines = [f'{f}: ' + ' | '.join(sorted(t)[:40]) for f, t in ui_text.items()]
        sections.append('## Visible UI text (labels, buttons, headings)\n' + '\n'.join(lines[:150]))

    out = '\n\n'.join(sections)
    return out[:budget]
