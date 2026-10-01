"""Tiny app under test: login + todo list + JSON API.

Run: backend/.venv/bin/uvicorn demo_app.server:app --port 8001
Login: demo@example.com / demo1234
"""

import secrets

from fastapi import Cookie, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

app = FastAPI(title='Demo Todo App')

USERS = {'demo@example.com': 'demo1234'}
SESSIONS: dict[str, str] = {}
TODOS: dict[str, list[dict]] = {}
_next_id = 1

PAGE = """<!doctype html><html><head><meta charset=utf-8><title>{title}</title>
<style>body{{font-family:system-ui;max-width:520px;margin:48px auto;padding:0 16px}}
label{{display:block;margin:12px 0 4px}} input{{padding:8px;width:100%;box-sizing:border-box}}
button{{margin-top:12px;padding:8px 16px;cursor:pointer}} .err{{color:#b00020}}
li{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #eee}}
li button{{margin:0}} nav{{display:flex;justify-content:space-between;align-items:center}}</style>
</head><body>{body}</body></html>"""

LOGIN = """<h1>Sign in to Todo</h1>
<form id=f>
  <label for=email>Email</label><input id=email name=email type=email autocomplete=username>
  <label for=password>Password</label><input id=password name=password type=password>
  <button type=submit>Sign in</button>
  <p id=error class=err role=alert></p>
</form>
<script>
document.getElementById('f').onsubmit = async (e) => {
  e.preventDefault();
  const r = await fetch('/api/login', {method:'POST', headers:{'content-type':'application/json'},
    body: JSON.stringify({email: email.value, password: password.value})});
  if (r.ok) location.href = '/todos';
  else document.getElementById('error').textContent = 'Invalid email or password';
};
</script>"""

TODOS_PAGE = """<nav><h1>My todos</h1><a href=/logout>Log out</a></nav>
<p>Signed in as <strong>{email}</strong></p>
<form id=add>
  <label for=title>New todo</label><input id=title maxlength=100>
  <button type=submit>Add</button>
  <p id=error class=err role=alert></p>
</form>
<p id=empty>No todos yet</p>
<ul id=list aria-label="Todo list"></ul>
<script>
async function load() {
  const items = await (await fetch('/api/todos')).json();
  const list = document.getElementById('list'); list.innerHTML = '';
  document.getElementById('empty').hidden = items.length > 0;
  for (const t of items) {
    const li = document.createElement('li');
    const span = document.createElement('span'); span.textContent = t.title;
    const del = document.createElement('button'); del.textContent = 'Delete';
    del.setAttribute('aria-label', 'Delete ' + t.title);
    del.onclick = async () => { await fetch('/api/todos/' + t.id, {method:'DELETE'}); load(); };
    li.append(span, del); list.append(li);
  }
}
document.getElementById('add').onsubmit = async (e) => {
  e.preventDefault();
  const err = document.getElementById('error'); err.textContent = '';
  const r = await fetch('/api/todos', {method:'POST', headers:{'content-type':'application/json'},
    body: JSON.stringify({title: title.value})});
  if (!r.ok) { err.textContent = (await r.json()).detail; return; }
  title.value = ''; load();
};
load();
</script>"""


def _user(sid: str | None) -> str | None:
    return SESSIONS.get(sid or '')


@app.get('/')
def root():
    return RedirectResponse('/login')


@app.get('/login', response_class=HTMLResponse)
def login_page():
    return PAGE.format(title='Sign in', body=LOGIN)


@app.get('/todos', response_class=HTMLResponse)
def todos_page(sid: str | None = Cookie(None)):
    email = _user(sid)
    if not email:
        return RedirectResponse('/login')
    return PAGE.format(title='My todos', body=TODOS_PAGE.replace('{email}', email))


@app.get('/logout')
def logout(sid: str | None = Cookie(None)):
    SESSIONS.pop(sid or '', None)
    r = RedirectResponse('/login')
    r.delete_cookie('sid')
    return r


class LoginIn(BaseModel):
    email: str
    password: str


@app.post('/api/login')
def api_login(body: LoginIn, response: Response):
    if USERS.get(body.email) != body.password:
        raise HTTPException(401, 'Invalid email or password')
    sid = secrets.token_hex(16)
    SESSIONS[sid] = body.email
    response.set_cookie('sid', sid, httponly=True)
    return {'email': body.email}


def _require(sid: str | None) -> str:
    email = _user(sid)
    if not email:
        raise HTTPException(401, 'Not authenticated')
    return email


class TodoIn(BaseModel):
    title: str


@app.get('/api/todos')
def list_todos(sid: str | None = Cookie(None)):
    return TODOS.get(_require(sid), [])


@app.post('/api/todos', status_code=201)
def add_todo(body: TodoIn, sid: str | None = Cookie(None)):
    global _next_id
    email = _require(sid)
    title = body.title.strip()
    if not title:
        raise HTTPException(422, 'Title is required')
    if len(title) > 100:
        raise HTTPException(422, 'Title must be at most 100 characters')
    todo = {'id': _next_id, 'title': title}
    _next_id += 1
    TODOS.setdefault(email, []).append(todo)
    return todo


@app.delete('/api/todos/{todo_id}', status_code=204)
def delete_todo(todo_id: int, sid: str | None = Cookie(None)):
    email = _require(sid)
    items = TODOS.get(email, [])
    if not any(t['id'] == todo_id for t in items):
        raise HTTPException(404, 'Todo not found')
    TODOS[email] = [t for t in items if t['id'] != todo_id]
    return Response(status_code=204)
