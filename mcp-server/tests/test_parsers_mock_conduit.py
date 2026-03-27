"""Mock-based versions of the 10 @skip_if_no_conduit tests in test_parsers.py.

Instead of requiring /tmp/conduit (a real Python project), these tests create a
temporary directory with realistic Python files that simulate a Conduit-like
project structure. The REAL functions (clone_repo, parse_all, etc.) are called
on the mock directory — only the DATA is mocked, not the code.
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.parsers.repo_cloner import CloneResult, FileInfo, clone_repo
from src.parsers.ast_parser import ParseResult, parse_file, parse_all
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import group_modules, build_node_module_map


# ── Realistic Python file content ────────────────────────────────────────────

ROUTES_PY = '''\
"""FastAPI route handlers for the Conduit API."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.auth import authenticate_user, create_access_token
from app.services.users import get_user_by_id, create_user, update_user
from app.models.user import UserCreate, UserUpdate, UserResponse

router = APIRouter(prefix="/api", tags=["users"])


class ArticleRouter:
    """Router class for article endpoints."""

    def __init__(self, prefix: str = "/articles"):
        self.prefix = prefix
        self.router = APIRouter(prefix=prefix)

    def register_routes(self):
        """Register all article routes."""
        self.router.add_api_route("/", self.list_articles, methods=["GET"])
        self.router.add_api_route("/{slug}", self.get_article, methods=["GET"])

    def list_articles(self, db: Session = Depends(get_db)) -> list:
        """Return a list of all articles."""
        return []

    def get_article(self, slug: str, db: Session = Depends(get_db)) -> dict:
        """Return a single article by slug."""
        return {}


