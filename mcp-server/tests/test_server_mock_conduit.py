"""Mock-based equivalents of the @skip_if_no_conduit tests in test_server.py.

Strategy: build a realistic Python project in a temp directory, then call
the REAL scan_repo / read_chapter functions on it.  No external network
calls, no /tmp/conduit dependency.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.tools._repo_cache import repo_cache
from src.tools.read_chapter import read_chapter
from src.tools.scan_repo import scan_repo


# ── helpers ──────────────────────────────────────────────────────────────────


def _build_project(tmp_path: Path) -> Path:
    """Create a realistic multi-module Python project under *tmp_path*.

    Structure mirrors a typical web-app (api / services / db layers) so
    scan_repo produces meaningful modules, functions and connections.
    """
    # ── app/api/routes.py ────────────────────────────────────────────────────
    api_dir = tmp_path / "app" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "__init__.py").write_text("")
    (api_dir / "routes.py").write_text(textwrap.dedent("""\
        from app.services.auth import login, register
        from app.db.users import find_user

        class UserRouter:
            \"\"\"User route controller.\"\"\"

            def get_user(self, user_id: int) -> dict:
                \"\"\"Return a single user by ID.\"\"\"
                return find_user(user_id)

            def create_user(self, email: str, password: str) -> dict:
                \"\"\"Register a new user and return the created record.\"\"\"
                return register(email, password)

        def health_check() -> str:
            \"\"\"Health-check endpoint — always returns 'ok'.\"\"\"
            return "ok"
    """))

    # ── app/services/auth.py ─────────────────────────────────────────────────
    svc_dir = tmp_path / "app" / "services"
    svc_dir.mkdir(parents=True)
    (svc_dir / "__init__.py").write_text("")
    (svc_dir / "auth.py").write_text(textwrap.dedent("""\
        import hashlib
        from app.db.users import save_user, find_user_by_email

        def login(email: str, password: str) -> dict:
            \"\"\"Authenticate a user with email and password.\"\"\"
            user = find_user_by_email(email)
            if user is None:
                return {"error": "user not found"}
            hashed = hashlib.sha256(password.encode()).hexdigest()
            if hashed != user["password_hash"]:
                return {"error": "wrong password"}
            return {"token": "fake-jwt", "user_id": user["id"]}

        def register(email: str, password: str) -> dict:
            \"\"\"Register a new user and return the new user ID.\"\"\"
            hashed = hashlib.sha256(password.encode()).hexdigest()
            user_id = save_user(email, hashed)
            return {"user_id": user_id}

        def _hash_password(raw: str) -> str:
            \"\"\"Internal helper: hash a plain-text password.\"\"\"
            return hashlib.sha256(raw.encode()).hexdigest()
    """))

    # ── app/services/email.py ────────────────────────────────────────────────
    (svc_dir / "email.py").write_text(textwrap.dedent("""\
        import smtplib
        from email.mime.text import MIMEText

        class EmailSender:
            \"\"\"Simple SMTP email sender.\"\"\"

            def __init__(self, host: str, port: int = 587):
                self.host = host
                self.port = port

            def send(self, to: str, subject: str, body: str) -> bool:
                \"\"\"Send an email; returns True on success.\"\"\"
                msg = MIMEText(body)
                msg["Subject"] = subject
                msg["To"] = to
                try:
                    with smtplib.SMTP(self.host, self.port) as s:
                        s.sendmail("noreply@example.com", [to], msg.as_string())
                    return True
                except Exception:
                    return False

        def send_welcome_email(email: str) -> bool:
            \"\"\"Send a welcome email to a newly registered user.\"\"\"
            sender = EmailSender("smtp.example.com")
            return sender.send(email, "Welcome!", "Thanks for signing up.")
    """))

    # ── app/db/users.py ──────────────────────────────────────────────────────
    db_dir = tmp_path / "app" / "db"
    db_dir.mkdir(parents=True)
    (db_dir / "__init__.py").write_text("")
    (db_dir / "users.py").write_text(textwrap.dedent("""\
        _USERS_DB: list[dict] = []

        def save_user(email: str, password_hash: str) -> int:
            \"\"\"Persist a user record and return its new ID.\"\"\"
            user_id = len(_USERS_DB) + 1
            _USERS_DB.append({
                "id": user_id,
                "email": email,
                "password_hash": password_hash,
            })
            return user_id

        def find_user(user_id: int) -> dict | None:
            \"\"\"Look up a user by primary-key ID.\"\"\"
            for u in _USERS_DB:
                if u["id"] == user_id:
                    return u
            return None

        def find_user_by_email(email: str) -> dict | None:
            \"\"\"Look up a user by email address.\"\"\"
            for u in _USERS_DB:
                if u["email"] == email:
                    return u
            return None

        def delete_user(user_id: int) -> bool:
            \"\"\"Remove a user record; returns True if it existed.\"\"\"
            global _USERS_DB
            before = len(_USERS_DB)
            _USERS_DB = [u for u in _USERS_DB if u["id"] != user_id]
            return len(_USERS_DB) < before
    """))

    # ── app/db/sessions.py ───────────────────────────────────────────────────
    (db_dir / "sessions.py").write_text(textwrap.dedent("""\
        import time
        import uuid

        _SESSIONS: dict[str, dict] = {}

        def create_session(user_id: int) -> str:
            \"\"\"Create a new session and return its token.\"\"\"
            token = str(uuid.uuid4())
            _SESSIONS[token] = {"user_id": user_id, "created_at": time.time()}
            return token

        def get_session(token: str) -> dict | None:
            \"\"\"Retrieve session data by token.\"\"\"
            return _SESSIONS.get(token)

        def invalidate_session(token: str) -> bool:
            \"\"\"Invalidate (delete) a session; returns True if it existed.\"\"\"
            return _SESSIONS.pop(token, None) is not None
    """))

    # ── tests/test_auth.py ───────────────────────────────────────────────────
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_auth.py").write_text(textwrap.dedent("""\
        def test_login_success():
            assert True

        def test_login_wrong_password():
            assert True

        def test_register_creates_user():
            assert True
    """))

    # ── pyproject.toml ───────────────────────────────────────────────────────
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""\
        [tool.poetry]
        name = "mock-conduit"
        version = "0.1.0"
        description = "Realistic mock project for scan_repo tests"
    """))

    return tmp_path


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def project_path(tmp_path: Path) -> str:
    """Build the mock project and return its absolute path as a string."""
    return str(_build_project(tmp_path))


