"""Create fixtures/requirements.sample.xlsx for the demo app."""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

ROWS = [
    ('REQ-01', 'Login', 'Users sign in with email and password.',
     'Valid login (demo@example.com / demo1234) opens the "My todos" page and shows the user email.', 'High'),
    ('REQ-02', 'Login', 'Reject sign-in with a wrong password.',
     'Shows the message "Invalid email or password" and stays on the sign-in page.', 'High'),
    ('REQ-03', 'Todos', 'Users can add a new todo.',
     'Typing a title and clicking Add shows the todo in the list and clears the input.', 'High'),
    ('REQ-04', 'Todos', 'Empty todos are not allowed.',
     'Clicking Add with an empty input shows "Title is required" and the list does not change.', 'Medium'),
    ('REQ-05', 'Todos', 'Users can delete a todo.',
     'Clicking Delete next to a todo removes it from the list.', 'Medium'),
    ('REQ-06', 'API', 'The /api/todos API requires authentication.',
     'GET /api/todos without a session returns 401. After a valid POST /api/login, GET returns 200 and a JSON array.', 'High'),
    ('REQ-07', 'Logout', 'Users can log out.',
     'Clicking "Log out" returns to the sign-in page; opening /todos again redirects to sign-in.', 'Low'),
]

wb = Workbook()
ws = wb.active
ws.title = 'Requirements'
ws.append(['ID', 'Feature', 'Requirement', 'Acceptance Criteria', 'Priority'])
for c in ws[1]:
    c.font = Font(bold=True)
for r in ROWS:
    ws.append(r)
for col, w in zip('ABCDE', (10, 12, 45, 80, 12)):
    ws.column_dimensions[col].width = w

out = Path(__file__).parent / 'requirements.sample.xlsx'
wb.save(out)
print(out)