@router.post("/users/login", response_model=UserResponse)
async def login(credentials: dict, db: Session = Depends(get_db)) -> UserResponse:
    """Authenticate user and return JWT token."""
    user = authenticate_user(db, credentials["email"], credentials["password"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token({"sub": str(user.id)})
    return UserResponse(user=user, token=token)


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    """Register a new user account."""
    existing = get_user_by_id(db, user_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email already registered",
        )
    user = create_user(db, user_data)
    token = create_access_token({"sub": str(user.id)})
    return UserResponse(user=user, token=token)


@router.get("/user", response_model=UserResponse)
async def get_current_user(db: Session = Depends(get_db)) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse(user=None, token="")


@router.put("/user", response_model=UserResponse)
async def update_current_user(
    user_data: UserUpdate, db: Session = Depends(get_db)
) -> UserResponse:
    """Update the current user\'s profile."""
    updated = update_user(db, user_data)
    return UserResponse(user=updated, token="")
'''

DEPENDENCIES_PY = '''\
"""FastAPI dependency injection helpers."""

from typing import Generator, Optional

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import User

SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy database session and close it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token, returning its payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc


def get_current_user_id(authorization: Optional[str] = Header(None)) -> int:
    """Extract and validate user ID from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing user id",
        )
    return int(user_id)


def require_auth(user_id: int = Depends(get_current_user_id)) -> int:
    """Dependency that enforces authentication; returns user_id."""
    return user_id
'''

MODELS_PY = '''\
"""SQLAlchemy ORM models for the Conduit application."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


class User(Base):
    """Represents a registered user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    bio = Column(Text, nullable=True)
    image = Column(String(512), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    articles = relationship("Article", back_populates="author", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="author", cascade="all, delete-orphan")


class Article(Base):
    """Represents a published article."""

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    body = Column(Text, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author = relationship("User", back_populates="articles")
    comments = relationship("Comment", back_populates="article", cascade="all, delete-orphan")


class Comment(Base):
    """Represents a comment on an article."""

    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    body = Column(Text, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    author = relationship("User", back_populates="comments")
    article = relationship("Article", back_populates="comments")
'''

SESSION_PY = '''\
"""Database session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.db.models import Base

DATABASE_URL = "sqlite:///./conduit.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all database tables defined in the ORM models."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Return a new database session (caller must close it)."""
    return SessionLocal()


def reset_db() -> None:
    """Drop and recreate all tables — for testing only."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
'''

AUTH_PY = '''\
"""Authentication service: password hashing, JWT creation, user verification."""

from datetime import datetime, timedelta
from typing import Optional

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.db.models import User

SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Handles all authentication-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Return True if plain matches hashed."""
        return pwd_context.verify(plain, hashed)

    def hash_password(self, plain: str) -> str:
        """Return bcrypt hash of plain."""
        return pwd_context.hash(plain)

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Look up a user by email address."""
        return self.db.query(User).filter(User.email == email).first()

    def authenticate(self, email: str, password: str) -> Optional[User]:
        """Validate email+password, returning the User or None."""
        user = self.get_user_by_email(email)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Module-level helper wrapping AuthService.authenticate."""
    service = AuthService(db)
    return service.authenticate(email, password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """Decode a JWT token and return its payload, or None if invalid."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return None
'''

USERS_PY = '''\
"""User business logic service."""

from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import User
from app.models.user import UserCreate, UserUpdate
from app.services.auth import AuthService


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Retrieve a user by their primary key."""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Retrieve a user by their email address."""
    return db.query(User).filter(User.email == email).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Retrieve a user by their username."""
    return db.query(User).filter(User.username == username).first()


def create_user(db: Session, data: UserCreate) -> User:
    """Create and persist a new user, returning the saved instance."""
    auth = AuthService(db)
    hashed = auth.hash_password(data.password)
    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hashed,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, data: UserUpdate, user_id: int) -> Optional[User]:
    """Apply partial updates to a user record."""
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    update_data = data.dict(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(user, field_name, value)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int) -> bool:
    """Delete a user by ID; returns True if deleted, False if not found."""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True


class UserService:
    """Aggregates user-related operations with a bound DB session."""

    def __init__(self, db: Session):
        self.db = db

    def find(self, user_id: int) -> Optional[User]:
        """Find a user by ID."""
        return get_user_by_id(self.db, user_id)

    def create(self, data: UserCreate) -> User:
        """Create a new user."""
        return create_user(self.db, data)

    def update(self, data: UserUpdate, user_id: int) -> Optional[User]:
        """Update an existing user."""
        return update_user(self.db, data, user_id)

    def delete(self, user_id: int) -> bool:
        """Delete a user."""
        return delete_user(self.db, user_id)
'''

USER_SCHEMA_PY = '''\
"""Pydantic schemas for user-related request/response models."""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Shared user fields used across multiple schemas."""

    email: EmailStr
    username: str = Field(..., min_length=1, max_length=100)
    bio: Optional[str] = None
    image: Optional[str] = None


class UserCreate(UserBase):
    """Schema for user registration requests."""

    password: str = Field(..., min_length=8)

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "username": "johndoe",
                "password": "secret123",
            }
        }


class UserUpdate(BaseModel):
    """Schema for partial user profile updates."""

    email: Optional[EmailStr] = None
    username: Optional[str] = None
    password: Optional[str] = None
    bio: Optional[str] = None
    image: Optional[str] = None

    def dict(self, **kwargs) -> dict:
        """Return only set fields."""
        return super().model_dump(**kwargs)


class UserInDB(UserBase):
    """Internal user schema including hashed password."""

    id: int
    hashed_password: str
    is_active: bool = True

    class Config:
        """Enable ORM mode."""
        from_attributes = True


class UserResponse(BaseModel):
    """Outer envelope returned to API clients."""

    user: Optional[UserBase] = None
    token: str = ""
