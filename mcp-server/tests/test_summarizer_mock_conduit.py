"""test_summarizer_mock_conduit.py

Mock-based equivalents of the 7 @skip_if_no_conduit tests in test_summarizer.py.

Instead of relying on /tmp/conduit, this module creates a realistic Python
project structure in a temp directory, runs the REAL parsers (clone_repo,
parse_all, group_modules, DependencyGraph), and constructs a real SummaryContext
— so no external test infrastructure is required.
"""

import textwrap
from pathlib import Path

import pytest
import pytest_asyncio

from src.parsers.repo_cloner import clone_repo
from src.parsers.ast_parser import parse_all
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import group_modules, build_node_module_map
from src.summarizer.engine import (
    SummaryContext,
    build_l1_prompt,
    build_l2_prompt,
    build_l3_prompt,
    generate_local_blueprint,
    generate_local_chapter,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _create_mock_conduit(tmp_path: Path) -> None:
    """Create a realistic Python project mirroring the Conduit structure.

    Directory layout (mirrors real Conduit):
      app/
        __init__.py
        api/
          __init__.py
          routes.py
          articles.py
        db/
          __init__.py
          connection.py
          queries.py
        services/
          __init__.py
          article_service.py
          user_service.py
        models/
          __init__.py
          user.py
          article.py
      tests/
        test_articles.py
        test_users.py
    """

    # ── app/__init__.py ──────────────────────────────────
    _write(tmp_path / "app" / "__init__.py", """\
        \"\"\"Conduit-like application package.\"\"\"
    """)

    # ── app/api/__init__.py ──────────────────────────────
    _write(tmp_path / "app" / "api" / "__init__.py", "")

    # ── app/api/routes.py ───────────────────────────────
    _write(tmp_path / "app" / "api" / "routes.py", """\
        \"\"\"HTTP route handlers for the main API.\"\"\"

        from app.services.user_service import create_user, get_user
        from app.services.article_service import create_article, list_articles


        class UserRouter:
            \"\"\"Routes for user-related endpoints.\"\"\"

            def get_user_handler(self, user_id: int) -> dict:
                \"\"\"Return a single user by ID.\"\"\"
                return get_user(user_id)

            def create_user_handler(self, email: str, password: str) -> dict:
                \"\"\"Register a new user account.\"\"\"
                return create_user(email, password)


        class ArticleRouter:
            \"\"\"Routes for article-related endpoints.\"\"\"

            def list_articles_handler(self, tag: str = "") -> list:
                \"\"\"Return a list of articles, optionally filtered by tag.\"\"\"
                return list_articles(tag=tag)

            def create_article_handler(self, title: str, body: str, author_id: int) -> dict:
                \"\"\"Publish a new article.\"\"\"
                return create_article(title=title, body=body, author_id=author_id)


        def health_check() -> str:
            \"\"\"Health check endpoint, returns 'ok'.\"\"\"
            return "ok"
    """)

    # ── app/api/articles.py ──────────────────────────────
    _write(tmp_path / "app" / "api" / "articles.py", """\
        \"\"\"Article-specific API helpers and validators.\"\"\"

        from app.models.article import Article


        def validate_article_payload(payload: dict) -> bool:
            \"\"\"Validate required fields in an article creation request.\"\"\"
            required = {"title", "body", "author_id"}
            return required.issubset(payload.keys())


        def format_article_response(article: Article) -> dict:
            \"\"\"Convert an Article model instance to an API-safe dict.\"\"\"
            return {
                "id": article.article_id,
                "title": article.title,
                "body": article.body,
                "author_id": article.author_id,
            }


        def paginate(items: list, page: int = 1, per_page: int = 20) -> dict:
            \"\"\"Slice a list for paginated API responses.\"\"\"
            start = (page - 1) * per_page
            end = start + per_page
            return {
                "items": items[start:end],
                "total": len(items),
                "page": page,
                "per_page": per_page,
            }
    """)

    # ── app/db/__init__.py ───────────────────────────────
    _write(tmp_path / "app" / "db" / "__init__.py", "")

    # ── app/db/connection.py ─────────────────────────────
    _write(tmp_path / "app" / "db" / "connection.py", """\
        \"\"\"Database connection management.\"\"\"

        from typing import Optional


        _DB_POOL: Optional[list] = None


        def get_connection():
            \"\"\"Return a connection from the pool (stub).\"\"\"
            global _DB_POOL
            if _DB_POOL is None:
                _DB_POOL = []
            return _DB_POOL


        def close_all_connections() -> None:
            \"\"\"Close every connection in the pool.\"\"\"
            global _DB_POOL
            _DB_POOL = None


        def ping() -> bool:
            \"\"\"Check whether the database is reachable.\"\"\"
            try:
                get_connection()
                return True
            except Exception:
                return False
    """)

    # ── app/db/queries.py ────────────────────────────────
    _write(tmp_path / "app" / "db" / "queries.py", """\
        \"\"\"Raw SQL query helpers.\"\"\"

        from app.db.connection import get_connection


        def fetch_user_by_id(user_id: int) -> dict | None:
            \"\"\"Fetch a user row by primary key.\"\"\"
            conn = get_connection()
            # stub: return None when pool is empty
            return None


        def fetch_user_by_email(email: str) -> dict | None:
            \"\"\"Fetch a user row by email address.\"\"\"
            conn = get_connection()
            return None


        def insert_user(email: str, password_hash: str) -> int:
            \"\"\"Insert a new user row and return the new ID.\"\"\"
            conn = get_connection()
            return 1


        def fetch_articles(tag: str = "") -> list:
            \"\"\"Fetch all article rows, optionally filtered by tag.\"\"\"
            conn = get_connection()
            return []


        def insert_article(title: str, body: str, author_id: int) -> int:
            \"\"\"Insert a new article and return its ID.\"\"\"
            conn = get_connection()
            return 1
    """)

    # ── app/services/__init__.py ─────────────────────────
    _write(tmp_path / "app" / "services" / "__init__.py", "")

    # ── app/services/user_service.py ─────────────────────
    _write(tmp_path / "app" / "services" / "user_service.py", """\
        \"\"\"Business logic for user management.\"\"\"

        import hashlib

        from app.db.queries import fetch_user_by_email, fetch_user_by_id, insert_user


        def create_user(email: str, password: str) -> dict:
            \"\"\"Register a new user after hashing the password.\"\"\"
            existing = fetch_user_by_email(email)
            if existing:
                return {"error": "email already registered"}
            hashed = _hash_password(password)
            user_id = insert_user(email, hashed)
            return {"user_id": user_id, "email": email}


        def get_user(user_id: int) -> dict:
            \"\"\"Retrieve user details by ID.\"\"\"
            user = fetch_user_by_id(user_id)
            if user is None:
                return {"error": "not found"}
            return user


        def authenticate(email: str, password: str) -> dict:
            \"\"\"Verify credentials and return a session token stub.\"\"\"
            user = fetch_user_by_email(email)
            if user is None:
                return {"error": "user not found"}
            if user.get("password_hash") != _hash_password(password):
                return {"error": "wrong password"}
            return {"token": "stub-token", "user_id": user["id"]}


        def _hash_password(raw: str) -> str:
            \"\"\"Internal helper: SHA-256 hash a plaintext password.\"\"\"
            return hashlib.sha256(raw.encode()).hexdigest()
    """)

    # ── app/services/article_service.py ──────────────────
    _write(tmp_path / "app" / "services" / "article_service.py", """\
        \"\"\"Business logic for article management.\"\"\"

        from app.db.queries import fetch_articles, insert_article
        from app.models.article import Article


        def create_article(title: str, body: str, author_id: int) -> dict:
            \"\"\"Create and persist a new article.\"\"\"
            if not title or not body:
                return {"error": "title and body are required"}
            article_id = insert_article(title, body, author_id)
            return {"article_id": article_id, "title": title}


        def list_articles(tag: str = "") -> list:
            \"\"\"Return all articles, optionally filtered by tag.\"\"\"
            rows = fetch_articles(tag=tag)
            return [
                Article(
                    article_id=r.get("id", 0),
                    title=r.get("title", ""),
                    body=r.get("body", ""),
                    author_id=r.get("author_id", 0),
                )
                for r in rows
            ]


        def delete_article(article_id: int, requester_id: int) -> dict:
            \"\"\"Delete an article if the requester is the author.\"\"\"
            return {"status": "deleted", "article_id": article_id}
    """)

    # ── app/models/__init__.py ───────────────────────────
    _write(tmp_path / "app" / "models" / "__init__.py", "")

    # ── app/models/user.py ───────────────────────────────
    _write(tmp_path / "app" / "models" / "user.py", """\
        \"\"\"User domain model.\"\"\"

        from dataclasses import dataclass, field


        @dataclass
        class User:
            \"\"\"Represents a registered user.\"\"\"

            user_id: int
            email: str
            password_hash: str
            is_active: bool = True
            roles: list = field(default_factory=list)

            def is_admin(self) -> bool:
                \"\"\"Return True if this user has the admin role.\"\"\"
                return "admin" in self.roles

            def deactivate(self) -> None:
                \"\"\"Mark the user account as inactive.\"\"\"
                self.is_active = False


        def from_dict(data: dict) -> User:
            \"\"\"Construct a User instance from a raw dict (e.g. DB row).\"\"\"
            return User(
                user_id=data["id"],
                email=data["email"],
                password_hash=data.get("password_hash", ""),
                is_active=data.get("is_active", True),
                roles=data.get("roles", []),
            )
    """)

    # ── app/models/article.py ────────────────────────────
    _write(tmp_path / "app" / "models" / "article.py", """\
        \"\"\"Article domain model.\"\"\"

        from dataclasses import dataclass


        @dataclass
        class Article:
            \"\"\"Represents a published article.\"\"\"

            article_id: int
            title: str
            body: str
            author_id: int
            tags: list = None

            def __post_init__(self):
                if self.tags is None:
                    self.tags = []

            def word_count(self) -> int:
                \"\"\"Return the approximate word count of the article body.\"\"\"
                return len(self.body.split())

            def has_tag(self, tag: str) -> bool:
                \"\"\"Return True if the article has the given tag.\"\"\"
                return tag in self.tags


        def slugify(title: str) -> str:
            \"\"\"Convert an article title to a URL-friendly slug.\"\"\"
            return title.lower().replace(" ", "-")
    """)

    # ── tests/ ───────────────────────────────────────────
    _write(tmp_path / "tests" / "test_users.py", """\
        \"\"\"Tests for user_service.\"\"\"

        from app.services.user_service import create_user, get_user


        def test_create_user():
            result = create_user("alice@example.com", "secret123")
            assert "user_id" in result or "error" in result


        def test_get_user_not_found():
            result = get_user(99999)
            assert "error" in result
    """)

    _write(tmp_path / "tests" / "test_articles.py", """\
        \"\"\"Tests for article_service.\"\"\"

        from app.services.article_service import create_article, list_articles


        def test_create_article_missing_body():
            result = create_article("My Title", "", author_id=1)
            assert result.get("error")


        def test_list_articles_empty():
            articles = list_articles()
            assert isinstance(articles, list)
    """)


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def mock_conduit_ctx(tmp_path: Path) -> SummaryContext:
    """Build a SummaryContext from a locally-created mock project.

    Uses REAL clone_repo, parse_all, group_modules, and DependencyGraph —
    only the project on disk is synthetic rather than the actual Conduit repo.
    """
    _create_mock_conduit(tmp_path)

    project_path = str(tmp_path)

    clone_result = await clone_repo(project_path)
    py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]
    parse_results = await parse_all(py_files)
    modules = await group_modules(parse_results, project_path)
    dep_graph = DependencyGraph()
    dep_graph.build(parse_results)
    node_map = build_node_module_map(modules, parse_results)
    dep_graph.set_module_groups(node_map)

    return SummaryContext(
        clone_result=clone_result,
        parse_results=parse_results,
        modules=modules,
        dep_graph=dep_graph,
        role="pm",
    )


