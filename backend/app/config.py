import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')

DATA_DIR = Path(os.getenv('QA_DATA_DIR', ROOT / 'data'))
UPLOADS_DIR = DATA_DIR / 'uploads'
REPOS_DIR = DATA_DIR / 'repos'
RUNS_DIR = DATA_DIR / 'runs'
for d in (UPLOADS_DIR, REPOS_DIR, RUNS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Browsers are installed inside the project (see README).
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT / '.browsers'))
os.environ.setdefault('PYDANTIC_AI_NO_BANNER', '1')

# LLM provider: "openai" or "anthropic". Any pydantic-ai model string works in QA_MODEL /
# QA_VERIFIER_MODEL (e.g. "openai:gpt-5.5"); the provider defaults only pick sensible pairs.
PROVIDER_DEFAULTS = {
    'openai': ('openai:gpt-5.5', 'openai:gpt-5.4-mini', 'OPENAI_API_KEY'),
    'anthropic': ('anthropic:claude-sonnet-5-5', 'anthropic:claude-haiku-4-5-20251001', 'ANTHROPIC_API_KEY'),
}
PROVIDER = os.getenv('QA_PROVIDER', 'openai').lower()
if PROVIDER not in PROVIDER_DEFAULTS:
    raise ValueError(f'QA_PROVIDER must be one of {list(PROVIDER_DEFAULTS)}, got {PROVIDER!r}')
_default_model, _default_verifier, _ = PROVIDER_DEFAULTS[PROVIDER]
MODEL = os.getenv('QA_MODEL', _default_model)
VERIFIER_MODEL = os.getenv('QA_VERIFIER_MODEL', _default_verifier)

HEADLESS = os.getenv('QA_HEADLESS', 'true').lower() != 'false'
MAX_SUB_ACTIONS = int(os.getenv('QA_MAX_SUB_ACTIONS', '8'))
MAX_ATTEMPTS = int(os.getenv('QA_MAX_ATTEMPTS', '3'))
PREVIOUS_STEP_COUNT = 3
STEP_TIMEOUT_S = float(os.getenv('QA_STEP_TIMEOUT_S', '120'))
MAX_CONCURRENT_RUNS = int(os.getenv('QA_MAX_CONCURRENT_RUNS', '2'))
VIEWPORT = {'width': 1280, 'height': 800}


def required_keys() -> list[str]:
    """Env vars needed by the configured models (planner and verifier may use different providers)."""
    keys = []
    for model in (MODEL, VERIFIER_MODEL):
        provider = model.split(':', 1)[0]
        key = PROVIDER_DEFAULTS.get(provider, (None, None, None))[2]
        if key and key not in keys:
            keys.append(key)
    return keys


def missing_keys() -> list[str]:
    return [k for k in required_keys() if not os.getenv(k)]


def has_api_key() -> bool:
    return not missing_keys()


def missing_key_message() -> str:
    return f'{", ".join(missing_keys())} is not set in .env'