'''

MAIN_PY = '''\
"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as user_router
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle for the FastAPI app."""
    init_db()
    yield


def create_app() -> FastAPI:
    """Factory function that creates and configures the FastAPI application."""
    app = FastAPI(
        title="Conduit API",
        description="RealWorld example app built with FastAPI and SQLAlchemy",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(user_router)

    return app


app = create_app()
'''

TEST_AUTH_PY = '''\
"""Tests for authentication service."""

import pytest
from unittest.mock import MagicMock, patch

from app.services.auth import (
    authenticate_user,
    create_access_token,
    verify_token,
    AuthService,
)


class TestAuthService:
    """Unit tests for AuthService class."""

    def setup_method(self):
        """Set up a mock DB session before each test."""
        self.db = MagicMock()
        self.service = AuthService(self.db)

    def test_hash_and_verify_password(self):
        """Hashed password should verify correctly."""
        plain = "mysecretpassword"
        hashed = self.service.hash_password(plain)
        assert self.service.verify_password(plain, hashed) is True

    def test_wrong_password_does_not_verify(self):
        """Wrong password should not verify."""
        hashed = self.service.hash_password("correct")
        assert self.service.verify_password("wrong", hashed) is False

    def test_authenticate_returns_none_for_missing_user(self):
        """authenticate() returns None when user not found."""
        self.db.query.return_value.filter.return_value.first.return_value = None
        result = self.service.authenticate("no@example.com", "pass")
        assert result is None


def test_create_and_verify_token():
    """Token created by create_access_token should be decodable."""
    token = create_access_token({"sub": "42"})
    payload = verify_token(token)
    assert payload is not None
    assert payload["sub"] == "42"


def test_verify_invalid_token_returns_none():
    """verify_token should return None for garbage input."""
    assert verify_token("not.a.real.token") is None
'''

TEST_USERS_PY = '''\
"""Tests for user business logic."""

import pytest
from unittest.mock import MagicMock

from app.services.users import (
    get_user_by_id,
    get_user_by_email,
    create_user,
    update_user,
    delete_user,
    UserService,
)


class TestGetUser:
    """Tests for user retrieval functions."""

    def test_get_user_by_id_returns_user(self):
        """get_user_by_id returns the user when found."""
        db = MagicMock()
        fake_user = MagicMock(id=1, email="a@b.com")
        db.query.return_value.filter.return_value.first.return_value = fake_user
        result = get_user_by_id(db, 1)
        assert result is fake_user

    def test_get_user_by_id_returns_none_when_missing(self):
        """get_user_by_id returns None when user not found."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = get_user_by_id(db, 999)
        assert result is None

    def test_get_user_by_email(self):
        """get_user_by_email should query by email field."""
        db = MagicMock()
        fake_user = MagicMock(email="x@y.com")
        db.query.return_value.filter.return_value.first.return_value = fake_user
        result = get_user_by_email(db, "x@y.com")
        assert result is fake_user


