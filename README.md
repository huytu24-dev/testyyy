# Mini QA Agent

A full-stack app for learning how to build a QA agent: **Excel requirements + GitHub repo → generated test cases → review/approve in the UI → an AI agent runs them in a real browser, with every step visible live.**

It combines ideas from two projects:
- [TestTeller](https://github.com/iAviPro/testteller-agent): generates test cases from docs + code. This app has a builtin (LLM) generator producing the same structure, plus an adapter that calls the real TestTeller.
- [agent-qa](https://github.com/vostride/agent-qa): an agent that runs natural-language tests and self-heals. The agent loop is re-implemented in Python following their architecture.

## Run

Requirements: Python ≥ 3.11, Node ≥ 20, git.

```bash
# 1. Backend
cd backend
python3.14 -m venv .venv            # or python3.11+
.venv/bin/pip install -r requirements.txt
PLAYWRIGHT_BROWSERS_PATH=../.browsers .venv/bin/playwright install chromium

# 2. Frontend
cd ../frontend && npm install

# 3. Keys: copy the template and fill in OPENAI_API_KEY
cd .. && cp env.example .env
```

Open 3 terminals in the repo root:

```bash
backend/.venv/bin/uvicorn --app-dir backend app.main:app --port 8000   # API
backend/.venv/bin/uvicorn demo_app.server:app --port 8001              # sample app under test
npm --prefix frontend run dev                                          # UI: http://localhost:5173
```

Quick demo: create a project with App URL `http://localhost:8001`, repo = path to the `demo_app` folder
(or a GitHub URL), Excel = `fixtures/requirements.sample.xlsx`. Then: **Generate** → open a case → **AI review** → **Approve** → select cases → **Chain into flow** → **Run flow in sandbox**.

**Try the sandbox without an API key:** run the dev server, where the real LLM is replaced by a scripted fake. The fake planner deliberately picks a wrong element once so you can see self-healing. Use this instead of the API command above:

```bash
backend/.venv/bin/python backend/tests/scripted_server.py
```

The fake planner only understands steps like `Fill the X field with Y`, `Click the "X" button`, `Verify "X" ...`, `Send GET /path`. Generate and AI review need a real LLM.

## Flow

```
Excel ─┐                                  ┌───────────── UI (React + Mantine) ─────────────┐
       ├─ ingest ─ generate ─ TestCase ── review / approve ── Flow (case → case → case) ── sandbox run
Repo ──┘                       (draft)                                                       │
                                            Playwright browser ── CDP screencast ── WebSocket ┘
                                            agent loop: observe → plan → act → verify
```

**Sandbox:** each case runs in its own BrowserContext (isolated cookies and storage). In a flow with *shared session* enabled, cases share one context, so each case continues from the state the previous one left (e.g. log in once). The headless browser is streamed via `Page.startScreencast` at up to 12 fps. The UI draws on top of it: the URL bar, a purple box around the element the agent is about to use, the current phase (Observing / Thinking / Acting / Verifying), and the verifier's verdict. A **Stop** button cancels the run.

| Folder | Contents |
|---|---|
| `backend/app/ingest/` | `excel.py`: flexible column matching (English and Vietnamese headers). `repo.py`: `--depth 1` clone, extracts routes, UI text, README ("RAG-lite", no vector DB) |
| `backend/app/generate/` | `builtin.py`: LLM generates structured cases. `testteller.py`: TestTeller CLI + markdown parser. `review.py`: AI scores each step |
| `backend/app/agent/` | The core, see below. `live.py`: screencast + action labels + bounding boxes |
| `backend/app/services.py` | Background jobs (generate, run, flow, cancel). Pub/sub for the `run:`, `flow:`, `live:run:`, `live:flow:` channels |
| `backend/app/main.py` | REST API + WebSockets: `/api/runs/{id}/ws`, `/api/flow-runs/{id}/ws` (state), `/api/live/{run\|flow}/{id}` (frames) |
| `frontend/src/` | Mantine (dark), TanStack React Query (WebSockets write straight into the query cache), React Flow (flow graph) |
| `frontend/src/components/` | `LiveBrowser` (sandbox window), `FlowGraph`, `StepTimeline`, `RunSandbox` |
| `frontend/src/pages/` | Projects, Project, Case editor, Flow builder, Run, Flow run |
| `demo_app/` | Small todo app (login + todos + JSON API) to test against |

## Agent vs. agent-qa

| File | agent-qa equivalent | What it does |
|---|---|---|
| `observer.py` | `web/src/observer.ts` | `aria_snapshot(mode="ai")` → accessibility tree with `[ref=eN]` + JPEG screenshot. Masks password field values and secret-looking `{{env:*PASS*/TOKEN/KEY…}}` values, because the snapshot includes input values |
| `actions.py` | `core/src/tools/` | Each action is a Pydantic model, i.e. one tool for the LLM. Every action carries `reasoning` and `step_complete` |
| `planner.py` | `core/src/agent/planner.ts`, `prompts.ts` | One LLM call per sub-action. The prompt has: previous steps, actions already tried (✓/✗, "screen did NOT change"), the last error, the current step, the screen |
| `executor.py` | `web/src/adapter.ts` | Executes via `aria-ref=eN`. Checks the ref exists in the snapshot first. `{{env:X}}` is substituted only at execution time, so secrets never reach the LLM |
| `loop.py` | `core/src/agent/loop.ts` | Up to 8 turns per step. A failed action is fed back into the prompt and re-planned (self-heal). 3 consecutive failures fail the step |
| `verifier.py` | `core/src/agent/verifier.ts` | A separate call to a cheaper model, returns `{success, reasoning, is_app_error}`. If the verifier rejects, the planner must try something else |
| `runner.py` | `core/src/agent/runner.ts` | Each case runs in a fresh browser context. Stops at the first failed step |

Not implemented yet (agent-qa has them): action cache, memory/curator, Docker hooks, mobile, suites.

## Real TestTeller

Needs Python ≥ 3.11. With OpenAI, one `OPENAI_API_KEY` covers both the LLM and TestTeller's embeddings:

```bash
backend/.venv/bin/pip install testteller
backend/.venv/bin/testteller configure
```

Then pick **TestTeller** in the generator switch. Its markdown output is turned into test cases by `parse_spec()`: `E2E_*` become UI cases, `INT_*` with an endpoint become API cases, other types are skipped.

## Config (environment variables)

| Variable | Default |
|---|---|
| `QA_PROVIDER` | `openai` (or `anthropic`) |
| `QA_MODEL` | `openai:gpt-5.5` (planner, generator, review) |
| `QA_VERIFIER_MODEL` | `openai:gpt-5.4-mini` |
| `QA_HEADLESS` | `true` (`false` to also show a browser window) |
| `QA_MAX_SUB_ACTIONS` / `QA_MAX_ATTEMPTS` | `8` / `3` |
| `QA_MAX_CONCURRENT_RUNS` | `2` |

## Tests

```bash
cd backend && .venv/bin/pytest tests -q
```

`test_agent_loop.py` and `test_flow.py` run the real agent loop in Chromium against the demo app with a scripted LLM (`FunctionModel`). They cover self-healing, the verifier, API requests, flows with shared/isolated sessions, live frames, and secret masking, without spending tokens.
