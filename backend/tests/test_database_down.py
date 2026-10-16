"""If the database is unreachable at boot, the app still starts, answers 503
(not a crash or a generic 500), and keeps /health green."""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

SCRIPT = textwrap.dedent("""
    from fastapi.testclient import TestClient
    import app.main as m
    c = TestClient(m.app, raise_server_exceptions=False)
    print("HEALTH", c.get("/health").status_code)
    r = c.post("/auth/login", json={"email": "a@b.co", "password": "x"})
    print("LOGIN", r.status_code, r.headers.get("retry-after"))
""")


def test_app_boots_and_returns_503_when_database_is_unreachable():
    env = dict(os.environ, DATABASE_URL="postgresql://u:p@127.0.0.1:1/none", PYTHONPATH=str(BACKEND))
    out = subprocess.run([sys.executable, "-c", SCRIPT], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "HEALTH 200" in out.stdout
    assert "LOGIN 503 30" in out.stdout
    assert "starting anyway and retrying" in out.stdout