class TestDeleteUser:
    """Tests for user deletion."""

    def test_delete_existing_user_returns_true(self):
        """delete_user returns True when user is found and deleted."""
        db = MagicMock()
        fake_user = MagicMock(id=5)
        db.query.return_value.filter.return_value.first.return_value = fake_user
        assert delete_user(db, 5) is True

    def test_delete_missing_user_returns_false(self):
        """delete_user returns False when user does not exist."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert delete_user(db, 404) is False
'''

PYPROJECT_TOML = '''\
[tool.poetry]
name = "conduit"
version = "0.1.0"
description = "RealWorld example app — FastAPI + SQLAlchemy"
authors = ["Test Author <test@example.com>"]

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.110.0"
sqlalchemy = "^2.0"
pydantic = {extras = ["email"], version = "^2.0"}
python-jose = {extras = ["cryptography"], version = "^3.3"}
passlib = {extras = ["bcrypt"], version = "^1.7"}
uvicorn = "^0.29.0"

[tool.poetry.dev-dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.23"
httpx = "^0.27"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
'''


# ── Fixture ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_conduit_path(tmp_path: Path) -> Path:
    """Create a temp directory tree with realistic Conduit-like Python files."""
    # Directory structure
    dirs = [
        tmp_path / "app" / "api",
        tmp_path / "app" / "db",
        tmp_path / "app" / "services",
        tmp_path / "app" / "models",
        tmp_path / "tests",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Write __init__.py stubs so directories are Python packages
    for d in dirs:
        (d / "__init__.py").write_text('"""Package init."""\n')
    (tmp_path / "app" / "__init__.py").write_text('"""App package."""\n')

    # Write realistic source files
    files = {
        tmp_path / "app" / "api" / "routes.py": ROUTES_PY,
        tmp_path / "app" / "api" / "dependencies.py": DEPENDENCIES_PY,
        tmp_path / "app" / "db" / "models.py": MODELS_PY,
        tmp_path / "app" / "db" / "session.py": SESSION_PY,
        tmp_path / "app" / "services" / "auth.py": AUTH_PY,
        tmp_path / "app" / "services" / "users.py": USERS_PY,
        tmp_path / "app" / "models" / "user.py": USER_SCHEMA_PY,
        tmp_path / "app" / "main.py": MAIN_PY,
        tmp_path / "tests" / "test_auth.py": TEST_AUTH_PY,
        tmp_path / "tests" / "test_users.py": TEST_USERS_PY,
        tmp_path / "pyproject.toml": PYPROJECT_TOML,
    }
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")

    # Add a lock file that should be filtered out
    (tmp_path / "poetry.lock").write_text("# lock file\n")

    return tmp_path


# ══════════════════════════════════════════════════════════════════════════════
# 1. test_clone_local_dir
# ══════════════════════════════════════════════════════════════════════════════


async def test_clone_local_dir(mock_conduit_path: Path) -> None:
    """clone_repo on a local directory returns CloneResult with files and language info."""
    result = await clone_repo(str(mock_conduit_path))

    assert isinstance(result, CloneResult)
    assert result.repo_path == str(mock_conduit_path)
    assert len(result.files) > 0
    assert "python" in result.languages
    assert result.total_lines > 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. test_filters_excluded_files
# ══════════════════════════════════════════════════════════════════════════════


async def test_filters_excluded_files(mock_conduit_path: Path) -> None:
    """Lock files must not appear in the clone result."""
    result = await clone_repo(str(mock_conduit_path))
    file_names = [Path(f.path).name for f in result.files]

    assert "package-lock.json" not in file_names
    assert "poetry.lock" not in file_names


# ══════════════════════════════════════════════════════════════════════════════
# 3. test_file_info_complete
# ══════════════════════════════════════════════════════════════════════════════


async def test_file_info_complete(mock_conduit_path: Path) -> None:
    """Every non-config Python FileInfo must have all fields populated."""
    result = await clone_repo(str(mock_conduit_path))
    py_files = [
        f for f in result.files
        if f.language == "python" and not f.is_config and f.size_bytes > 0
    ]

    assert len(py_files) > 0, "Expected at least one non-config Python file"
    f = py_files[0]

    assert f.path, "path must be non-empty"
    assert f.abs_path, "abs_path must be non-empty"
    assert f.language == "python"
    assert f.size_bytes > 0
    assert f.line_count > 0
    assert f.is_config is False


# ══════════════════════════════════════════════════════════════════════════════
# 4. test_config_files_marked
# ══════════════════════════════════════════════════════════════════════════════


async def test_config_files_marked(mock_conduit_path: Path) -> None:
    """pyproject.toml must be marked as is_config=True."""
    result = await clone_repo(str(mock_conduit_path))

    config_files = [f for f in result.files if f.is_config]
    # The mock project includes pyproject.toml — it should be marked
    assert len(config_files) > 0, "Expected at least one config file to be marked"

    for f in config_files:
        assert f.is_config is True


# ══════════════════════════════════════════════════════════════════════════════
# 5. test_parse_conduit_files
# ══════════════════════════════════════════════════════════════════════════════


async def test_parse_conduit_files(mock_conduit_path: Path) -> None:
    """parse_all on the mock project should find >10 functions, >3 classes, >10 imports."""
    clone_result = await clone_repo(str(mock_conduit_path))
    py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]

    results = await parse_all(py_files)
    assert len(results) > 0, "parse_all should return at least one result"

    total_funcs = sum(len(r.functions) for r in results)
    total_classes = sum(len(r.classes) for r in results)
    total_imports = sum(len(r.imports) for r in results)

    assert total_funcs > 10, f"Expected >10 functions, got {total_funcs}"
    assert total_classes > 3, f"Expected >3 classes, got {total_classes}"
    assert total_imports > 10, f"Expected >10 imports, got {total_imports}"


# ══════════════════════════════════════════════════════════════════════════════
# 6. test_parse_coverage_above_90_percent
# ══════════════════════════════════════════════════════════════════════════════


async def test_parse_coverage_above_90_percent(mock_conduit_path: Path) -> None:
    """Parse success rate must be >= 90% across all Python files."""
    clone_result = await clone_repo(str(mock_conduit_path))
    py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]

    results = await parse_all(py_files)

    error_count = sum(1 for r in results if r.parse_errors)
    success_rate = (len(results) - error_count) / max(len(results), 1)

    assert success_rate >= 0.9, (
        f"Parse success rate {success_rate:.1%} < 90% "
        f"({error_count} errors in {len(results)} files)"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 7. test_conduit_dependency_graph
# ══════════════════════════════════════════════════════════════════════════════


async def test_conduit_dependency_graph(mock_conduit_path: Path) -> None:
    """DependencyGraph built from the mock project must have nodes and valid Mermaid output."""
    clone_result = await clone_repo(str(mock_conduit_path))
    py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]
    parse_results = await parse_all(py_files)

    dg = DependencyGraph()
    dg.build(parse_results)

    assert dg.graph.number_of_nodes() > 0, "Dependency graph must have at least one node"

    mermaid = dg.to_mermaid(level="function")
    assert "graph TD" in mermaid


# ══════════════════════════════════════════════════════════════════════════════
# 8. test_conduit_module_grouping
# ══════════════════════════════════════════════════════════════════════════════


async def test_conduit_module_grouping(mock_conduit_path: Path) -> None:
    """Module grouping must include a '测试' group and cover every parsed file."""
    clone_result = await clone_repo(str(mock_conduit_path))
    py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]
    parse_results = await parse_all(py_files)

    modules = await group_modules(parse_results, str(mock_conduit_path))

    assert len(modules) > 0, "Expected at least one module group"

    module_names = [m.name for m in modules]
    assert "测试" in module_names, f"Expected '测试' module, got: {module_names}"

    # Every parsed file must be in exactly one module group
    all_grouped_files: set[str] = set()
    for m in modules:
        all_grouped_files.update(m.files)

    parsed_files = {pr.file_path for pr in parse_results}
    assert parsed_files.issubset(all_grouped_files), (
        f"Files not grouped: {parsed_files - all_grouped_files}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 9. test_node_module_map
# ══════════════════════════════════════════════════════════════════════════════


async def test_node_module_map(mock_conduit_path: Path) -> None:
    """build_node_module_map must return a non-empty mapping."""
    clone_result = await clone_repo(str(mock_conduit_path))
    py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]
    parse_results = await parse_all(py_files)
    modules = await group_modules(parse_results, str(mock_conduit_path))

    node_map = build_node_module_map(modules, parse_results)

    assert len(node_map) > 0, "node_map must be non-empty"


# ══════════════════════════════════════════════════════════════════════════════
# 10. test_full_pipeline
# ══════════════════════════════════════════════════════════════════════════════


async def test_full_pipeline(mock_conduit_path: Path) -> None:
    """End-to-end: clone → parse → group → graph → mermaid all succeed."""
    # 1. Clone / Scan
    clone_result = await clone_repo(str(mock_conduit_path))
    assert len(clone_result.files) > 0, "clone_repo must return files"

    # 2. Parse
    py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]
    parse_results = await parse_all(py_files)
    assert len(parse_results) > 0, "parse_all must return results"

    total_funcs = sum(len(r.functions) for r in parse_results)
    total_classes = sum(len(r.classes) for r in parse_results)
    assert total_funcs > 10, f"Expected >10 functions, got {total_funcs}"
    assert total_classes > 3, f"Expected >3 classes, got {total_classes}"

    # 3. Module Grouping
    modules = await group_modules(parse_results, str(mock_conduit_path))
    assert len(modules) > 0, "group_modules must return at least one module"

    # 4. Dependency Graph
    dg = DependencyGraph()
    dg.build(parse_results)

    node_map = build_node_module_map(modules, parse_results)
    dg.set_module_groups(node_map)

    assert dg.graph.number_of_nodes() > 0, "Dependency graph must have nodes"

    # 5. Mermaid output
    mermaid_module = dg.to_mermaid(level="module")
    mermaid_func = dg.to_mermaid(level="function")

    assert "graph TD" in mermaid_module
    assert "graph TD" in mermaid_func
    assert len(mermaid_module.strip().split("\n")) > 1
