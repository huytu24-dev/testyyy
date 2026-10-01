import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

# Isolated data dir for tests; make `app` and `demo_app` importable.
os.environ.setdefault('QA_DATA_DIR', tempfile.mkdtemp(prefix='qa-test-'))
sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[2])]


@pytest.fixture(scope='session')
def demo_url():
    import uvicorn

    from demo_app.server import app

    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level='warning'))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    yield f'http://127.0.0.1:{port}'
    server.should_exit = True