@pytest.fixture(autouse=True)
def clear_cache():
    """Guarantee a clean repo_cache before every test, and after."""
    repo_cache.clear_all()
    yield
    repo_cache.clear_all()


# ── scan_repo tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_repo_full_pipeline(project_path: str):
    """scan_repo full pipeline: scans local dir, returns a complete blueprint."""
    result = await scan_repo(repo_url=project_path, role="pm", depth="overview")

    assert result["status"] == "ok"
    assert result["repo_url"] == project_path
    assert result["role"] == "pm"
    assert result["depth"] == "overview"
    assert len(result["project_overview"]) > 0
    assert len(result["modules"]) > 0
    assert "mermaid_diagram" in result
    assert "graph TD" in result["mermaid_diagram"]
    assert result["stats"]["files"] > 0
    assert result["stats"]["modules"] > 0
    assert result["stats"]["functions"] > 0
    assert result["stats"]["scan_time_seconds"] >= 0


@pytest.mark.asyncio
async def test_scan_repo_accepts_all_roles(project_path: str):
    """scan_repo accepts all four role values and reflects them in the result."""
    for role in ("ceo", "pm", "investor", "qa"):
        repo_cache.clear_all()
        result = await scan_repo(repo_url=project_path, role=role)
        assert result["status"] == "ok", f"Failed for role={role}: {result}"
        assert result["role"] == role


@pytest.mark.asyncio
async def test_scan_repo_detailed_depth(project_path: str):
    """depth=detailed pre-generates chapter cards for all business modules."""
    result = await scan_repo(repo_url=project_path, role="pm", depth="detailed")

    assert result["status"] == "ok"
    assert result["depth"] == "detailed"
    assert "chapters" in result
    assert len(result["chapters"]) > 0


@pytest.mark.asyncio
async def test_scan_repo_module_fields(project_path: str):
    """Every module in the result carries the required fields."""
    result = await scan_repo(repo_url=project_path, role="pm")

    assert result["status"] == "ok"
    for mod in result["modules"]:
        assert "name" in mod, f"Module missing 'name': {mod}"
        assert "node_title" in mod, f"Module missing 'node_title': {mod}"
        assert "health" in mod, f"Module missing 'health': {mod}"
        assert "role_badge" in mod, f"Module missing 'role_badge': {mod}"
        assert "source_refs" in mod, f"Module missing 'source_refs': {mod}"


@pytest.mark.asyncio
async def test_scan_repo_connections(project_path: str):
    """connections list entries have from/to/strength with valid strength values."""
    result = await scan_repo(repo_url=project_path)

    assert result["status"] == "ok"
    for conn in result["connections"]:
        assert "from" in conn, f"Connection missing 'from': {conn}"
        assert "to" in conn, f"Connection missing 'to': {conn}"
        assert "strength" in conn, f"Connection missing 'strength': {conn}"
        assert conn["strength"] in ("strong", "weak"), (
            f"Unexpected strength value '{conn['strength']}'"
        )


# ── read_chapter tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_chapter_after_scan(project_path: str):
    """read_chapter succeeds after scan_repo, returns module_cards + dependency_graph."""
    scan_result = await scan_repo(repo_url=project_path)
    assert scan_result["status"] == "ok"

    # Pick the first real module name reported by scan_repo
    module_name = scan_result["modules"][0]["name"]

    result = await read_chapter(module_name=module_name, role="pm")

    assert result["status"] == "ok", f"read_chapter failed: {result}"
    assert len(result["module_cards"]) > 0
    assert "dependency_graph" in result
    # Sprint 3: parent_group 字段存在
    assert "parent_group" in result
    assert isinstance(result["parent_group"], str)


@pytest.mark.asyncio
async def test_read_chapter_module_not_found(project_path: str):
    """read_chapter returns an error with available_modules for an unknown module."""
    await scan_repo(repo_url=project_path)

    result = await read_chapter(module_name="__nonexistent_module_xyz__")

    assert result["status"] == "error"
    assert "available_modules" in result


@pytest.mark.asyncio
async def test_read_chapter_card_schema(project_path: str):
    """Module cards carry all required schema fields."""
    scan_result = await scan_repo(repo_url=project_path)
    assert scan_result["status"] == "ok"

    module_name = scan_result["modules"][0]["name"]
    result = await read_chapter(module_name=module_name)

    assert result["status"] == "ok"
    if result["module_cards"]:
        card = result["module_cards"][0]
        for field in ("name", "path", "summary", "functions", "classes",
                      "calls", "imports", "ref"):
            assert field in card, f"Card missing field '{field}': {list(card.keys())}"