# ── Tests (mirrors the 7 @skip_if_no_conduit tests) ──────────────────────────


class TestPromptBuildingMockConduit:

    async def test_build_l1_prompt(self, mock_conduit_ctx: SummaryContext):
        """L1 prompt should reference '项目' in system and 'app' in user."""
        system, user = build_l1_prompt(mock_conduit_ctx)

        assert len(system) > 50
        assert len(user) > 50
        assert "项目" in system
        # user prompt should contain the rendered file tree which includes 'app'
        assert "app" in user

    async def test_build_l2_prompt(self, mock_conduit_ctx: SummaryContext):
        """L2 prompt should embed the project summary and '文件' keyword."""
        system, user = build_l2_prompt(mock_conduit_ctx, project_summary="测试项目概览")

        assert len(system) > 50
        assert "测试项目概览" in user
        # module_groups text always contains '文件' (file count suffix)
        assert "文件" in user

    async def test_build_l3_prompt(self, mock_conduit_ctx: SummaryContext):
        """L3 prompt should embed module name, HTTP codes, and banned terms."""
        # Pick the first non-special module
        target = None
        for m in mock_conduit_ctx.modules:
            if not m.is_special:
                target = m
                break
        assert target is not None, "Expected at least one non-special module"

        repo_path = mock_conduit_ctx.clone_result.repo_path
        system, user = build_l3_prompt(mock_conduit_ctx, target, repo_path)

        assert len(system) > 50
        assert target.name in user
        # system prompt must include HTTP annotations and banned terms
        assert "400" in system
        assert "幂等" in system or "slug" in system

    async def test_generate_local_blueprint(self, mock_conduit_ctx: SummaryContext):
        """Blueprint should be valid with modules, mermaid, and stats."""
        result = generate_local_blueprint(mock_conduit_ctx)

        assert result["status"] == "ok"
        assert len(result["project_overview"]) > 0
        assert len(result["modules"]) > 0
        assert len(result["mermaid_diagram"]) > 0
        assert "graph TD" in result["mermaid_diagram"]
        assert result["stats"]["files"] > 0
        assert result["stats"]["modules"] > 0
        assert result["stats"]["functions"] > 0
        assert result["stats"]["scan_time_seconds"] >= 0

        # Every module must have the required fields
        for mod in result["modules"]:
            assert "name" in mod
            assert "paths" in mod
            assert "responsibility" in mod

    async def test_generate_local_chapter_exists(self, mock_conduit_ctx: SummaryContext):
        """Chapter for an existing multi-file module should return ok + cards."""
        target_name = None
        for m in mock_conduit_ctx.modules:
            if not m.is_special and len(m.files) > 1:
                target_name = m.name
                break
        assert target_name is not None, (
            "Expected at least one non-special module with >1 file; "
            f"modules found: {[(m.name, len(m.files), m.is_special) for m in mock_conduit_ctx.modules]}"
        )

        result = generate_local_chapter(mock_conduit_ctx, target_name)

        assert result["status"] == "ok"
        assert result["module_name"] == target_name
        assert len(result["module_cards"]) > 0
        assert len(result["dependency_graph"]) > 0

        # Card field completeness
        card = result["module_cards"][0]
        for field in ["name", "path", "what", "inputs", "outputs", "branches",
                      "key_code_refs", "pm_note"]:
            assert field in card, f"Missing field in card: {field}"

    async def test_generate_local_chapter_not_found(self, mock_conduit_ctx: SummaryContext):
        """Requesting a non-existent module should return error + available_modules."""
        result = generate_local_chapter(mock_conduit_ctx, "不存在的模块")

        assert result["status"] == "error"
        assert "available_modules" in result

    async def test_blueprint_module_card_schema_consistent(self, mock_conduit_ctx: SummaryContext):
        """Blueprint module schema should contain all codebook_config-defined fields."""
        blueprint = generate_local_blueprint(mock_conduit_ctx)

        # Fields defined in codebook_config blueprint module schema
        expected_fields = {"name", "paths", "responsibility", "entry_points",
                           "depends_on", "used_by", "pm_note"}

        for mod in blueprint["modules"]:
            actual_fields = set(mod.keys())
            assert expected_fields.issubset(actual_fields), (
                f"Module '{mod['name']}' missing fields: {expected_fields - actual_fields}"
            )
