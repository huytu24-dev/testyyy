"""Tests that need no API key and no browser."""

from pathlib import Path

from app.generate.testteller import parse_spec
from app.ingest.excel import parse_requirements
from app.ingest.repo import build_context

ROOT = Path(__file__).resolve().parents[2]

TESTTELLER_MD = """
## Summary
| S.No | Test ID | Feature | Category | Objective | Priority |

### Test Case E2E_1
**Feature:** User Login Flow
**Type:** Journey/Flow
**Category:** Happy Path

#### Objective
Verify successful user authentication through complete login process.

#### Prerequisites & Setup
- **System State:** User registration completed
- **Test Data:** `user_id: 123`, `password: SecurePass123`

#### Test Steps
1. **Action:** Navigate to login page and enter credentials
   - **Technical Details:** Form submission to `/api/v1/auth/login`
2. **Validation:** Success message displayed
   - **Technical Details:** Expect 200 OK, JWT token returned
3. **Validation:** Dashboard shows the user name

#### Expected Final State
- **UI/Frontend:** Dashboard loads with user profile visible

### Test Case INT_1
**Integration:** Todo API
**Type:** API
**Category:** Negative

#### Objective
Unauthenticated access is rejected.

#### Test Steps
1. **Action:** Call the todo list endpoint without a session
   - **Technical Details:** GET `/api/todos`
2. **Validation:** 401 returned

### Test Case TECH_1
**Technical Area:** Performance
#### Test Steps
1. **Action:** Load test
"""


def test_parse_testteller_markdown():
    suite = parse_spec(TESTTELLER_MD)
    assert [c.key for c in suite.cases] == ['E2E_1', 'INT_1']  # TECH_* is not executable
    e2e, api = suite.cases
    assert e2e.kind == 'ui' and e2e.category == 'Happy Path'
    assert e2e.title == 'User Login Flow'
    assert e2e.steps[0].action.startswith('Navigate to login page')
    assert e2e.steps[0].expected == 'Success message displayed'
    assert e2e.steps[1].action == 'Verify dashboard shows the user name'
    assert api.kind == 'api' and api.steps[0].expected == '401 returned'


def test_excel_requirements_sample():
    reqs = parse_requirements(ROOT / 'fixtures' / 'requirements.sample.xlsx')
    assert len(reqs) == 7
    assert reqs[0]['ref'] == 'REQ-01'
    assert reqs[0]['feature'] == 'Login'
    assert 'My todos' in reqs[0]['acceptance']
    assert reqs[0]['priority'] == 'High'


def test_excel_vietnamese_headers_are_recognised(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(['Mã', 'Chức năng', 'Mô tả', 'Tiêu chí chấp nhận', 'Độ ưu tiên'])
    wb.active.append(['R1', 'Login', 'Sign in', 'Shows the dashboard', 'High'])
    wb.save(tmp_path / 'vi.xlsx')
    [req] = parse_requirements(tmp_path / 'vi.xlsx')
    assert req == {'ref': 'R1', 'feature': 'Login', 'text': 'Sign in', 'acceptance': 'Shows the dashboard', 'priority': 'High'}


def test_repo_context_finds_routes_and_labels():
    ctx = build_context(ROOT / 'demo_app')
    assert "@app.post('/api/login')" in ctx
    assert 'Sign in' in ctx and 'New todo' in ctx
