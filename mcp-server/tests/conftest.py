"""E2E 测试共享 fixtures — 通过 MCP 协议（stdio transport）连接到 CodeBook Server。

提供:
- mcp_session: 启动子进程运行 CodeBook MCP Server，通过 ClientSession 连接
- mini_project_path: 内置微型 Python 项目的本地目录路径
- medium_project_path: 指向 repos/ 目录下可用项目的路径（跳过条件）
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest
import pytest_asyncio

# ── 定位项目根目录 ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPOS_DIR = PROJECT_ROOT.parent / "repos"


# ── mini_project fixture ────────────────────────────────

@pytest.fixture()
def mini_project_path(tmp_path: Path) -> str:
    """创建一个自包含的微型 Python 项目（api/auth/db 三层）。

    所有 E2E 测试的默认 small_project。
    """
    # app/api/routes.py
    api_dir = tmp_path / "app" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "__init__.py").write_text("")
    (api_dir / "routes.py").write_text(textwrap.dedent("""\
        from app.services.auth import login, register
        from app.db.users import find_user

        class UserRouter:
            \"\"\"用户路由控制器。\"\"\"

            def get_user(self, user_id: int) -> dict:
                \"\"\"获取单个用户。\"\"\"
                return find_user(user_id)

            def create_user(self, email: str, password: str) -> dict:
                \"\"\"注册新用户。\"\"\"
                return register(email, password)

        def health_check() -> str:
            \"\"\"健康检查端点。\"\"\"
            return "ok"
    """))

    # app/services/auth.py
    svc_dir = tmp_path / "app" / "services"
    svc_dir.mkdir(parents=True)
    (svc_dir / "__init__.py").write_text("")
    (svc_dir / "auth.py").write_text(textwrap.dedent("""\
        import hashlib
        from app.db.users import save_user, find_user_by_email

        def login(email: str, password: str) -> dict:
            \"\"\"用户登录：校验邮箱和密码。\"\"\"
            user = find_user_by_email(email)
            if user is None:
                return {"error": "用户不存在"}
            hashed = hashlib.sha256(password.encode()).hexdigest()
            if hashed != user["password_hash"]:
                return {"error": "密码错误"}
            return {"token": "fake-jwt", "user_id": user["id"]}

        def register(email: str, password: str) -> dict:
            \"\"\"注册新用户，返回用户 ID。\"\"\"
            hashed = hashlib.sha256(password.encode()).hexdigest()
            user_id = save_user(email, hashed)
            return {"user_id": user_id}

        def _hash_password(raw: str) -> str:
            \"\"\"内部辅助：哈希密码。\"\"\"
            return hashlib.sha256(raw.encode()).hexdigest()
    """))

    # app/db/users.py
    db_dir = tmp_path / "app" / "db"
    db_dir.mkdir(parents=True)
    (db_dir / "__init__.py").write_text("")
    (db_dir / "users.py").write_text(textwrap.dedent("""\
        _USERS_DB: list[dict] = []

        def save_user(email: str, password_hash: str) -> int:
            \"\"\"保存用户到数据库。\"\"\"
            user_id = len(_USERS_DB) + 1
            _USERS_DB.append({"id": user_id, "email": email, "password_hash": password_hash})
            return user_id

        def find_user(user_id: int) -> dict | None:
            \"\"\"根据 ID 查找用户。\"\"\"
            for u in _USERS_DB:
                if u["id"] == user_id:
                    return u
            return None

        def find_user_by_email(email: str) -> dict | None:
            \"\"\"根据邮箱查找用户。\"\"\"
            for u in _USERS_DB:
                if u["email"] == email:
                    return u
            return None
    """))

    # tests/test_login.py
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_login.py").write_text(textwrap.dedent("""\
        def test_login_success():
            assert True

        def test_login_wrong_password():
            assert True
    """))

    # pyproject.toml
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""\
        [tool.poetry]
        name = "mini-project"
        version = "0.1.0"
    """))

    return str(tmp_path)


# ── medium_project fixture ──────────────────────────────

def _find_medium_project() -> str | None:
    """在 repos/ 下找到第一个可用项目。"""
    if not REPOS_DIR.is_dir():
        return None
    for child in sorted(REPOS_DIR.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            return str(child)
    return None


MEDIUM_PROJECT = _find_medium_project()

skip_if_no_medium_project = pytest.mark.skipif(
    MEDIUM_PROJECT is None,
    reason=f"未找到 medium 项目 (搜索路径: {REPOS_DIR})",
)


@pytest.fixture()
def medium_project_path() -> str:
    """返回 repos/ 下第一个可用项目路径。"""
    assert MEDIUM_PROJECT is not None
    return MEDIUM_PROJECT
