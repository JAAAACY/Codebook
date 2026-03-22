================================================
FILE: README.rst
================================================
.. image:: ./.github/assets/logo.png

|

.. image:: https://github.com/nsidnev/fastapi-realworld-example-app/workflows/API%20spec/badge.svg
   :target: https://github.com/nsidnev/fastapi-realworld-example-app

.. image:: https://github.com/nsidnev/fastapi-realworld-example-app/workflows/Tests/badge.svg
   :target: https://github.com/nsidnev/fastapi-realworld-example-app

.. image:: https://github.com/nsidnev/fastapi-realworld-example-app/workflows/Styles/badge.svg
   :target: https://github.com/nsidnev/fastapi-realworld-example-app

.. image:: https://codecov.io/gh/nsidnev/fastapi-realworld-example-app/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/nsidnev/fastapi-realworld-example-app

.. image:: https://img.shields.io/github/license/Naereen/StrapDown.js.svg
   :target: https://github.com/nsidnev/fastapi-realworld-example-app/blob/master/LICENSE

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/ambv/black

.. image:: https://img.shields.io/badge/style-wemake-000000.svg
   :target: https://github.com/wemake-services/wemake-python-styleguide

----------

**NOTE**: This repository is not actively maintained because this example is quite complete and does its primary goal - passing Conduit testsuite.

More modern and relevant examples can be found in other repositories with ``fastapi`` tag on GitHub.

Quickstart
----------

First, run ``PostgreSQL``, set environment variables and create database. For example using ``docker``: ::

    export POSTGRES_DB=rwdb POSTGRES_PORT=5432 POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres
    docker run --name pgdb --rm -e POSTGRES_USER="$POSTGRES_USER" -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" -e POSTGRES_DB="$POSTGRES_DB" postgres
    export POSTGRES_HOST=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' pgdb)
    createdb --host=$POSTGRES_HOST --port=$POSTGRES_PORT --username=$POSTGRES_USER $POSTGRES_DB

Then run the following commands to bootstrap your environment with ``poetry``: ::

    git clone https://github.com/nsidnev/fastapi-realworld-example-app
    cd fastapi-realworld-example-app
    poetry install
    poetry shell

Then create ``.env`` file (or rename and modify ``.env.example``) in project root and set environment variables for application: ::

    touch .env
    echo APP_ENV=dev >> .env
    echo DATABASE_URL=postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$POSTGRES_HOST:$POSTGRES_PORT/$POSTGRES_DB >> .env
    echo SECRET_KEY=$(openssl rand -hex 32) >> .env

To run the web application in debug use::

    alembic upgrade head
    uvicorn app.main:app --reload

If you run into the following error in your docker container:

   sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) could not connect to server: No such file or directory
   Is the server running locally and accepting
   connections on Unix domain socket "/tmp/.s.PGSQL.5432"?

Ensure the DATABASE_URL variable is set correctly in the `.env` file.
It is most likely caused by POSTGRES_HOST not pointing to its localhost.

   DATABASE_URL=postgresql://postgres:postgres@0.0.0.0:5432/rwdb



Run tests
---------

Tests for this project are defined in the ``tests/`` folder.

Set up environment variable ``DATABASE_URL`` or set up ``database_url`` in ``app/core/settings/test.py``

This project uses `pytest
<https://docs.pytest.org/>`_ to define tests because it allows you to use the ``assert`` keyword with good formatting for failed assertations.


To run all the tests of a project, simply run the ``pytest`` command: ::

    $ pytest
    ================================================= test session starts ==================================================
    platform linux -- Python 3.8.3, pytest-5.4.2, py-1.8.1, pluggy-0.13.1
    rootdir: /home/some-user/user-projects/fastapi-realworld-example-app, inifile: setup.cfg, testpaths: tests
    plugins: env-0.6.2, cov-2.9.0, asyncio-0.12.0
    collected 90 items
    
    tests/test_api/test_errors/test_422_error.py .                                                                   [  1%]
    tests/test_api/test_errors/test_error.py .                                                                       [  2%]
    tests/test_api/test_routes/test_articles.py .................................                                    [ 38%]
    tests/test_api/test_routes/test_authentication.py ..                                                             [ 41%]
    tests/test_api/test_routes/test_comments.py ....                                                                 [ 45%]
    tests/test_api/test_routes/test_login.py ...                                                                     [ 48%]
    tests/test_api/test_routes/test_profiles.py ............                                                         [ 62%]
    tests/test_api/test_routes/test_registration.py ...                                                              [ 65%]
    tests/test_api/test_routes/test_tags.py ..                                                                       [ 67%]
    tests/test_api/test_routes/test_users.py ....................                                                    [ 90%]
    tests/test_db/test_queries/test_tables.py ...                                                                    [ 93%]
    tests/test_schemas/test_rw_model.py .                                                                            [ 94%]
    tests/test_services/test_jwt.py .....                                                                            [100%]
    
    ============================================ 90 passed in 70.50s (0:01:10) =============================================
    $

If you want to run a specific test, you can do this with `this
<https://docs.pytest.org/en/latest/usage.html#specifying-tests-selecting-tests>`_ pytest feature: ::

    $ pytest tests/test_api/test_routes/test_users.py::test_user_can_not_take_already_used_credentials

Deployment with Docker
----------------------

You must have ``docker`` and ``docker-compose`` tools installed to work with material in this section.
First, create ``.env`` file like in `Quickstart` section or modify ``.env.example``.
``POSTGRES_HOST`` must be specified as `db` or modified in ``docker-compose.yml`` also.
Then just run::

    docker-compose up -d db
    docker-compose up -d app

Application will be available on ``localhost`` in your browser.

Web routes
----------

All routes are available on ``/docs`` or ``/redoc`` paths with Swagger or ReDoc.


Project structure
-----------------

Files related to application are in the ``app`` or ``tests`` directories.
Application parts are:

::

    app
    ├── api              - web related stuff.
    │   ├── dependencies - dependencies for routes definition.
    │   ├── errors       - definition of error handlers.
    │   └── routes       - web routes.
    ├── core             - application configuration, startup events, logging.
    ├── db               - db related stuff.
    │   ├── migrations   - manually written alembic migrations.
    │   └── repositories - all crud stuff.
    ├── models           - pydantic models for this application.
    │   ├── domain       - main models that are used almost everywhere.
    │   └── schemas      - schemas for using in web routes.
    ├── resources        - strings that are used in web responses.
    ├── services         - logic that is not just crud related.
    └── main.py          - FastAPI application creation and configuration.



================================================
FILE: alembic.ini
================================================
[alembic]
script_location = ./app/db/migrations

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S



================================================
FILE: docker-compose.yml
================================================
version: '3'

services:
  app:
    build: .
    restart: on-failure
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: "postgresql://postgres:postgres@db/postgres"
    env_file:
      - .env
    depends_on:
      - db
  db:
    image: postgres:11.5-alpine
    ports:
      - "5432:5432"
    env_file:
      - .env
    volumes:
      - ./postgres-data:/var/lib/postgresql/data:cached



================================================
FILE: Dockerfile
================================================
FROM python:3.9.10-slim

ENV PYTHONUNBUFFERED 1

EXPOSE 8000
WORKDIR /app


RUN apt-get update && \
    apt-get install -y --no-install-recommends netcat && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY poetry.lock pyproject.toml ./
RUN pip install poetry==1.1 && \
    poetry config virtualenvs.in-project true && \
    poetry install --no-dev

COPY . ./

CMD poetry run alembic upgrade head && \
    poetry run uvicorn --host=0.0.0.0 app.main:app



================================================
FILE: LICENSE
================================================
MIT License

Copyright (c) 2019 Nik Sidnev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


================================================
FILE: pyproject.toml
================================================
[tool.poetry]
name = "fastapi-realworld-example-app"
version = "0.0.0"
description = "Backend logic implementation for https://github.com/gothinkster/realworld with awesome FastAPI"
authors = ["Nik Sidnev <sidnev.nick@gmail.com>"]
license = "MIT"

[tool.poetry.dependencies]
python = "^3.9"
uvicorn = "^0.18.2"
fastapi = "^0.79.1"
pydantic = { version = "^1.9", extras = ["email", "dotenv"] }
passlib = { version = "^1.7", extras = ["bcrypt"] }
pyjwt = "^2.4"
databases = "^0.6.1"
asyncpg = "^0.26.0"
psycopg2-binary = "^2.9.3"
aiosql = "^6.2"
pypika = "^0.48.9"
alembic = "^1.8"
python-slugify = "^6.1"
Unidecode = "^1.3"
loguru = "^0.6.0"

[tool.poetry.dev-dependencies]
black = "^22.6.0"
isort = "^5.10"
autoflake = "^1.4"
wemake-python-styleguide = "^0.16.1"
mypy = "^0.971"
flake8-fixme = "^1.1"
pytest = "^7.1"
pytest-cov = "^3.0"
pytest-asyncio = "^0.19.0"
pytest-env = "^0.6.2"
pytest-xdist = "^2.4.0"
httpx = "^0.23.0"
asgi-lifespan = "^1.0.1"

[tool.isort]
profile = "black"
src_paths = ["app", "tests"]
combine_as_imports = true

[tool.pytest.ini_options]
testpaths = "tests"
filterwarnings = "error"
addopts = '''
  --strict-markers
  --tb=short
  --cov=app
  --cov=tests
  --cov-branch
  --cov-report=term-missing
  --cov-report=html
  --cov-report=xml
  --no-cov-on-fail
  --cov-fail-under=100
  --numprocesses=auto
  --asyncio-mode=auto
'''
env = [
  "SECRET_KEY=secret",
  "MAX_CONNECTIONS_COUNT=1",
  "MIN_CONNECTIONS_COUNT=1"
]

[build-system]
requires = ["poetry>=1.0"]
build-backend = "poetry.masonry.api"



================================================
FILE: setup.cfg
================================================
[coverage:report]
precision = 2
exclude_lines =
    pragma: no cover
    raise NotImplementedError
    raise NotImplemented

[coverage:run]
source = app
branch = True

[mypy]
plugins = pydantic.mypy

strict_optional = True
warn_redundant_casts = True
warn_unused_ignores = True
disallow_any_generics = True
check_untyped_defs = True

disallow_untyped_defs = True

[pydantic-mypy]
init_forbid_extra = True
init_typed = True
warn_required_dynamic_aliases = True
warn_untyped_fields = True

[mypy-sqlalchemy.*]
ignore_missing_imports = True

[mypy-alembic.*]
ignore_missing_imports = True

[mypy-loguru.*]
ignore_missing_imports = True

[mypy-asyncpg.*]
ignore_missing_imports = True

[mypy-bcrypt.*]
ignore_missing_imports = True

[mypy-passlib.*]
ignore_missing_imports = True

[mypy-slugify.*]
ignore_missing_imports = True

[mypy-pypika.*]
ignore_missing_imports = True

[flake8]
format = wemake
max-line-length = 88
per-file-ignores =
    # ignore error on builtin names for TypedTable classes, since just mapper for SQL table
    app/db/queries/tables.py: WPS125,

    # ignore black disabling in some places for queries building using pypika
    app/db/repositories/*.py: E800,
    
    app/api/dependencies/authentication.py: WPS201,
ignore =
    # common errors:
    # FastAPI architecture requires a lot of functions calls as default arguments, so ignore it here.
    B008,
    # docs are missing in this project.
    D, RST

    # WPS: 3xx
    # IMO, but the obligation to specify the base class is redundant.
    WPS306,
    
    # WPS: 4xx
    # FastAPI architecture requires a lot of complex calls as default arguments, so ignore it here.
    WPS404,
    # again, FastAPI DI architecture involves a lot of nested functions as DI providers.
    WPS430,
    # used for pypika operations
    WPS465,
    
    # WPS: 6xx
    # pydantic defines models in dataclasses model style, but not supported by WPS.
    WPS601,
no-accept-encodings = True
nested-classes-whitelist=Config
inline-quotes = double



================================================
FILE: .dockerignore
================================================
__pycache__
*.pyc
*.pyo
*.pyd
.Python
.env*
pip-log.txt
pip-delete-this-directory.txt
.tox
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*,cover
*.log
.git*
tests
scripts
postman
./postgres-data



================================================
FILE: .env.example
================================================
SECRET_KEY=secret
DEBUG=True
DATABASE_URL=postgresql://postgres:postgres@localhost/postgres



================================================
FILE: app/__init__.py
================================================
[Empty file]


================================================
FILE: app/main.py
================================================
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from app.api.errors.http_error import http_error_handler
from app.api.errors.validation_error import http422_error_handler
from app.api.routes.api import router as api_router
from app.core.config import get_app_settings
from app.core.events import create_start_app_handler, create_stop_app_handler


def get_application() -> FastAPI:
    settings = get_app_settings()

    settings.configure_logging()
    
    application = FastAPI(**settings.fastapi_kwargs)
    
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_hosts,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    application.add_event_handler(
        "startup",
        create_start_app_handler(application, settings),
    )
    application.add_event_handler(
        "shutdown",
        create_stop_app_handler(application),
    )
    
    application.add_exception_handler(HTTPException, http_error_handler)
    application.add_exception_handler(RequestValidationError, http422_error_handler)
    
    application.include_router(api_router, prefix=settings.api_prefix)
    
    return application


app = get_application()



================================================
FILE: app/api/__init__.py
================================================
[Empty file]


================================================
FILE: app/api/dependencies/__init__.py
================================================
[Empty file]


================================================
FILE: app/api/dependencies/articles.py
================================================
from typing import Optional

from fastapi import Depends, HTTPException, Path, Query
from starlette import status

from app.api.dependencies.authentication import get_current_user_authorizer
from app.api.dependencies.database import get_repository
from app.db.errors import EntityDoesNotExist
from app.db.repositories.articles import ArticlesRepository
from app.models.domain.articles import Article
from app.models.domain.users import User
from app.models.schemas.articles import (
    DEFAULT_ARTICLES_LIMIT,
    DEFAULT_ARTICLES_OFFSET,
    ArticlesFilters,
)
from app.resources import strings
from app.services.articles import check_user_can_modify_article


def get_articles_filters(
    tag: Optional[str] = None,
    author: Optional[str] = None,
    favorited: Optional[str] = None,
    limit: int = Query(DEFAULT_ARTICLES_LIMIT, ge=1),
    offset: int = Query(DEFAULT_ARTICLES_OFFSET, ge=0),
) -> ArticlesFilters:
    return ArticlesFilters(
        tag=tag,
        author=author,
        favorited=favorited,
        limit=limit,
        offset=offset,
    )


async def get_article_by_slug_from_path(
    slug: str = Path(..., min_length=1),
    user: Optional[User] = Depends(get_current_user_authorizer(required=False)),
    articles_repo: ArticlesRepository = Depends(get_repository(ArticlesRepository)),
) -> Article:
    try:
        return await articles_repo.get_article_by_slug(slug=slug, requested_user=user)
    except EntityDoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=strings.ARTICLE_DOES_NOT_EXIST_ERROR,
        )


def check_article_modification_permissions(
    current_article: Article = Depends(get_article_by_slug_from_path),
    user: User = Depends(get_current_user_authorizer()),
) -> None:
    if not check_user_can_modify_article(current_article, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=strings.USER_IS_NOT_AUTHOR_OF_ARTICLE,
        )



================================================
FILE: app/api/dependencies/authentication.py
================================================
# noqa:WPS201
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from starlette import requests, status
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.dependencies.database import get_repository
from app.core.config import get_app_settings
from app.core.settings.app import AppSettings
from app.db.errors import EntityDoesNotExist
from app.db.repositories.users import UsersRepository
from app.models.domain.users import User
from app.resources import strings
from app.services import jwt

HEADER_KEY = "Authorization"


class RWAPIKeyHeader(APIKeyHeader):
    async def __call__(  # noqa: WPS610
        self,
        request: requests.Request,
    ) -> Optional[str]:
        try:
            return await super().__call__(request)
        except StarletteHTTPException as original_auth_exc:
            raise HTTPException(
                status_code=original_auth_exc.status_code,
                detail=strings.AUTHENTICATION_REQUIRED,
            )


def get_current_user_authorizer(*, required: bool = True) -> Callable:  # type: ignore
    return _get_current_user if required else _get_current_user_optional


def _get_authorization_header_retriever(
    *,
    required: bool = True,
) -> Callable:  # type: ignore
    return _get_authorization_header if required else _get_authorization_header_optional


def _get_authorization_header(
    api_key: str = Security(RWAPIKeyHeader(name=HEADER_KEY)),
    settings: AppSettings = Depends(get_app_settings),
) -> str:
    try:
        token_prefix, token = api_key.split(" ")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=strings.WRONG_TOKEN_PREFIX,
        )
    if token_prefix != settings.jwt_token_prefix:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=strings.WRONG_TOKEN_PREFIX,
        )

    return token


def _get_authorization_header_optional(
    authorization: Optional[str] = Security(
        RWAPIKeyHeader(name=HEADER_KEY, auto_error=False),
    ),
    settings: AppSettings = Depends(get_app_settings),
) -> str:
    if authorization:
        return _get_authorization_header(authorization, settings)

    return ""


async def _get_current_user(
    users_repo: UsersRepository = Depends(get_repository(UsersRepository)),
    token: str = Depends(_get_authorization_header_retriever()),
    settings: AppSettings = Depends(get_app_settings),
) -> User:
    try:
        username = jwt.get_username_from_token(
            token,
            str(settings.secret_key.get_secret_value()),
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=strings.MALFORMED_PAYLOAD,
        )

    try:
        return await users_repo.get_user_by_username(username=username)
    except EntityDoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=strings.MALFORMED_PAYLOAD,
        )


async def _get_current_user_optional(
    repo: UsersRepository = Depends(get_repository(UsersRepository)),
    token: str = Depends(_get_authorization_header_retriever(required=False)),
    settings: AppSettings = Depends(get_app_settings),
) -> Optional[User]:
    if token:
        return await _get_current_user(repo, token, settings)

    return None



================================================
FILE: app/api/dependencies/comments.py
================================================
from typing import Optional

from fastapi import Depends, HTTPException, Path
from starlette import status

from app.api.dependencies import articles, authentication, database
from app.db.errors import EntityDoesNotExist
from app.db.repositories.comments import CommentsRepository
from app.models.domain.articles import Article
from app.models.domain.comments import Comment
from app.models.domain.users import User
from app.resources import strings
from app.services.comments import check_user_can_modify_comment


async def get_comment_by_id_from_path(
    comment_id: int = Path(..., ge=1),
    article: Article = Depends(articles.get_article_by_slug_from_path),
    user: Optional[User] = Depends(
        authentication.get_current_user_authorizer(required=False),
    ),
    comments_repo: CommentsRepository = Depends(
        database.get_repository(CommentsRepository),
    ),
) -> Comment:
    try:
        return await comments_repo.get_comment_by_id(
            comment_id=comment_id,
            article=article,
            user=user,
        )
    except EntityDoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=strings.COMMENT_DOES_NOT_EXIST,
        )


def check_comment_modification_permissions(
    comment: Comment = Depends(get_comment_by_id_from_path),
    user: User = Depends(authentication.get_current_user_authorizer()),
) -> None:
    if not check_user_can_modify_comment(comment, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=strings.USER_IS_NOT_AUTHOR_OF_ARTICLE,
        )



================================================
FILE: app/api/dependencies/database.py
================================================
from typing import AsyncGenerator, Callable, Type

from asyncpg.connection import Connection
from asyncpg.pool import Pool
from fastapi import Depends
from starlette.requests import Request

from app.db.repositories.base import BaseRepository


def _get_db_pool(request: Request) -> Pool:
    return request.app.state.pool


async def _get_connection_from_pool(
    pool: Pool = Depends(_get_db_pool),
) -> AsyncGenerator[Connection, None]:
    async with pool.acquire() as conn:
        yield conn


def get_repository(
    repo_type: Type[BaseRepository],
) -> Callable[[Connection], BaseRepository]:
    def _get_repo(
        conn: Connection = Depends(_get_connection_from_pool),
    ) -> BaseRepository:
        return repo_type(conn)

    return _get_repo



================================================
FILE: app/api/dependencies/profiles.py
================================================
from typing import Optional

from fastapi import Depends, HTTPException, Path
from starlette.status import HTTP_404_NOT_FOUND

from app.api.dependencies.authentication import get_current_user_authorizer
from app.api.dependencies.database import get_repository
from app.db.errors import EntityDoesNotExist
from app.db.repositories.profiles import ProfilesRepository
from app.models.domain.profiles import Profile
from app.models.domain.users import User
from app.resources import strings


async def get_profile_by_username_from_path(
    username: str = Path(..., min_length=1),
    user: Optional[User] = Depends(get_current_user_authorizer(required=False)),
    profiles_repo: ProfilesRepository = Depends(get_repository(ProfilesRepository)),
) -> Profile:
    try:
        return await profiles_repo.get_profile_by_username(
            username=username,
            requested_user=user,
        )
    except EntityDoesNotExist:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=strings.USER_DOES_NOT_EXIST_ERROR,
        )



================================================
FILE: app/api/errors/__init__.py
================================================
[Empty file]


================================================
FILE: app/api/errors/http_error.py
================================================
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse


async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"errors": [exc.detail]}, status_code=exc.status_code)



================================================
FILE: app/api/errors/validation_error.py
================================================
from typing import Union

from fastapi.exceptions import RequestValidationError
from fastapi.openapi.constants import REF_PREFIX
from fastapi.openapi.utils import validation_error_response_definition
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY


async def http422_error_handler(
    _: Request,
    exc: Union[RequestValidationError, ValidationError],
) -> JSONResponse:
    return JSONResponse(
        {"errors": exc.errors()},
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
    )


validation_error_response_definition["properties"] = {
    "errors": {
        "title": "Errors",
        "type": "array",
        "items": {"$ref": "{0}ValidationError".format(REF_PREFIX)},
    },
}



================================================
FILE: app/api/routes/__init__.py
================================================
[Empty file]


================================================
FILE: app/api/routes/api.py
================================================
from fastapi import APIRouter

from app.api.routes import authentication, comments, profiles, tags, users
from app.api.routes.articles import api as articles

router = APIRouter()
router.include_router(authentication.router, tags=["authentication"], prefix="/users")
router.include_router(users.router, tags=["users"], prefix="/user")
router.include_router(profiles.router, tags=["profiles"], prefix="/profiles")
router.include_router(articles.router, tags=["articles"])
router.include_router(
    comments.router,
    tags=["comments"],
    prefix="/articles/{slug}/comments",
)
router.include_router(tags.router, tags=["tags"], prefix="/tags")



================================================
FILE: app/api/routes/authentication.py
================================================
from fastapi import APIRouter, Body, Depends, HTTPException
from starlette.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST

from app.api.dependencies.database import get_repository
from app.core.config import get_app_settings
from app.core.settings.app import AppSettings
from app.db.errors import EntityDoesNotExist
from app.db.repositories.users import UsersRepository
from app.models.schemas.users import (
    UserInCreate,
    UserInLogin,
    UserInResponse,
    UserWithToken,
)
from app.resources import strings
from app.services import jwt
from app.services.authentication import check_email_is_taken, check_username_is_taken

router = APIRouter()


@router.post("/login", response_model=UserInResponse, name="auth:login")
async def login(
    user_login: UserInLogin = Body(..., embed=True, alias="user"),
    users_repo: UsersRepository = Depends(get_repository(UsersRepository)),
    settings: AppSettings = Depends(get_app_settings),
) -> UserInResponse:
    wrong_login_error = HTTPException(
        status_code=HTTP_400_BAD_REQUEST,
        detail=strings.INCORRECT_LOGIN_INPUT,
    )

    try:
        user = await users_repo.get_user_by_email(email=user_login.email)
    except EntityDoesNotExist as existence_error:
        raise wrong_login_error from existence_error
    
    if not user.check_password(user_login.password):
        raise wrong_login_error
    
    token = jwt.create_access_token_for_user(
        user,
        str(settings.secret_key.get_secret_value()),
    )
    return UserInResponse(
        user=UserWithToken(
            username=user.username,
            email=user.email,
            bio=user.bio,
            image=user.image,
            token=token,
        ),
    )


@router.post(
    "",
    status_code=HTTP_201_CREATED,
    response_model=UserInResponse,
    name="auth:register",
)
async def register(
    user_create: UserInCreate = Body(..., embed=True, alias="user"),
    users_repo: UsersRepository = Depends(get_repository(UsersRepository)),
    settings: AppSettings = Depends(get_app_settings),
) -> UserInResponse:
    if await check_username_is_taken(users_repo, user_create.username):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=strings.USERNAME_TAKEN,
        )

    if await check_email_is_taken(users_repo, user_create.email):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=strings.EMAIL_TAKEN,
        )
    
    user = await users_repo.create_user(**user_create.dict())
    
    token = jwt.create_access_token_for_user(
        user,
        str(settings.secret_key.get_secret_value()),
    )
    return UserInResponse(
        user=UserWithToken(
            username=user.username,
            email=user.email,
            bio=user.bio,
            image=user.image,
            token=token,
        ),
    )



================================================
FILE: app/api/routes/comments.py
================================================
from typing import Optional

from fastapi import APIRouter, Body, Depends, Response
from starlette import status

from app.api.dependencies.articles import get_article_by_slug_from_path
from app.api.dependencies.authentication import get_current_user_authorizer
from app.api.dependencies.comments import (
    check_comment_modification_permissions,
    get_comment_by_id_from_path,
)
from app.api.dependencies.database import get_repository
from app.db.repositories.comments import CommentsRepository
from app.models.domain.articles import Article
from app.models.domain.comments import Comment
from app.models.domain.users import User
from app.models.schemas.comments import (
    CommentInCreate,
    CommentInResponse,
    ListOfCommentsInResponse,
)

router = APIRouter()


@router.get(
    "",
    response_model=ListOfCommentsInResponse,
    name="comments:get-comments-for-article",
)
async def list_comments_for_article(
    article: Article = Depends(get_article_by_slug_from_path),
    user: Optional[User] = Depends(get_current_user_authorizer(required=False)),
    comments_repo: CommentsRepository = Depends(get_repository(CommentsRepository)),
) -> ListOfCommentsInResponse:
    comments = await comments_repo.get_comments_for_article(article=article, user=user)
    return ListOfCommentsInResponse(comments=comments)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CommentInResponse,
    name="comments:create-comment-for-article",
)
async def create_comment_for_article(
    comment_create: CommentInCreate = Body(..., embed=True, alias="comment"),
    article: Article = Depends(get_article_by_slug_from_path),
    user: User = Depends(get_current_user_authorizer()),
    comments_repo: CommentsRepository = Depends(get_repository(CommentsRepository)),
) -> CommentInResponse:
    comment = await comments_repo.create_comment_for_article(
        body=comment_create.body,
        article=article,
        user=user,
    )
    return CommentInResponse(comment=comment)


@router.delete(
    "/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    name="comments:delete-comment-from-article",
    dependencies=[Depends(check_comment_modification_permissions)],
    response_class=Response,
)
async def delete_comment_from_article(
    comment: Comment = Depends(get_comment_by_id_from_path),
    comments_repo: CommentsRepository = Depends(get_repository(CommentsRepository)),
) -> None:
    await comments_repo.delete_comment(comment=comment)



================================================
FILE: app/api/routes/profiles.py
================================================
from fastapi import APIRouter, Depends, HTTPException
from starlette.status import HTTP_400_BAD_REQUEST

from app.api.dependencies.authentication import get_current_user_authorizer
from app.api.dependencies.database import get_repository
from app.api.dependencies.profiles import get_profile_by_username_from_path
from app.db.repositories.profiles import ProfilesRepository
from app.models.domain.profiles import Profile
from app.models.domain.users import User
from app.models.schemas.profiles import ProfileInResponse
from app.resources import strings

router = APIRouter()


@router.get(
    "/{username}",
    response_model=ProfileInResponse,
    name="profiles:get-profile",
)
async def retrieve_profile_by_username(
    profile: Profile = Depends(get_profile_by_username_from_path),
) -> ProfileInResponse:
    return ProfileInResponse(profile=profile)


@router.post(
    "/{username}/follow",
    response_model=ProfileInResponse,
    name="profiles:follow-user",
)
async def follow_for_user(
    profile: Profile = Depends(get_profile_by_username_from_path),
    user: User = Depends(get_current_user_authorizer()),
    profiles_repo: ProfilesRepository = Depends(get_repository(ProfilesRepository)),
) -> ProfileInResponse:
    if user.username == profile.username:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=strings.UNABLE_TO_FOLLOW_YOURSELF,
        )

    if profile.following:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=strings.USER_IS_ALREADY_FOLLOWED,
        )
    
    await profiles_repo.add_user_into_followers(
        target_user=profile,
        requested_user=user,
    )
    
    return ProfileInResponse(profile=profile.copy(update={"following": True}))


@router.delete(
    "/{username}/follow",
    response_model=ProfileInResponse,
    name="profiles:unsubscribe-from-user",
)
async def unsubscribe_from_user(
    profile: Profile = Depends(get_profile_by_username_from_path),
    user: User = Depends(get_current_user_authorizer()),
    profiles_repo: ProfilesRepository = Depends(get_repository(ProfilesRepository)),
) -> ProfileInResponse:
    if user.username == profile.username:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=strings.UNABLE_TO_UNSUBSCRIBE_FROM_YOURSELF,
        )

    if not profile.following:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=strings.USER_IS_NOT_FOLLOWED,
        )
    
    await profiles_repo.remove_user_from_followers(
        target_user=profile,
        requested_user=user,
    )
    
    return ProfileInResponse(profile=profile.copy(update={"following": False}))



================================================
FILE: app/api/routes/tags.py
================================================
from fastapi import APIRouter, Depends

from app.api.dependencies.database import get_repository
from app.db.repositories.tags import TagsRepository
from app.models.schemas.tags import TagsInList

router = APIRouter()


@router.get("", response_model=TagsInList, name="tags:get-all")
async def get_all_tags(
    tags_repo: TagsRepository = Depends(get_repository(TagsRepository)),
) -> TagsInList:
    tags = await tags_repo.get_all_tags()
    return TagsInList(tags=tags)



================================================
FILE: app/api/routes/users.py
================================================
from fastapi import APIRouter, Body, Depends, HTTPException
from starlette.status import HTTP_400_BAD_REQUEST

from app.api.dependencies.authentication import get_current_user_authorizer
from app.api.dependencies.database import get_repository
from app.core.config import get_app_settings
from app.core.settings.app import AppSettings
from app.db.repositories.users import UsersRepository
from app.models.domain.users import User
from app.models.schemas.users import UserInResponse, UserInUpdate, UserWithToken
from app.resources import strings
from app.services import jwt
from app.services.authentication import check_email_is_taken, check_username_is_taken

router = APIRouter()


@router.get("", response_model=UserInResponse, name="users:get-current-user")
async def retrieve_current_user(
    user: User = Depends(get_current_user_authorizer()),
    settings: AppSettings = Depends(get_app_settings),
) -> UserInResponse:
    token = jwt.create_access_token_for_user(
        user,
        str(settings.secret_key.get_secret_value()),
    )
    return UserInResponse(
        user=UserWithToken(
            username=user.username,
            email=user.email,
            bio=user.bio,
            image=user.image,
            token=token,
        ),
    )


@router.put("", response_model=UserInResponse, name="users:update-current-user")
async def update_current_user(
    user_update: UserInUpdate = Body(..., embed=True, alias="user"),
    current_user: User = Depends(get_current_user_authorizer()),
    users_repo: UsersRepository = Depends(get_repository(UsersRepository)),
    settings: AppSettings = Depends(get_app_settings),
) -> UserInResponse:
    if user_update.username and user_update.username != current_user.username:
        if await check_username_is_taken(users_repo, user_update.username):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=strings.USERNAME_TAKEN,
            )

    if user_update.email and user_update.email != current_user.email:
        if await check_email_is_taken(users_repo, user_update.email):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=strings.EMAIL_TAKEN,
            )
    
    user = await users_repo.update_user(user=current_user, **user_update.dict())
    
    token = jwt.create_access_token_for_user(
        user,
        str(settings.secret_key.get_secret_value()),
    )
    return UserInResponse(
        user=UserWithToken(
            username=user.username,
            email=user.email,
            bio=user.bio,
            image=user.image,
            token=token,
        ),
    )



================================================
FILE: app/api/routes/articles/__init__.py
================================================
[Empty file]


================================================
FILE: app/api/routes/articles/api.py
================================================
from fastapi import APIRouter

from app.api.routes.articles import articles_common, articles_resource

router = APIRouter()

router.include_router(articles_common.router, prefix="/articles")
router.include_router(articles_resource.router, prefix="/articles")



================================================
FILE: app/api/routes/articles/articles_common.py
================================================
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status

from app.api.dependencies.articles import get_article_by_slug_from_path
from app.api.dependencies.authentication import get_current_user_authorizer
from app.api.dependencies.database import get_repository
from app.db.repositories.articles import ArticlesRepository
from app.models.domain.articles import Article
from app.models.domain.users import User
from app.models.schemas.articles import (
    DEFAULT_ARTICLES_LIMIT,
    DEFAULT_ARTICLES_OFFSET,
    ArticleForResponse,
    ArticleInResponse,
    ListOfArticlesInResponse,
)
from app.resources import strings

router = APIRouter()


@router.get(
    "/feed",
    response_model=ListOfArticlesInResponse,
    name="articles:get-user-feed-articles",
)
async def get_articles_for_user_feed(
    limit: int = Query(DEFAULT_ARTICLES_LIMIT, ge=1),
    offset: int = Query(DEFAULT_ARTICLES_OFFSET, ge=0),
    user: User = Depends(get_current_user_authorizer()),
    articles_repo: ArticlesRepository = Depends(get_repository(ArticlesRepository)),
) -> ListOfArticlesInResponse:
    articles = await articles_repo.get_articles_for_user_feed(
        user=user,
        limit=limit,
        offset=offset,
    )
    articles_for_response = [
        ArticleForResponse(**article.dict()) for article in articles
    ]
    return ListOfArticlesInResponse(
        articles=articles_for_response,
        articles_count=len(articles),
    )


@router.post(
    "/{slug}/favorite",
    response_model=ArticleInResponse,
    name="articles:mark-article-favorite",
)
async def mark_article_as_favorite(
    article: Article = Depends(get_article_by_slug_from_path),
    user: User = Depends(get_current_user_authorizer()),
    articles_repo: ArticlesRepository = Depends(get_repository(ArticlesRepository)),
) -> ArticleInResponse:
    if not article.favorited:
        await articles_repo.add_article_into_favorites(article=article, user=user)

        return ArticleInResponse(
            article=ArticleForResponse.from_orm(
                article.copy(
                    update={
                        "favorited": True,
                        "favorites_count": article.favorites_count + 1,
                    },
                ),
            ),
        )
    
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=strings.ARTICLE_IS_ALREADY_FAVORITED,
    )


@router.delete(
    "/{slug}/favorite",
    response_model=ArticleInResponse,
    name="articles:unmark-article-favorite",
)
async def remove_article_from_favorites(
    article: Article = Depends(get_article_by_slug_from_path),
    user: User = Depends(get_current_user_authorizer()),
    articles_repo: ArticlesRepository = Depends(get_repository(ArticlesRepository)),
) -> ArticleInResponse:
    if article.favorited:
        await articles_repo.remove_article_from_favorites(article=article, user=user)

        return ArticleInResponse(
            article=ArticleForResponse.from_orm(
                article.copy(
                    update={
                        "favorited": False,
                        "favorites_count": article.favorites_count - 1,
                    },
                ),
            ),
        )
    
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=strings.ARTICLE_IS_NOT_FAVORITED,
    )



================================================
FILE: app/api/routes/articles/articles_resource.py
================================================
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from starlette import status

from app.api.dependencies.articles import (
    check_article_modification_permissions,
    get_article_by_slug_from_path,
    get_articles_filters,
)
from app.api.dependencies.authentication import get_current_user_authorizer
from app.api.dependencies.database import get_repository
from app.db.repositories.articles import ArticlesRepository
from app.models.domain.articles import Article
from app.models.domain.users import User
from app.models.schemas.articles import (
    ArticleForResponse,
    ArticleInCreate,
    ArticleInResponse,
    ArticleInUpdate,
    ArticlesFilters,
    ListOfArticlesInResponse,
)
from app.resources import strings
from app.services.articles import check_article_exists, get_slug_for_article

router = APIRouter()


@router.get("", response_model=ListOfArticlesInResponse, name="articles:list-articles")
async def list_articles(
    articles_filters: ArticlesFilters = Depends(get_articles_filters),
    user: Optional[User] = Depends(get_current_user_authorizer(required=False)),
    articles_repo: ArticlesRepository = Depends(get_repository(ArticlesRepository)),
) -> ListOfArticlesInResponse:
    articles = await articles_repo.filter_articles(
        tag=articles_filters.tag,
        author=articles_filters.author,
        favorited=articles_filters.favorited,
        limit=articles_filters.limit,
        offset=articles_filters.offset,
        requested_user=user,
    )
    articles_for_response = [
        ArticleForResponse.from_orm(article) for article in articles
    ]
    return ListOfArticlesInResponse(
        articles=articles_for_response,
        articles_count=len(articles),
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ArticleInResponse,
    name="articles:create-article",
)
async def create_new_article(
    article_create: ArticleInCreate = Body(..., embed=True, alias="article"),
    user: User = Depends(get_current_user_authorizer()),
    articles_repo: ArticlesRepository = Depends(get_repository(ArticlesRepository)),
) -> ArticleInResponse:
    slug = get_slug_for_article(article_create.title)
    if await check_article_exists(articles_repo, slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=strings.ARTICLE_ALREADY_EXISTS,
        )

    article = await articles_repo.create_article(
        slug=slug,
        title=article_create.title,
        description=article_create.description,
        body=article_create.body,
        author=user,
        tags=article_create.tags,
    )
    return ArticleInResponse(article=ArticleForResponse.from_orm(article))


@router.get("/{slug}", response_model=ArticleInResponse, name="articles:get-article")
async def retrieve_article_by_slug(
    article: Article = Depends(get_article_by_slug_from_path),
) -> ArticleInResponse:
    return ArticleInResponse(article=ArticleForResponse.from_orm(article))


@router.put(
    "/{slug}",
    response_model=ArticleInResponse,
    name="articles:update-article",
    dependencies=[Depends(check_article_modification_permissions)],
)
async def update_article_by_slug(
    article_update: ArticleInUpdate = Body(..., embed=True, alias="article"),
    current_article: Article = Depends(get_article_by_slug_from_path),
    articles_repo: ArticlesRepository = Depends(get_repository(ArticlesRepository)),
) -> ArticleInResponse:
    slug = get_slug_for_article(article_update.title) if article_update.title else None
    article = await articles_repo.update_article(
        article=current_article,
        slug=slug,
        **article_update.dict(),
    )
    return ArticleInResponse(article=ArticleForResponse.from_orm(article))


@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    name="articles:delete-article",
    dependencies=[Depends(check_article_modification_permissions)],
    response_class=Response,
)
async def delete_article_by_slug(
    article: Article = Depends(get_article_by_slug_from_path),
    articles_repo: ArticlesRepository = Depends(get_repository(ArticlesRepository)),
) -> None:
    await articles_repo.delete_article(article=article)



================================================
FILE: app/core/__init__.py
================================================
[Empty file]


================================================
FILE: app/core/config.py
================================================
from functools import lru_cache
from typing import Dict, Type

from app.core.settings.app import AppSettings
from app.core.settings.base import AppEnvTypes, BaseAppSettings
from app.core.settings.development import DevAppSettings
from app.core.settings.production import ProdAppSettings
from app.core.settings.test import TestAppSettings

environments: Dict[AppEnvTypes, Type[AppSettings]] = {
    AppEnvTypes.dev: DevAppSettings,
    AppEnvTypes.prod: ProdAppSettings,
    AppEnvTypes.test: TestAppSettings,
}


@lru_cache
def get_app_settings() -> AppSettings:
    app_env = BaseAppSettings().app_env
    config = environments[app_env]
    return config()



================================================
FILE: app/core/events.py
================================================
from typing import Callable

from fastapi import FastAPI
from loguru import logger

from app.core.settings.app import AppSettings
from app.db.events import close_db_connection, connect_to_db


def create_start_app_handler(
    app: FastAPI,
    settings: AppSettings,
) -> Callable:  # type: ignore
    async def start_app() -> None:
        await connect_to_db(app, settings)

    return start_app


def create_stop_app_handler(app: FastAPI) -> Callable:  # type: ignore
    @logger.catch
    async def stop_app() -> None:
        await close_db_connection(app)

    return stop_app



================================================
FILE: app/core/logging.py
================================================
import logging
from types import FrameType
from typing import cast

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = str(record.levelno)

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:  # noqa: WPS609
            frame = cast(FrameType, frame.f_back)
            depth += 1
    
        logger.opt(depth=depth, exception=record.exc_info).log(
            level,
            record.getMessage(),
        )



================================================
FILE: app/core/settings/__init__.py
================================================
[Empty file]


================================================
FILE: app/core/settings/app.py
================================================
import logging
import sys
from typing import Any, Dict, List, Tuple

from loguru import logger
from pydantic import PostgresDsn, SecretStr

from app.core.logging import InterceptHandler
from app.core.settings.base import BaseAppSettings


class AppSettings(BaseAppSettings):
    debug: bool = False
    docs_url: str = "/docs"
    openapi_prefix: str = ""
    openapi_url: str = "/openapi.json"
    redoc_url: str = "/redoc"
    title: str = "FastAPI example application"
    version: str = "0.0.0"

    database_url: PostgresDsn
    max_connection_count: int = 10
    min_connection_count: int = 10
    
    secret_key: SecretStr
    
    api_prefix: str = "/api"
    
    jwt_token_prefix: str = "Token"
    
    allowed_hosts: List[str] = ["*"]
    
    logging_level: int = logging.INFO
    loggers: Tuple[str, str] = ("uvicorn.asgi", "uvicorn.access")
    
    class Config:
        validate_assignment = True
    
    @property
    def fastapi_kwargs(self) -> Dict[str, Any]:
        return {
            "debug": self.debug,
            "docs_url": self.docs_url,
            "openapi_prefix": self.openapi_prefix,
            "openapi_url": self.openapi_url,
            "redoc_url": self.redoc_url,
            "title": self.title,
            "version": self.version,
        }
    
    def configure_logging(self) -> None:
        logging.getLogger().handlers = [InterceptHandler()]
        for logger_name in self.loggers:
            logging_logger = logging.getLogger(logger_name)
            logging_logger.handlers = [InterceptHandler(level=self.logging_level)]
    
        logger.configure(handlers=[{"sink": sys.stderr, "level": self.logging_level}])



================================================
FILE: app/core/settings/base.py
================================================
from enum import Enum

from pydantic import BaseSettings


class AppEnvTypes(Enum):
    prod: str = "prod"
    dev: str = "dev"
    test: str = "test"


class BaseAppSettings(BaseSettings):
    app_env: AppEnvTypes = AppEnvTypes.prod

    class Config:
        env_file = ".env"



================================================
FILE: app/core/settings/development.py
================================================
import logging

from app.core.settings.app import AppSettings


class DevAppSettings(AppSettings):
    debug: bool = True

    title: str = "Dev FastAPI example application"
    
    logging_level: int = logging.DEBUG
    
    class Config(AppSettings.Config):
        env_file = ".env"



================================================
FILE: app/core/settings/production.py
================================================
from app.core.settings.app import AppSettings


class ProdAppSettings(AppSettings):
    class Config(AppSettings.Config):
        env_file = "prod.env"



================================================
FILE: app/core/settings/test.py
================================================
import logging

from pydantic import PostgresDsn, SecretStr

from app.core.settings.app import AppSettings


class TestAppSettings(AppSettings):
    debug: bool = True

    title: str = "Test FastAPI example application"
    
    secret_key: SecretStr = SecretStr("test_secret")
    
    database_url: PostgresDsn
    max_connection_count: int = 5
    min_connection_count: int = 5
    
    logging_level: int = logging.DEBUG



================================================
FILE: app/db/__init__.py
================================================
[Empty file]


================================================
FILE: app/db/errors.py
================================================
class EntityDoesNotExist(Exception):
    """Raised when entity was not found in database."""



================================================
FILE: app/db/events.py
================================================
import asyncpg
from fastapi import FastAPI
from loguru import logger

from app.core.settings.app import AppSettings


async def connect_to_db(app: FastAPI, settings: AppSettings) -> None:
    logger.info("Connecting to PostgreSQL")

    app.state.pool = await asyncpg.create_pool(
        str(settings.database_url),
        min_size=settings.min_connection_count,
        max_size=settings.max_connection_count,
    )
    
    logger.info("Connection established")


async def close_db_connection(app: FastAPI) -> None:
    logger.info("Closing connection to database")

    await app.state.pool.close()
    
    logger.info("Connection closed")



================================================
FILE: app/db/migrations/env.py
================================================
import pathlib
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.append(str(pathlib.Path(__file__).resolve().parents[3]))

from app.core.config import get_app_settings  # isort:skip

SETTINGS = get_app_settings()
DATABASE_URL = SETTINGS.database_url

config = context.config

fileConfig(config.config_file_name)  # type: ignore

target_metadata = None

config.set_main_option("sqlalchemy.url", str(DATABASE_URL))


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
    
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()



================================================
FILE: app/db/migrations/script.py.mako
================================================
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}



================================================
FILE: app/db/migrations/versions/fdf8821871d7_main_tables.py
================================================
"""main tables

Revision ID: fdf8821871d7
Revises:
Create Date: 2019-09-22 01:36:44.791880

"""
from typing import Tuple

import sqlalchemy as sa
from alembic import op
from sqlalchemy import func

revision = "fdf8821871d7"
down_revision = None
branch_labels = None
depends_on = None


def create_updated_at_trigger() -> None:
    op.execute(
        """
    CREATE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS
    $$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $$ language 'plpgsql';
    """
    )


def timestamps() -> Tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.current_timestamp(),
        ),
    )


def create_users_table() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.Text, unique=True, nullable=False, index=True),
        sa.Column("email", sa.Text, unique=True, nullable=False, index=True),
        sa.Column("salt", sa.Text, nullable=False),
        sa.Column("hashed_password", sa.Text),
        sa.Column("bio", sa.Text, nullable=False, server_default=""),
        sa.Column("image", sa.Text),
        *timestamps(),
    )
    op.execute(
        """
        CREATE TRIGGER update_user_modtime
            BEFORE UPDATE
            ON users
            FOR EACH ROW
        EXECUTE PROCEDURE update_updated_at_column();
        """
    )


def create_followers_to_followings_table() -> None:
    op.create_table(
        "followers_to_followings",
        sa.Column(
            "follower_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "following_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_primary_key(
        "pk_followers_to_followings",
        "followers_to_followings",
        ["follower_id", "following_id"],
    )


def create_articles_table() -> None:
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.Text, unique=True, nullable=False, index=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "author_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        *timestamps(),
    )
    op.execute(
        """
        CREATE TRIGGER update_article_modtime
            BEFORE UPDATE
            ON articles
            FOR EACH ROW
        EXECUTE PROCEDURE update_updated_at_column();
        """
    )


def create_tags_table() -> None:
    op.create_table("tags", sa.Column("tag", sa.Text, primary_key=True))


def create_articles_to_tags_table() -> None:
    op.create_table(
        "articles_to_tags",
        sa.Column(
            "article_id",
            sa.Integer,
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tag",
            sa.Text,
            sa.ForeignKey("tags.tag", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_primary_key(
        "pk_articles_to_tags", "articles_to_tags", ["article_id", "tag"]
    )


def create_favorites_table() -> None:
    op.create_table(
        "favorites",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "article_id",
            sa.Integer,
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_primary_key("pk_favorites", "favorites", ["user_id", "article_id"])


def create_commentaries_table() -> None:
    op.create_table(
        "commentaries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "author_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "article_id",
            sa.Integer,
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *timestamps(),
    )
    op.execute(
        """
        CREATE TRIGGER update_comment_modtime
            BEFORE UPDATE
            ON commentaries
            FOR EACH ROW
        EXECUTE PROCEDURE update_updated_at_column();
        """
    )


def upgrade() -> None:
    create_updated_at_trigger()
    create_users_table()
    create_followers_to_followings_table()
    create_articles_table()
    create_tags_table()
    create_articles_to_tags_table()
    create_favorites_table()
    create_commentaries_table()


def downgrade() -> None:
    op.drop_table("commentaries")
    op.drop_table("favorites")
    op.drop_table("articles_to_tags")
    op.drop_table("tags")
    op.drop_table("articles")
    op.drop_table("followers_to_followings")
    op.drop_table("users")
    op.execute("DROP FUNCTION update_updated_at_column")



================================================
FILE: app/db/queries/__init__.py
================================================
[Empty file]


================================================
FILE: app/db/queries/queries.py
================================================
import pathlib

import aiosql

queries = aiosql.from_path(pathlib.Path(__file__).parent / "sql", "asyncpg")



================================================
FILE: app/db/queries/queries.pyi
================================================
"""Typings for queries generated by aiosql"""

from typing import Dict, Optional, Sequence

from asyncpg import Connection, Record

class TagsQueriesMixin:
    async def get_all_tags(self, conn: Connection) -> Record: ...
    async def create_new_tags(
        self, conn: Connection, tags: Sequence[Dict[str, str]]
    ) -> None: ...

class UsersQueriesMixin:
    async def get_user_by_email(self, conn: Connection, *, email: str) -> Record: ...
    async def get_user_by_username(
        self, conn: Connection, *, username: str
    ) -> Record: ...
    async def create_new_user(
        self,
        conn: Connection,
        *,
        username: str,
        email: str,
        salt: str,
        hashed_password: str
    ) -> Record: ...
    async def update_user_by_username(
        self,
        conn: Connection,
        *,
        username: str,
        new_username: str,
        new_email: str,
        new_salt: str,
        new_password: str,
        new_bio: Optional[str],
        new_image: Optional[str]
    ) -> Record: ...

class ProfilesQueriesMixin:
    async def is_user_following_for_another(
        self, conn: Connection, *, follower_username: str, following_username: str
    ) -> Record: ...
    async def subscribe_user_to_another(
        self, conn: Connection, *, follower_username: str, following_username: str
    ) -> None: ...
    async def unsubscribe_user_from_another(
        self, conn: Connection, *, follower_username: str, following_username: str
    ) -> None: ...

class CommentsQueriesMixin:
    async def get_comments_for_article_by_slug(
        self, conn: Connection, *, slug: str
    ) -> Record: ...
    async def get_comment_by_id_and_slug(
        self, conn: Connection, *, comment_id: int, article_slug: str
    ) -> Record: ...
    async def create_new_comment(
        self, conn: Connection, *, body: str, article_slug: str, author_username: str
    ) -> Record: ...
    async def delete_comment_by_id(
        self, conn: Connection, *, comment_id: int, author_username: str
    ) -> None: ...

class ArticlesQueriesMixin:
    async def add_article_to_favorites(
        self, conn: Connection, *, username: str, slug: str
    ) -> None: ...
    async def remove_article_from_favorites(
        self, conn: Connection, *, username: str, slug: str
    ) -> None: ...
    async def is_article_in_favorites(
        self, conn: Connection, *, username: str, slug: str
    ) -> Record: ...
    async def get_favorites_count_for_article(
        self, conn: Connection, *, slug: str
    ) -> Record: ...
    async def get_tags_for_article_by_slug(
        self, conn: Connection, *, slug: str
    ) -> Record: ...
    async def get_article_by_slug(self, conn: Connection, *, slug: str) -> Record: ...
    async def create_new_article(
        self,
        conn: Connection,
        *,
        slug: str,
        title: str,
        description: str,
        body: str,
        author_username: str
    ) -> Record: ...
    async def add_tags_to_article(
        self, conn: Connection, tags_slugs: Sequence[Dict[str, str]]
    ) -> None: ...
    async def update_article(
        self,
        conn: Connection,
        *,
        slug: str,
        author_username: str,
        new_slug: str,
        new_title: str,
        new_body: str,
        new_description: str
    ) -> Record: ...
    async def delete_article(
        self, conn: Connection, *, slug: str, author_username: str
    ) -> None: ...
    async def get_articles_for_feed(
        self, conn: Connection, *, follower_username: str, limit: int, offset: int
    ) -> Record: ...

class Queries(
    TagsQueriesMixin,
    UsersQueriesMixin,
    ProfilesQueriesMixin,
    CommentsQueriesMixin,
    ArticlesQueriesMixin,
): ...

queries: Queries



================================================
FILE: app/db/queries/tables.py
================================================
from datetime import datetime
from typing import Optional

from pypika import Parameter as CommonParameter, Query, Table


class Parameter(CommonParameter):
    def __init__(self, count: int) -> None:
        super().__init__("${0}".format(count))


class TypedTable(Table):
    __table__ = ""

    def __init__(
        self,
        name: Optional[str] = None,
        schema: Optional[str] = None,
        alias: Optional[str] = None,
        query_cls: Optional[Query] = None,
    ) -> None:
        if name is None:
            if self.__table__:
                name = self.__table__
            else:
                name = self.__class__.__name__
    
        super().__init__(name, schema, alias, query_cls)


class Users(TypedTable):
    __table__ = "users"

    id: int
    username: str


class Articles(TypedTable):
    __table__ = "articles"

    id: int
    slug: str
    title: str
    description: str
    body: str
    author_id: int
    created_at: datetime
    updated_at: datetime


class Tags(TypedTable):
    __table__ = "tags"

    tag: str


class ArticlesToTags(TypedTable):
    __table__ = "articles_to_tags"

    article_id: int
    tag: str


class Favorites(TypedTable):
    __table__ = "favorites"

    article_id: int
    user_id: int


users = Users()
articles = Articles()
tags = Tags()
articles_to_tags = ArticlesToTags()
favorites = Favorites()



================================================
FILE: app/db/queries/sql/articles.sql
================================================
-- name: add-article-to-favorites!
INSERT INTO favorites (user_id, article_id)
VALUES ((SELECT id FROM users WHERE username = :username),
        (SELECT id FROM articles WHERE slug = :slug))
ON CONFLICT DO NOTHING;


-- name: remove-article-from-favorites!
DELETE
FROM favorites
WHERE user_id = (SELECT id FROM users WHERE username = :username)
  AND article_id = (SELECT id FROM articles WHERE slug = :slug);


-- name: is-article-in-favorites^
SELECT CASE WHEN count(user_id) > 0 THEN TRUE ELSE FALSE END AS favorited
FROM favorites
WHERE user_id = (SELECT id FROM users WHERE username = :username)
  AND article_id = (SELECT id FROM articles WHERE slug = :slug);


-- name: get-favorites-count-for-article^
SELECT count(*) as favorites_count
FROM favorites
WHERE article_id = (SELECT id FROM articles WHERE slug = :slug);


-- name: get-tags-for-article-by-slug
SELECT t.tag
FROM tags t
         INNER JOIN articles_to_tags att ON
        t.tag = att.tag
        AND
        att.article_id = (SELECT id FROM articles WHERE slug = :slug);


-- name: get-article-by-slug^
SELECT id,
       slug,
       title,
       description,
       body,
       created_at,
       updated_at,
       (SELECT username FROM users WHERE id = author_id) AS author_username
FROM articles
WHERE slug = :slug
LIMIT 1;


-- name: create-new-article<!
WITH author_subquery AS (
    SELECT id, username
    FROM users
    WHERE username = :author_username
)
INSERT
INTO articles (slug, title, description, body, author_id)
VALUES (:slug, :title, :description, :body, (SELECT id FROM author_subquery))
RETURNING
    id,
    slug,
    title,
    description,
    body,
        (SELECT username FROM author_subquery) as author_username,
    created_at,
    updated_at;


-- name: add-tags-to-article*!
INSERT INTO articles_to_tags (article_id, tag)
VALUES ((SELECT id FROM articles WHERE slug = :slug),
        (SELECT tag FROM tags WHERE tag = :tag))
ON CONFLICT DO NOTHING;


-- name: update-article<!
UPDATE articles
SET slug        = :new_slug,
    title       = :new_title,
    body        = :new_body,
    description = :new_description
WHERE slug = :slug
  AND author_id = (SELECT id FROM users WHERE username = :author_username)
RETURNING updated_at;


-- name: delete-article!
DELETE
FROM articles
WHERE slug = :slug
  AND author_id = (SELECT id FROM users WHERE username = :author_username);


-- name: get-articles-for-feed
SELECT a.id,
       a.slug,
       a.title,
       a.description,
       a.body,
       a.created_at,
       a.updated_at,
       (
           SELECT username
           FROM users
           WHERE id = a.author_id
       ) AS author_username
FROM articles a
         INNER JOIN followers_to_followings f ON
        f.following_id = a.author_id AND
        f.follower_id = (SELECT id FROM users WHERE username = :follower_username)
ORDER BY a.created_at
LIMIT :limit
OFFSET
:offset;



================================================
FILE: app/db/queries/sql/comments.sql
================================================
-- name: get-comments-for-article-by-slug
SELECT c.id,
       c.body,
       c.created_at,
       c.updated_at,
       (SELECT username FROM users WHERE id = c.author_id) as author_username
FROM commentaries c
         INNER JOIN articles a ON c.article_id = a.id AND (a.slug = :slug);

-- name: get-comment-by-id-and-slug^
SELECT c.id,
       c.body,
       c.created_at,
       c.updated_at,
       (SELECT username FROM users WHERE id = c.author_id) as author_username
FROM commentaries c
         INNER JOIN articles a ON c.article_id = a.id AND (a.slug = :article_slug)
WHERE c.id = :comment_id;

-- name: create-new-comment<!
WITH users_subquery AS (
        (SELECT id, username FROM users WHERE username = :author_username)
)
INSERT
INTO commentaries (body, author_id, article_id)
VALUES (:body,
        (SELECT id FROM users_subquery),
        (SELECT id FROM articles WHERE slug = :article_slug))
RETURNING
    id,
    body,
        (SELECT username FROM users_subquery) AS author_username,
    created_at,
    updated_at;

-- name: delete-comment-by-id!
DELETE
FROM commentaries
WHERE id = :comment_id
  AND author_id = (SELECT id FROM users WHERE username = :author_username);



================================================
FILE: app/db/queries/sql/profiles.sql
================================================
-- name: is-user-following-for-another^
SELECT CASE
           WHEN following_id IS NULL THEN
               FALSE
           ELSE
               TRUE
           END AS is_following
FROM users u
         LEFT OUTER JOIN followers_to_followings f ON u.id = f.follower_id
    AND f.following_id = (
        SELECT id
        FROM users
        WHERE username = :following_username)
WHERE u.username = :follower_username
LIMIT 1;


-- name: subscribe-user-to-another!
INSERT INTO followers_to_followings (follower_id, following_id)
VALUES ((
            SELECT id
            FROM users
            WHERE username = :follower_username), (
            SELECT id
            FROM users
            WHERE username = :following_username));

-- name: unsubscribe-user-from-another!
DELETE
FROM followers_to_followings
WHERE follower_id = (
    SELECT id
    FROM users
    WHERE username = :follower_username)
  AND following_id = (
    SELECT id
    FROM users
    WHERE username = :following_username);



================================================
FILE: app/db/queries/sql/tags.sql
================================================
-- name: get-all-tags
SELECT tag
FROM tags;


-- name: create-new-tags*!
INSERT INTO tags (tag)
VALUES (:tag)
ON CONFLICT DO NOTHING;



================================================
FILE: app/db/queries/sql/users.sql
================================================
-- name: get-user-by-email^
SELECT id,
       username,
       email,
       salt,
       hashed_password,
       bio,
       image,
       created_at,
       updated_at
FROM users
WHERE email = :email
LIMIT 1;


-- name: get-user-by-username^
SELECT id,
       username,
       email,
       salt,
       hashed_password,
       bio,
       image,
       created_at,
       updated_at
FROM users
WHERE username = :username
LIMIT 1;


-- name: create-new-user<!
INSERT INTO users (username, email, salt, hashed_password)
VALUES (:username, :email, :salt, :hashed_password)
RETURNING
    id, created_at, updated_at;


-- name: update-user-by-username<!
UPDATE
    users
SET username        = :new_username,
    email           = :new_email,
    salt            = :new_salt,
    hashed_password = :new_password,
    bio             = :new_bio,
    image           = :new_image
WHERE username = :username
RETURNING
    updated_at;



================================================
FILE: app/db/repositories/__init__.py
================================================
[Empty file]


================================================
FILE: app/db/repositories/articles.py
================================================
from typing import List, Optional, Sequence, Union

from asyncpg import Connection, Record
from pypika import Query

from app.db.errors import EntityDoesNotExist
from app.db.queries.queries import queries
from app.db.queries.tables import (
    Parameter,
    articles,
    articles_to_tags,
    favorites,
    tags as tags_table,
    users,
)
from app.db.repositories.base import BaseRepository
from app.db.repositories.profiles import ProfilesRepository
from app.db.repositories.tags import TagsRepository
from app.models.domain.articles import Article
from app.models.domain.users import User

AUTHOR_USERNAME_ALIAS = "author_username"
SLUG_ALIAS = "slug"

CAMEL_OR_SNAKE_CASE_TO_WORDS = r"^[a-z\d_\-]+|[A-Z\d_\-][^A-Z\d_\-]*"


class ArticlesRepository(BaseRepository):  # noqa: WPS214
    def __init__(self, conn: Connection) -> None:
        super().__init__(conn)
        self._profiles_repo = ProfilesRepository(conn)
        self._tags_repo = TagsRepository(conn)

    async def create_article(  # noqa: WPS211
        self,
        *,
        slug: str,
        title: str,
        description: str,
        body: str,
        author: User,
        tags: Optional[Sequence[str]] = None,
    ) -> Article:
        async with self.connection.transaction():
            article_row = await queries.create_new_article(
                self.connection,
                slug=slug,
                title=title,
                description=description,
                body=body,
                author_username=author.username,
            )
    
            if tags:
                await self._tags_repo.create_tags_that_dont_exist(tags=tags)
                await self._link_article_with_tags(slug=slug, tags=tags)
    
        return await self._get_article_from_db_record(
            article_row=article_row,
            slug=slug,
            author_username=article_row[AUTHOR_USERNAME_ALIAS],
            requested_user=author,
        )
    
    async def update_article(  # noqa: WPS211
        self,
        *,
        article: Article,
        slug: Optional[str] = None,
        title: Optional[str] = None,
        body: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Article:
        updated_article = article.copy(deep=True)
        updated_article.slug = slug or updated_article.slug
        updated_article.title = title or article.title
        updated_article.body = body or article.body
        updated_article.description = description or article.description
    
        async with self.connection.transaction():
            updated_article.updated_at = await queries.update_article(
                self.connection,
                slug=article.slug,
                author_username=article.author.username,
                new_slug=updated_article.slug,
                new_title=updated_article.title,
                new_body=updated_article.body,
                new_description=updated_article.description,
            )
    
        return updated_article
    
    async def delete_article(self, *, article: Article) -> None:
        async with self.connection.transaction():
            await queries.delete_article(
                self.connection,
                slug=article.slug,
                author_username=article.author.username,
            )
    
    async def filter_articles(  # noqa: WPS211
        self,
        *,
        tag: Optional[str] = None,
        author: Optional[str] = None,
        favorited: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        requested_user: Optional[User] = None,
    ) -> List[Article]:
        query_params: List[Union[str, int]] = []
        query_params_count = 0
    
        # fmt: off
        query = Query.from_(
            articles,
        ).select(
            articles.id,
            articles.slug,
            articles.title,
            articles.description,
            articles.body,
            articles.created_at,
            articles.updated_at,
            Query.from_(
                users,
            ).where(
                users.id == articles.author_id,
            ).select(
                users.username,
            ).as_(
                AUTHOR_USERNAME_ALIAS,
            ),
        )
        # fmt: on
    
        if tag:
            query_params.append(tag)
            query_params_count += 1
    
            # fmt: off
            query = query.join(
                articles_to_tags,
            ).on(
                (articles.id == articles_to_tags.article_id) & (
                    articles_to_tags.tag == Query.from_(
                        tags_table,
                    ).where(
                        tags_table.tag == Parameter(query_params_count),
                    ).select(
                        tags_table.tag,
                    )
                ),
            )
            # fmt: on
    
        if author:
            query_params.append(author)
            query_params_count += 1
    
            # fmt: off
            query = query.join(
                users,
            ).on(
                (articles.author_id == users.id) & (
                    users.id == Query.from_(
                        users,
                    ).where(
                        users.username == Parameter(query_params_count),
                    ).select(
                        users.id,
                    )
                ),
            )
            # fmt: on
    
        if favorited:
            query_params.append(favorited)
            query_params_count += 1
    
            # fmt: off
            query = query.join(
                favorites,
            ).on(
                (articles.id == favorites.article_id) & (
                    favorites.user_id == Query.from_(
                        users,
                    ).where(
                        users.username == Parameter(query_params_count),
                    ).select(
                        users.id,
                    )
                ),
            )
            # fmt: on
    
        query = query.limit(Parameter(query_params_count + 1)).offset(
            Parameter(query_params_count + 2),
        )
        query_params.extend([limit, offset])
    
        articles_rows = await self.connection.fetch(query.get_sql(), *query_params)
    
        return [
            await self._get_article_from_db_record(
                article_row=article_row,
                slug=article_row[SLUG_ALIAS],
                author_username=article_row[AUTHOR_USERNAME_ALIAS],
                requested_user=requested_user,
            )
            for article_row in articles_rows
        ]
    
    async def get_articles_for_user_feed(
        self,
        *,
        user: User,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Article]:
        articles_rows = await queries.get_articles_for_feed(
            self.connection,
            follower_username=user.username,
            limit=limit,
            offset=offset,
        )
        return [
            await self._get_article_from_db_record(
                article_row=article_row,
                slug=article_row[SLUG_ALIAS],
                author_username=article_row[AUTHOR_USERNAME_ALIAS],
                requested_user=user,
            )
            for article_row in articles_rows
        ]
    
    async def get_article_by_slug(
        self,
        *,
        slug: str,
        requested_user: Optional[User] = None,
    ) -> Article:
        article_row = await queries.get_article_by_slug(self.connection, slug=slug)
        if article_row:
            return await self._get_article_from_db_record(
                article_row=article_row,
                slug=article_row[SLUG_ALIAS],
                author_username=article_row[AUTHOR_USERNAME_ALIAS],
                requested_user=requested_user,
            )
    
        raise EntityDoesNotExist("article with slug {0} does not exist".format(slug))
    
    async def get_tags_for_article_by_slug(self, *, slug: str) -> List[str]:
        tag_rows = await queries.get_tags_for_article_by_slug(
            self.connection,
            slug=slug,
        )
        return [row["tag"] for row in tag_rows]
    
    async def get_favorites_count_for_article_by_slug(self, *, slug: str) -> int:
        return (
            await queries.get_favorites_count_for_article(self.connection, slug=slug)
        )["favorites_count"]
    
    async def is_article_favorited_by_user(self, *, slug: str, user: User) -> bool:
        return (
            await queries.is_article_in_favorites(
                self.connection,
                username=user.username,
                slug=slug,
            )
        )["favorited"]
    
    async def add_article_into_favorites(self, *, article: Article, user: User) -> None:
        await queries.add_article_to_favorites(
            self.connection,
            username=user.username,
            slug=article.slug,
        )
    
    async def remove_article_from_favorites(
        self,
        *,
        article: Article,
        user: User,
    ) -> None:
        await queries.remove_article_from_favorites(
            self.connection,
            username=user.username,
            slug=article.slug,
        )
    
    async def _get_article_from_db_record(
        self,
        *,
        article_row: Record,
        slug: str,
        author_username: str,
        requested_user: Optional[User],
    ) -> Article:
        return Article(
            id_=article_row["id"],
            slug=slug,
            title=article_row["title"],
            description=article_row["description"],
            body=article_row["body"],
            author=await self._profiles_repo.get_profile_by_username(
                username=author_username,
                requested_user=requested_user,
            ),
            tags=await self.get_tags_for_article_by_slug(slug=slug),
            favorites_count=await self.get_favorites_count_for_article_by_slug(
                slug=slug,
            ),
            favorited=await self.is_article_favorited_by_user(
                slug=slug,
                user=requested_user,
            )
            if requested_user
            else False,
            created_at=article_row["created_at"],
            updated_at=article_row["updated_at"],
        )
    
    async def _link_article_with_tags(self, *, slug: str, tags: Sequence[str]) -> None:
        await queries.add_tags_to_article(
            self.connection,
            [{SLUG_ALIAS: slug, "tag": tag} for tag in tags],
        )



================================================
FILE: app/db/repositories/base.py
================================================
from asyncpg.connection import Connection


class BaseRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    @property
    def connection(self) -> Connection:
        return self._conn



================================================
FILE: app/db/repositories/comments.py
================================================
from typing import List, Optional

from asyncpg import Connection, Record

from app.db.errors import EntityDoesNotExist
from app.db.queries.queries import queries
from app.db.repositories.base import BaseRepository
from app.db.repositories.profiles import ProfilesRepository
from app.models.domain.articles import Article
from app.models.domain.comments import Comment
from app.models.domain.users import User


class CommentsRepository(BaseRepository):
    def __init__(self, conn: Connection) -> None:
        super().__init__(conn)
        self._profiles_repo = ProfilesRepository(conn)

    async def get_comment_by_id(
        self,
        *,
        comment_id: int,
        article: Article,
        user: Optional[User] = None,
    ) -> Comment:
        comment_row = await queries.get_comment_by_id_and_slug(
            self.connection,
            comment_id=comment_id,
            article_slug=article.slug,
        )
        if comment_row:
            return await self._get_comment_from_db_record(
                comment_row=comment_row,
                author_username=comment_row["author_username"],
                requested_user=user,
            )
    
        raise EntityDoesNotExist(
            "comment with id {0} does not exist".format(comment_id),
        )
    
    async def get_comments_for_article(
        self,
        *,
        article: Article,
        user: Optional[User] = None,
    ) -> List[Comment]:
        comments_rows = await queries.get_comments_for_article_by_slug(
            self.connection,
            slug=article.slug,
        )
        return [
            await self._get_comment_from_db_record(
                comment_row=comment_row,
                author_username=comment_row["author_username"],
                requested_user=user,
            )
            for comment_row in comments_rows
        ]
    
    async def create_comment_for_article(
        self,
        *,
        body: str,
        article: Article,
        user: User,
    ) -> Comment:
        comment_row = await queries.create_new_comment(
            self.connection,
            body=body,
            article_slug=article.slug,
            author_username=user.username,
        )
        return await self._get_comment_from_db_record(
            comment_row=comment_row,
            author_username=comment_row["author_username"],
            requested_user=user,
        )
    
    async def delete_comment(self, *, comment: Comment) -> None:
        await queries.delete_comment_by_id(
            self.connection,
            comment_id=comment.id_,
            author_username=comment.author.username,
        )
    
    async def _get_comment_from_db_record(
        self,
        *,
        comment_row: Record,
        author_username: str,
        requested_user: Optional[User],
    ) -> Comment:
        return Comment(
            id_=comment_row["id"],
            body=comment_row["body"],
            author=await self._profiles_repo.get_profile_by_username(
                username=author_username,
                requested_user=requested_user,
            ),
            created_at=comment_row["created_at"],
            updated_at=comment_row["updated_at"],
        )



================================================
FILE: app/db/repositories/profiles.py
================================================
from typing import Optional, Union

from asyncpg import Connection

from app.db.queries.queries import queries
from app.db.repositories.base import BaseRepository
from app.db.repositories.users import UsersRepository
from app.models.domain.profiles import Profile
from app.models.domain.users import User

UserLike = Union[User, Profile]


class ProfilesRepository(BaseRepository):
    def __init__(self, conn: Connection):
        super().__init__(conn)
        self._users_repo = UsersRepository(conn)

    async def get_profile_by_username(
        self,
        *,
        username: str,
        requested_user: Optional[UserLike],
    ) -> Profile:
        user = await self._users_repo.get_user_by_username(username=username)
    
        profile = Profile(username=user.username, bio=user.bio, image=user.image)
        if requested_user:
            profile.following = await self.is_user_following_for_another_user(
                target_user=user,
                requested_user=requested_user,
            )
    
        return profile
    
    async def is_user_following_for_another_user(
        self,
        *,
        target_user: UserLike,
        requested_user: UserLike,
    ) -> bool:
        return (
            await queries.is_user_following_for_another(
                self.connection,
                follower_username=requested_user.username,
                following_username=target_user.username,
            )
        )["is_following"]
    
    async def add_user_into_followers(
        self,
        *,
        target_user: UserLike,
        requested_user: UserLike,
    ) -> None:
        async with self.connection.transaction():
            await queries.subscribe_user_to_another(
                self.connection,
                follower_username=requested_user.username,
                following_username=target_user.username,
            )
    
    async def remove_user_from_followers(
        self,
        *,
        target_user: UserLike,
        requested_user: UserLike,
    ) -> None:
        async with self.connection.transaction():
            await queries.unsubscribe_user_from_another(
                self.connection,
                follower_username=requested_user.username,
                following_username=target_user.username,
            )



================================================
FILE: app/db/repositories/tags.py
================================================
from typing import List, Sequence

from app.db.queries.queries import queries
from app.db.repositories.base import BaseRepository


class TagsRepository(BaseRepository):
    async def get_all_tags(self) -> List[str]:
        tags_row = await queries.get_all_tags(self.connection)
        return [tag[0] for tag in tags_row]

    async def create_tags_that_dont_exist(self, *, tags: Sequence[str]) -> None:
        await queries.create_new_tags(self.connection, [{"tag": tag} for tag in tags])



================================================
FILE: app/db/repositories/users.py
================================================
from typing import Optional

from app.db.errors import EntityDoesNotExist
from app.db.queries.queries import queries
from app.db.repositories.base import BaseRepository
from app.models.domain.users import User, UserInDB


class UsersRepository(BaseRepository):
    async def get_user_by_email(self, *, email: str) -> UserInDB:
        user_row = await queries.get_user_by_email(self.connection, email=email)
        if user_row:
            return UserInDB(**user_row)

        raise EntityDoesNotExist("user with email {0} does not exist".format(email))
    
    async def get_user_by_username(self, *, username: str) -> UserInDB:
        user_row = await queries.get_user_by_username(
            self.connection,
            username=username,
        )
        if user_row:
            return UserInDB(**user_row)
    
        raise EntityDoesNotExist(
            "user with username {0} does not exist".format(username),
        )
    
    async def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
    ) -> UserInDB:
        user = UserInDB(username=username, email=email)
        user.change_password(password)
    
        async with self.connection.transaction():
            user_row = await queries.create_new_user(
                self.connection,
                username=user.username,
                email=user.email,
                salt=user.salt,
                hashed_password=user.hashed_password,
            )
    
        return user.copy(update=dict(user_row))
    
    async def update_user(  # noqa: WPS211
        self,
        *,
        user: User,
        username: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        bio: Optional[str] = None,
        image: Optional[str] = None,
    ) -> UserInDB:
        user_in_db = await self.get_user_by_username(username=user.username)
    
        user_in_db.username = username or user_in_db.username
        user_in_db.email = email or user_in_db.email
        user_in_db.bio = bio or user_in_db.bio
        user_in_db.image = image or user_in_db.image
        if password:
            user_in_db.change_password(password)
    
        async with self.connection.transaction():
            user_in_db.updated_at = await queries.update_user_by_username(
                self.connection,
                username=user.username,
                new_username=user_in_db.username,
                new_email=user_in_db.email,
                new_salt=user_in_db.salt,
                new_password=user_in_db.hashed_password,
                new_bio=user_in_db.bio,
                new_image=user_in_db.image,
            )
    
        return user_in_db



================================================
FILE: app/models/__init__.py
================================================
[Empty file]


================================================
FILE: app/models/common.py
================================================
import datetime

from pydantic import BaseModel, Field, validator


class DateTimeModelMixin(BaseModel):
    created_at: datetime.datetime = None  # type: ignore
    updated_at: datetime.datetime = None  # type: ignore

    @validator("created_at", "updated_at", pre=True)
    def default_datetime(
        cls,  # noqa: N805
        value: datetime.datetime,  # noqa: WPS110
    ) -> datetime.datetime:
        return value or datetime.datetime.now()


class IDModelMixin(BaseModel):
    id_: int = Field(0, alias="id")



================================================
FILE: app/models/domain/__init__.py
================================================
[Empty file]


================================================
FILE: app/models/domain/articles.py
================================================
from typing import List

from app.models.common import DateTimeModelMixin, IDModelMixin
from app.models.domain.profiles import Profile
from app.models.domain.rwmodel import RWModel


class Article(IDModelMixin, DateTimeModelMixin, RWModel):
    slug: str
    title: str
    description: str
    body: str
    tags: List[str]
    author: Profile
    favorited: bool
    favorites_count: int



================================================
FILE: app/models/domain/comments.py
================================================
from app.models.common import DateTimeModelMixin, IDModelMixin
from app.models.domain.profiles import Profile
from app.models.domain.rwmodel import RWModel


class Comment(IDModelMixin, DateTimeModelMixin, RWModel):
    body: str
    author: Profile



================================================
FILE: app/models/domain/profiles.py
================================================
from typing import Optional

from app.models.domain.rwmodel import RWModel


class Profile(RWModel):
    username: str
    bio: str = ""
    image: Optional[str] = None
    following: bool = False



================================================
FILE: app/models/domain/rwmodel.py
================================================
import datetime

from pydantic import BaseConfig, BaseModel


def convert_datetime_to_realworld(dt: datetime.datetime) -> str:
    return dt.replace(tzinfo=datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def convert_field_to_camel_case(string: str) -> str:
    return "".join(
        word if index == 0 else word.capitalize()
        for index, word in enumerate(string.split("_"))
    )


class RWModel(BaseModel):
    class Config(BaseConfig):
        allow_population_by_field_name = True
        json_encoders = {datetime.datetime: convert_datetime_to_realworld}
        alias_generator = convert_field_to_camel_case



================================================
FILE: app/models/domain/users.py
================================================
from typing import Optional

from app.models.common import DateTimeModelMixin, IDModelMixin
from app.models.domain.rwmodel import RWModel
from app.services import security


class User(RWModel):
    username: str
    email: str
    bio: str = ""
    image: Optional[str] = None


class UserInDB(IDModelMixin, DateTimeModelMixin, User):
    salt: str = ""
    hashed_password: str = ""

    def check_password(self, password: str) -> bool:
        return security.verify_password(self.salt + password, self.hashed_password)
    
    def change_password(self, password: str) -> None:
        self.salt = security.generate_salt()
        self.hashed_password = security.get_password_hash(self.salt + password)



================================================
FILE: app/models/schemas/__init__.py
================================================
[Empty file]


================================================
FILE: app/models/schemas/articles.py
================================================
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.domain.articles import Article
from app.models.schemas.rwschema import RWSchema

DEFAULT_ARTICLES_LIMIT = 20
DEFAULT_ARTICLES_OFFSET = 0


class ArticleForResponse(RWSchema, Article):
    tags: List[str] = Field(..., alias="tagList")


class ArticleInResponse(RWSchema):
    article: ArticleForResponse


class ArticleInCreate(RWSchema):
    title: str
    description: str
    body: str
    tags: List[str] = Field([], alias="tagList")


class ArticleInUpdate(RWSchema):
    title: Optional[str] = None
    description: Optional[str] = None
    body: Optional[str] = None


class ListOfArticlesInResponse(RWSchema):
    articles: List[ArticleForResponse]
    articles_count: int


class ArticlesFilters(BaseModel):
    tag: Optional[str] = None
    author: Optional[str] = None
    favorited: Optional[str] = None
    limit: int = Field(DEFAULT_ARTICLES_LIMIT, ge=1)
    offset: int = Field(DEFAULT_ARTICLES_OFFSET, ge=0)



================================================
FILE: app/models/schemas/comments.py
================================================
from typing import List

from app.models.domain.comments import Comment
from app.models.schemas.rwschema import RWSchema


class ListOfCommentsInResponse(RWSchema):
    comments: List[Comment]


class CommentInResponse(RWSchema):
    comment: Comment


class CommentInCreate(RWSchema):
    body: str



================================================
FILE: app/models/schemas/jwt.py
================================================
from datetime import datetime

from pydantic import BaseModel


class JWTMeta(BaseModel):
    exp: datetime
    sub: str


class JWTUser(BaseModel):
    username: str



================================================
FILE: app/models/schemas/profiles.py
================================================
from pydantic import BaseModel

from app.models.domain.profiles import Profile


class ProfileInResponse(BaseModel):
    profile: Profile



================================================
FILE: app/models/schemas/rwschema.py
================================================
from app.models.domain.rwmodel import RWModel


class RWSchema(RWModel):
    class Config(RWModel.Config):
        orm_mode = True



================================================
FILE: app/models/schemas/tags.py
================================================
from typing import List

from pydantic import BaseModel


class TagsInList(BaseModel):
    tags: List[str]



================================================
FILE: app/models/schemas/users.py
================================================
from typing import Optional

from pydantic import BaseModel, EmailStr, HttpUrl

from app.models.domain.users import User
from app.models.schemas.rwschema import RWSchema


class UserInLogin(RWSchema):
    email: EmailStr
    password: str


class UserInCreate(UserInLogin):
    username: str


class UserInUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    bio: Optional[str] = None
    image: Optional[HttpUrl] = None


class UserWithToken(User):
    token: str


class UserInResponse(RWSchema):
    user: UserWithToken



================================================
FILE: app/resources/__init__.py
================================================
[Empty file]


================================================
FILE: app/resources/strings.py
================================================
# API messages

USER_DOES_NOT_EXIST_ERROR = "user does not exist"
ARTICLE_DOES_NOT_EXIST_ERROR = "article does not exist"
ARTICLE_ALREADY_EXISTS = "article already exists"
USER_IS_NOT_AUTHOR_OF_ARTICLE = "you are not an author of this article"

INCORRECT_LOGIN_INPUT = "incorrect email or password"
USERNAME_TAKEN = "user with this username already exists"
EMAIL_TAKEN = "user with this email already exists"

UNABLE_TO_FOLLOW_YOURSELF = "user can not follow him self"
UNABLE_TO_UNSUBSCRIBE_FROM_YOURSELF = "user can not unsubscribe from him self"
USER_IS_NOT_FOLLOWED = "you don't follow this user"
USER_IS_ALREADY_FOLLOWED = "you follow this user already"

WRONG_TOKEN_PREFIX = "unsupported authorization type"  # noqa: S105
MALFORMED_PAYLOAD = "could not validate credentials"

ARTICLE_IS_ALREADY_FAVORITED = "you are already marked this articles as favorite"
ARTICLE_IS_NOT_FAVORITED = "article is not favorited"

COMMENT_DOES_NOT_EXIST = "comment does not exist"

AUTHENTICATION_REQUIRED = "authentication required"



================================================
FILE: app/services/__init__.py
================================================
[Empty file]


================================================
FILE: app/services/articles.py
================================================
from slugify import slugify

from app.db.errors import EntityDoesNotExist
from app.db.repositories.articles import ArticlesRepository
from app.models.domain.articles import Article
from app.models.domain.users import User


async def check_article_exists(articles_repo: ArticlesRepository, slug: str) -> bool:
    try:
        await articles_repo.get_article_by_slug(slug=slug)
    except EntityDoesNotExist:
        return False

    return True


def get_slug_for_article(title: str) -> str:
    return slugify(title)


def check_user_can_modify_article(article: Article, user: User) -> bool:
    return article.author.username == user.username



================================================
FILE: app/services/authentication.py
================================================
from app.db.errors import EntityDoesNotExist
from app.db.repositories.users import UsersRepository


async def check_username_is_taken(repo: UsersRepository, username: str) -> bool:
    try:
        await repo.get_user_by_username(username=username)
    except EntityDoesNotExist:
        return False

    return True


async def check_email_is_taken(repo: UsersRepository, email: str) -> bool:
    try:
        await repo.get_user_by_email(email=email)
    except EntityDoesNotExist:
        return False

    return True



================================================
FILE: app/services/comments.py
================================================
from app.models.domain.comments import Comment
from app.models.domain.users import User


def check_user_can_modify_comment(comment: Comment, user: User) -> bool:
    return comment.author.username == user.username



================================================
FILE: app/services/jwt.py
================================================
from datetime import datetime, timedelta
from typing import Dict

import jwt
from pydantic import ValidationError

from app.models.domain.users import User
from app.models.schemas.jwt import JWTMeta, JWTUser

JWT_SUBJECT = "access"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # one week


def create_jwt_token(
    *,
    jwt_content: Dict[str, str],
    secret_key: str,
    expires_delta: timedelta,
) -> str:
    to_encode = jwt_content.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update(JWTMeta(exp=expire, sub=JWT_SUBJECT).dict())
    return jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)


def create_access_token_for_user(user: User, secret_key: str) -> str:
    return create_jwt_token(
        jwt_content=JWTUser(username=user.username).dict(),
        secret_key=secret_key,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def get_username_from_token(token: str, secret_key: str) -> str:
    try:
        return JWTUser(**jwt.decode(token, secret_key, algorithms=[ALGORITHM])).username
    except jwt.PyJWTError as decode_error:
        raise ValueError("unable to decode JWT token") from decode_error
    except ValidationError as validation_error:
        raise ValueError("malformed payload in token") from validation_error



================================================
FILE: app/services/security.py
================================================
import bcrypt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_salt() -> str:
    return bcrypt.gensalt().decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)



================================================
FILE: postman/run-api-tests.sh
================================================
#!/usr/bin/env bash
set -x

SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

APIURL=${APIURL:-https://conduit.productionready.io/api}
USERNAME=${USERNAME:-u`date +%s`}
EMAIL=${EMAIL:-$USERNAME@mail.com}
PASSWORD=${PASSWORD:-password}

npx newman run $SCRIPTDIR/Conduit.postman_collection.json \
  --delay-request 500 \
  --global-var "APIURL=$APIURL" \
  --global-var "USERNAME=$USERNAME" \
  --global-var "EMAIL=$EMAIL" \
  --global-var "PASSWORD=$PASSWORD"


================================================
FILE: scripts/format
================================================
#!/usr/bin/env bash

set -e

isort --force-single-line-imports app tests
autoflake --recursive --remove-all-unused-imports --remove-unused-variables --in-place app tests
black app tests
isort app tests



================================================
FILE: scripts/lint
================================================
#!/usr/bin/env bash

set -e
set -x


flake8 app --exclude=app/db/migrations
mypy app

black --check app --diff
isort --check-only app



================================================
FILE: scripts/test
================================================
#!/usr/bin/env bash

set -e
set -x

pytest --cov=app --cov=tests --cov-report=term-missing --cov-config=setup.cfg ${@}



================================================
FILE: scripts/test-cov-html
================================================
#!/usr/bin/env bash

set -e
set -x

bash scripts/test --cov-report=html ${@}



================================================
FILE: tests/__init__.py
================================================
[Empty file]


================================================
FILE: tests/conftest.py
================================================
from os import environ

import pytest
from asgi_lifespan import LifespanManager
from asyncpg.pool import Pool
from fastapi import FastAPI
from httpx import AsyncClient

from app.db.repositories.articles import ArticlesRepository
from app.db.repositories.users import UsersRepository
from app.models.domain.articles import Article
from app.models.domain.users import UserInDB
from app.services import jwt
from tests.fake_asyncpg_pool import FakeAsyncPGPool

environ["APP_ENV"] = "test"


@pytest.fixture
def app() -> FastAPI:
    from app.main import get_application  # local import for testing purpose

    return get_application()


@pytest.fixture
async def initialized_app(app: FastAPI) -> FastAPI:
    async with LifespanManager(app):
        app.state.pool = await FakeAsyncPGPool.create_pool(app.state.pool)
        yield app


@pytest.fixture
def pool(initialized_app: FastAPI) -> Pool:
    return initialized_app.state.pool


@pytest.fixture
async def client(initialized_app: FastAPI) -> AsyncClient:
    async with AsyncClient(
        app=initialized_app,
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.fixture
def authorization_prefix() -> str:
    from app.core.config import get_app_settings

    settings = get_app_settings()
    jwt_token_prefix = settings.jwt_token_prefix
    
    return jwt_token_prefix


@pytest.fixture
async def test_user(pool: Pool) -> UserInDB:
    async with pool.acquire() as conn:
        return await UsersRepository(conn).create_user(
            email="test@test.com", password="password", username="username"
        )


@pytest.fixture
async def test_article(test_user: UserInDB, pool: Pool) -> Article:
    async with pool.acquire() as connection:
        articles_repo = ArticlesRepository(connection)
        return await articles_repo.create_article(
            slug="test-slug",
            title="Test Slug",
            description="Slug for tests",
            body="Test " * 100,
            author=test_user,
            tags=["tests", "testing", "pytest"],
        )


@pytest.fixture
def token(test_user: UserInDB) -> str:
    return jwt.create_access_token_for_user(test_user, environ["SECRET_KEY"])


@pytest.fixture
def authorized_client(
    client: AsyncClient, token: str, authorization_prefix: str
) -> AsyncClient:
    client.headers = {
        "Authorization": f"{authorization_prefix} {token}",
        **client.headers,
    }
    return client



================================================
FILE: tests/fake_asyncpg_pool.py
================================================
from types import TracebackType
from typing import Optional, Type

from asyncpg import Connection
from asyncpg.pool import Pool


class FakeAsyncPGPool:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool
        self._conn = None
        self._tx = None

    @classmethod
    async def create_pool(cls, pool: Pool) -> "FakeAsyncPGPool":
        pool = cls(pool)
        conn = await pool._pool.acquire()
        tx = conn.transaction()
        await tx.start()
        pool._conn = conn
        pool._tx = tx
        return pool
    
    async def close(self) -> None:
        await self._tx.rollback()
        await self._pool.release(self._conn)
        await self._pool.close()
    
    def acquire(self, *, timeout: Optional[float] = None) -> "FakePoolAcquireContent":
        return FakePoolAcquireContent(self)


class FakePoolAcquireContent:
    def __init__(self, pool: FakeAsyncPGPool) -> None:
        self._pool = pool

    async def __aenter__(self) -> Connection:
        return self._pool._conn
    
    async def __aexit__(
        self,
        exc_type: Optional[Type[Exception]],
        exc: Optional[Exception],
        tb: Optional[TracebackType],
    ) -> None:
        pass



================================================
FILE: tests/test_api/__init__.py
================================================
[Empty file]


================================================
FILE: tests/test_api/test_errors/__init__.py
================================================
[Empty file]


================================================
FILE: tests/test_api/test_errors/test_422_error.py
================================================
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

pytestmark = pytest.mark.asyncio


async def test_frw_validation_error_format(app: FastAPI):
    @app.get("/wrong_path/{param}")
    def route_for_test(param: int) -> None:  # pragma: no cover
        pass

    async with AsyncClient(base_url="http://testserver", app=app) as client:
        response = await client.get("/wrong_path/asd")
    
    assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY
    
    error_data = response.json()
    assert "errors" in error_data



================================================
FILE: tests/test_api/test_errors/test_error.py
================================================
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.status import HTTP_404_NOT_FOUND

pytestmark = pytest.mark.asyncio


async def test_frw_validation_error_format(app: FastAPI):
    async with AsyncClient(base_url="http://testserver", app=app) as client:
        response = await client.get("/wrong_path/asd")

    assert response.status_code == HTTP_404_NOT_FOUND
    
    error_data = response.json()
    assert "errors" in error_data



================================================
FILE: tests/test_api/test_routes/__init__.py
================================================
[Empty file]


================================================
FILE: tests/test_api/test_routes/test_articles.py
================================================
import pytest
from asyncpg.pool import Pool
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status

from app.db.errors import EntityDoesNotExist
from app.db.repositories.articles import ArticlesRepository
from app.db.repositories.profiles import ProfilesRepository
from app.db.repositories.users import UsersRepository
from app.models.domain.articles import Article
from app.models.domain.users import UserInDB
from app.models.schemas.articles import ArticleInResponse, ListOfArticlesInResponse

pytestmark = pytest.mark.asyncio


async def test_user_can_not_create_article_with_duplicated_slug(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    article_data = {
        "title": "Test Slug",
        "body": "does not matter",
        "description": "¯\\_(ツ)_/¯",
    }
    response = await authorized_client.post(
        app.url_path_for("articles:create-article"), json={"article": article_data}
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_user_can_create_article(
    app: FastAPI, authorized_client: AsyncClient, test_user: UserInDB
) -> None:
    article_data = {
        "title": "Test Slug",
        "body": "does not matter",
        "description": "¯\\_(ツ)_/¯",
    }
    response = await authorized_client.post(
        app.url_path_for("articles:create-article"), json={"article": article_data}
    )
    article = ArticleInResponse(**response.json())
    assert article.article.title == article_data["title"]
    assert article.article.author.username == test_user.username


async def test_not_existing_tags_will_be_created_without_duplication(
    app: FastAPI, authorized_client: AsyncClient, test_user: UserInDB
) -> None:
    article_data = {
        "title": "Test Slug",
        "body": "does not matter",
        "description": "¯\\_(ツ)_/¯",
        "tagList": ["tag1", "tag2", "tag3", "tag3"],
    }
    response = await authorized_client.post(
        app.url_path_for("articles:create-article"), json={"article": article_data}
    )
    article = ArticleInResponse(**response.json())
    assert set(article.article.tags) == {"tag1", "tag2", "tag3"}


@pytest.mark.parametrize(
    "api_method, route_name",
    (("GET", "articles:get-article"), ("PUT", "articles:update-article")),
)
async def test_user_can_not_retrieve_not_existing_article(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    api_method: str,
    route_name: str,
) -> None:
    response = await authorized_client.request(
        api_method, app.url_path_for(route_name, slug="wrong-slug")
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_user_can_retrieve_article_if_exists(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    response = await authorized_client.get(
        app.url_path_for("articles:get-article", slug=test_article.slug)
    )
    article = ArticleInResponse(**response.json())
    assert article.article == test_article


@pytest.mark.parametrize(
    "update_field, update_value, extra_updates",
    (
        ("title", "New Title", {"slug": "new-title"}),
        ("description", "new description", {}),
        ("body", "new body", {}),
    ),
)
async def test_user_can_update_article(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    update_field: str,
    update_value: str,
    extra_updates: dict,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("articles:update-article", slug=test_article.slug),
        json={"article": {update_field: update_value}},
    )

    assert response.status_code == status.HTTP_200_OK
    
    article = ArticleInResponse(**response.json()).article
    article_as_dict = article.dict()
    assert article_as_dict[update_field] == update_value
    
    for extra_field, extra_value in extra_updates.items():
        assert article_as_dict[extra_field] == extra_value
    
    exclude_fields = {update_field, *extra_updates.keys(), "updated_at"}
    assert article.dict(exclude=exclude_fields) == test_article.dict(
        exclude=exclude_fields
    )


@pytest.mark.parametrize(
    "api_method, route_name",
    (("PUT", "articles:update-article"), ("DELETE", "articles:delete-article")),
)
async def test_user_can_not_modify_article_that_is_not_authored_by_him(
    app: FastAPI,
    authorized_client: AsyncClient,
    pool: Pool,
    api_method: str,
    route_name: str,
) -> None:
    async with pool.acquire() as connection:
        users_repo = UsersRepository(connection)
        user = await users_repo.create_user(
            username="test_author", email="author@email.com", password="password"
        )
        articles_repo = ArticlesRepository(connection)
        await articles_repo.create_article(
            slug="test-slug",
            title="Test Slug",
            description="Slug for tests",
            body="Test " * 100,
            author=user,
            tags=["tests", "testing", "pytest"],
        )

    response = await authorized_client.request(
        api_method,
        app.url_path_for(route_name, slug="test-slug"),
        json={"article": {"title": "Updated Title"}},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_user_can_delete_his_article(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    pool: Pool,
) -> None:
    await authorized_client.delete(
        app.url_path_for("articles:delete-article", slug=test_article.slug)
    )

    async with pool.acquire() as connection:
        articles_repo = ArticlesRepository(connection)
        with pytest.raises(EntityDoesNotExist):
            await articles_repo.get_article_by_slug(slug=test_article.slug)


@pytest.mark.parametrize(
    "api_method, route_name, favorite_state",
    (
        ("POST", "articles:mark-article-favorite", True),
        ("DELETE", "articles:unmark-article-favorite", False),
    ),
)
async def test_user_can_change_favorite_state(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    test_user: UserInDB,
    pool: Pool,
    api_method: str,
    route_name: str,
    favorite_state: bool,
) -> None:
    if not favorite_state:
        async with pool.acquire() as connection:
            articles_repo = ArticlesRepository(connection)
            await articles_repo.add_article_into_favorites(
                article=test_article, user=test_user
            )

    await authorized_client.request(
        api_method, app.url_path_for(route_name, slug=test_article.slug)
    )
    
    response = await authorized_client.get(
        app.url_path_for("articles:get-article", slug=test_article.slug)
    )
    
    article = ArticleInResponse(**response.json())
    
    assert article.article.favorited == favorite_state
    assert article.article.favorites_count == int(favorite_state)


@pytest.mark.parametrize(
    "api_method, route_name, favorite_state",
    (
        ("POST", "articles:mark-article-favorite", True),
        ("DELETE", "articles:unmark-article-favorite", False),
    ),
)
async def test_user_can_not_change_article_state_twice(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    test_user: UserInDB,
    pool: Pool,
    api_method: str,
    route_name: str,
    favorite_state: bool,
) -> None:
    if favorite_state:
        async with pool.acquire() as connection:
            articles_repo = ArticlesRepository(connection)
            await articles_repo.add_article_into_favorites(
                article=test_article, user=test_user
            )

    response = await authorized_client.request(
        api_method, app.url_path_for(route_name, slug=test_article.slug)
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_empty_feed_if_user_has_not_followings(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    test_user: UserInDB,
    pool: Pool,
) -> None:
    async with pool.acquire() as connection:
        users_repo = UsersRepository(connection)
        articles_repo = ArticlesRepository(connection)

        for i in range(5):
            user = await users_repo.create_user(
                username=f"user-{i}", email=f"user-{i}@email.com", password="password"
            )
            for j in range(5):
                await articles_repo.create_article(
                    slug=f"slug-{i}-{j}",
                    title="tmp",
                    description="tmp",
                    body="tmp",
                    author=user,
                    tags=[f"tag-{i}-{j}"],
                )
    
    response = await authorized_client.get(
        app.url_path_for("articles:get-user-feed-articles")
    )
    
    articles = ListOfArticlesInResponse(**response.json())
    assert articles.articles == []


async def test_user_will_receive_only_following_articles(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    test_user: UserInDB,
    pool: Pool,
) -> None:
    following_author_username = "user-2"
    async with pool.acquire() as connection:
        users_repo = UsersRepository(connection)
        profiles_repo = ProfilesRepository(connection)
        articles_repo = ArticlesRepository(connection)

        for i in range(5):
            user = await users_repo.create_user(
                username=f"user-{i}", email=f"user-{i}@email.com", password="password"
            )
            if i == 2:
                await profiles_repo.add_user_into_followers(
                    target_user=user, requested_user=test_user
                )
    
            for j in range(5):
                await articles_repo.create_article(
                    slug=f"slug-{i}-{j}",
                    title="tmp",
                    description="tmp",
                    body="tmp",
                    author=user,
                    tags=[f"tag-{i}-{j}"],
                )
    
    response = await authorized_client.get(
        app.url_path_for("articles:get-user-feed-articles")
    )
    
    articles_from_response = ListOfArticlesInResponse(**response.json())
    assert len(articles_from_response.articles) == 5
    
    all_from_following = (
        article.author.username == following_author_username
        for article in articles_from_response.articles
    )
    assert all(all_from_following)


async def test_user_receiving_feed_with_limit_and_offset(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    test_user: UserInDB,
    pool: Pool,
) -> None:
    async with pool.acquire() as connection:
        users_repo = UsersRepository(connection)
        profiles_repo = ProfilesRepository(connection)
        articles_repo = ArticlesRepository(connection)

        for i in range(5):
            user = await users_repo.create_user(
                username=f"user-{i}", email=f"user-{i}@email.com", password="password"
            )
            if i == 2:
                await profiles_repo.add_user_into_followers(
                    target_user=user, requested_user=test_user
                )
    
            for j in range(5):
                await articles_repo.create_article(
                    slug=f"slug-{i}-{j}",
                    title="tmp",
                    description="tmp",
                    body="tmp",
                    author=user,
                    tags=[f"tag-{i}-{j}"],
                )
    
    full_response = await authorized_client.get(
        app.url_path_for("articles:get-user-feed-articles")
    )
    full_articles = ListOfArticlesInResponse(**full_response.json())
    
    response = await authorized_client.get(
        app.url_path_for("articles:get-user-feed-articles"),
        params={"limit": 2, "offset": 3},
    )
    
    articles_from_response = ListOfArticlesInResponse(**response.json())
    assert full_articles.articles[3:] == articles_from_response.articles


async def test_article_will_contain_only_attached_tags(
    app: FastAPI, authorized_client: AsyncClient, test_user: UserInDB, pool: Pool
) -> None:
    attached_tags = ["tag1", "tag3"]

    async with pool.acquire() as connection:
        articles_repo = ArticlesRepository(connection)
    
        await articles_repo.create_article(
            slug=f"test-slug",
            title="tmp",
            description="tmp",
            body="tmp",
            author=test_user,
            tags=attached_tags,
        )
    
        for i in range(5):
            await articles_repo.create_article(
                slug=f"slug-{i}",
                title="tmp",
                description="tmp",
                body="tmp",
                author=test_user,
                tags=[f"tag-{i}"],
            )
    
    response = await authorized_client.get(
        app.url_path_for("articles:get-article", slug="test-slug")
    )
    article = ArticleInResponse(**response.json())
    assert len(article.article.tags) == len(attached_tags)
    assert set(article.article.tags) == set(attached_tags)


@pytest.mark.parametrize(
    "tag, result", (("", 7), ("tag1", 1), ("tag2", 2), ("wrong", 0))
)
async def test_filtering_by_tags(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_user: UserInDB,
    pool: Pool,
    tag: str,
    result: int,
) -> None:
    async with pool.acquire() as connection:
        articles_repo = ArticlesRepository(connection)

        await articles_repo.create_article(
            slug=f"slug-1",
            title="tmp",
            description="tmp",
            body="tmp",
            author=test_user,
            tags=["tag1", "tag2"],
        )
        await articles_repo.create_article(
            slug=f"slug-2",
            title="tmp",
            description="tmp",
            body="tmp",
            author=test_user,
            tags=["tag2"],
        )
    
        for i in range(5, 10):
            await articles_repo.create_article(
                slug=f"slug-{i}",
                title="tmp",
                description="tmp",
                body="tmp",
                author=test_user,
                tags=[f"tag-{i}"],
            )
    
    response = await authorized_client.get(
        app.url_path_for("articles:list-articles"), params={"tag": tag}
    )
    articles = ListOfArticlesInResponse(**response.json())
    assert articles.articles_count == result


@pytest.mark.parametrize(
    "author, result", (("", 8), ("author1", 1), ("author2", 2), ("wrong", 0))
)
async def test_filtering_by_authors(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_user: UserInDB,
    pool: Pool,
    author: str,
    result: int,
) -> None:
    async with pool.acquire() as connection:
        users_repo = UsersRepository(connection)
        articles_repo = ArticlesRepository(connection)

        author1 = await users_repo.create_user(
            username="author1", email="author1@email.com", password="password"
        )
        author2 = await users_repo.create_user(
            username="author2", email="author2@email.com", password="password"
        )
    
        await articles_repo.create_article(
            slug=f"slug-1", title="tmp", description="tmp", body="tmp", author=author1
        )
        await articles_repo.create_article(
            slug=f"slug-2-1", title="tmp", description="tmp", body="tmp", author=author2
        )
        await articles_repo.create_article(
            slug=f"slug-2-2", title="tmp", description="tmp", body="tmp", author=author2
        )
    
        for i in range(5, 10):
            await articles_repo.create_article(
                slug=f"slug-{i}",
                title="tmp",
                description="tmp",
                body="tmp",
                author=test_user,
            )
    
    response = await authorized_client.get(
        app.url_path_for("articles:list-articles"), params={"author": author}
    )
    articles = ListOfArticlesInResponse(**response.json())
    assert articles.articles_count == result


@pytest.mark.parametrize(
    "favorited, result", (("", 7), ("fan1", 1), ("fan2", 2), ("wrong", 0))
)
async def test_filtering_by_favorited(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_user: UserInDB,
    pool: Pool,
    favorited: str,
    result: int,
) -> None:
    async with pool.acquire() as connection:
        users_repo = UsersRepository(connection)
        articles_repo = ArticlesRepository(connection)

        fan1 = await users_repo.create_user(
            username="fan1", email="fan1@email.com", password="password"
        )
        fan2 = await users_repo.create_user(
            username="fan2", email="fan2@email.com", password="password"
        )
    
        article1 = await articles_repo.create_article(
            slug=f"slug-1", title="tmp", description="tmp", body="tmp", author=test_user
        )
        article2 = await articles_repo.create_article(
            slug=f"slug-2", title="tmp", description="tmp", body="tmp", author=test_user
        )
    
        await articles_repo.add_article_into_favorites(article=article1, user=fan1)
        await articles_repo.add_article_into_favorites(article=article1, user=fan2)
        await articles_repo.add_article_into_favorites(article=article2, user=fan2)
    
        for i in range(5, 10):
            await articles_repo.create_article(
                slug=f"slug-{i}",
                title="tmp",
                description="tmp",
                body="tmp",
                author=test_user,
            )
    
    response = await authorized_client.get(
        app.url_path_for("articles:list-articles"), params={"favorited": favorited}
    )
    articles = ListOfArticlesInResponse(**response.json())
    assert articles.articles_count == result


async def test_filtering_with_limit_and_offset(
    app: FastAPI, authorized_client: AsyncClient, test_user: UserInDB, pool: Pool
) -> None:
    async with pool.acquire() as connection:
        articles_repo = ArticlesRepository(connection)

        for i in range(5, 10):
            await articles_repo.create_article(
                slug=f"slug-{i}",
                title="tmp",
                description="tmp",
                body="tmp",
                author=test_user,
            )
    
    full_response = await authorized_client.get(
        app.url_path_for("articles:list-articles")
    )
    full_articles = ListOfArticlesInResponse(**full_response.json())
    
    response = await authorized_client.get(
        app.url_path_for("articles:list-articles"), params={"limit": 2, "offset": 3}
    )
    
    articles_from_response = ListOfArticlesInResponse(**response.json())
    assert full_articles.articles[3:] == articles_from_response.articles



================================================
FILE: tests/test_api/test_routes/test_authentication.py
================================================
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.status import HTTP_403_FORBIDDEN

from app.models.domain.users import User
from app.services.jwt import create_access_token_for_user

pytestmark = pytest.mark.asyncio


async def test_unable_to_login_with_wrong_jwt_prefix(
    app: FastAPI, client: AsyncClient, token: str
) -> None:
    response = await client.get(
        app.url_path_for("users:get-current-user"),
        headers={"Authorization": f"WrongPrefix {token}"},
    )
    assert response.status_code == HTTP_403_FORBIDDEN


async def test_unable_to_login_when_user_does_not_exist_any_more(
    app: FastAPI, client: AsyncClient, authorization_prefix: str
) -> None:
    token = create_access_token_for_user(
        User(username="user", email="email@email.com"), "secret"
    )
    response = await client.get(
        app.url_path_for("users:get-current-user"),
        headers={"Authorization": f"{authorization_prefix} {token}"},
    )
    assert response.status_code == HTTP_403_FORBIDDEN



================================================
FILE: tests/test_api/test_routes/test_comments.py
================================================
import pytest
from asyncpg.pool import Pool
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status

from app.db.repositories.comments import CommentsRepository
from app.db.repositories.users import UsersRepository
from app.models.domain.articles import Article
from app.models.schemas.comments import CommentInResponse, ListOfCommentsInResponse

pytestmark = pytest.mark.asyncio


async def test_user_can_add_comment_for_article(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    created_comment_response = await authorized_client.post(
        app.url_path_for("comments:create-comment-for-article", slug=test_article.slug),
        json={"comment": {"body": "comment"}},
    )

    created_comment = CommentInResponse(**created_comment_response.json())
    
    comments_for_article_response = await authorized_client.get(
        app.url_path_for("comments:get-comments-for-article", slug=test_article.slug)
    )
    
    comments = ListOfCommentsInResponse(**comments_for_article_response.json())
    
    assert created_comment.comment == comments.comments[0]


async def test_user_can_delete_own_comment(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    created_comment_response = await authorized_client.post(
        app.url_path_for("comments:create-comment-for-article", slug=test_article.slug),
        json={"comment": {"body": "comment"}},
    )

    created_comment = CommentInResponse(**created_comment_response.json())
    
    await authorized_client.delete(
        app.url_path_for(
            "comments:delete-comment-from-article",
            slug=test_article.slug,
            comment_id=str(created_comment.comment.id_),
        )
    )
    
    comments_for_article_response = await authorized_client.get(
        app.url_path_for("comments:get-comments-for-article", slug=test_article.slug)
    )
    
    comments = ListOfCommentsInResponse(**comments_for_article_response.json())
    
    assert len(comments.comments) == 0


async def test_user_can_not_delete_not_authored_comment(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article, pool: Pool
) -> None:
    async with pool.acquire() as connection:
        users_repo = UsersRepository(connection)
        user = await users_repo.create_user(
            username="test_author", email="author@email.com", password="password"
        )
        comments_repo = CommentsRepository(connection)
        comment = await comments_repo.create_comment_for_article(
            body="tmp", article=test_article, user=user
        )

    forbidden_response = await authorized_client.delete(
        app.url_path_for(
            "comments:delete-comment-from-article",
            slug=test_article.slug,
            comment_id=str(comment.id_),
        )
    )
    
    assert forbidden_response.status_code == status.HTTP_403_FORBIDDEN


async def test_user_will_receive_error_for_not_existing_comment(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    not_found_response = await authorized_client.delete(
        app.url_path_for(
            "comments:delete-comment-from-article",
            slug=test_article.slug,
            comment_id="1",
        )
    )

    assert not_found_response.status_code == status.HTTP_404_NOT_FOUND



================================================
FILE: tests/test_api/test_routes/test_login.py
================================================
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.status import HTTP_200_OK, HTTP_400_BAD_REQUEST

from app.models.domain.users import UserInDB

pytestmark = pytest.mark.asyncio


async def test_user_successful_login(
    app: FastAPI, client: AsyncClient, test_user: UserInDB
) -> None:
    login_json = {"user": {"email": "test@test.com", "password": "password"}}

    response = await client.post(app.url_path_for("auth:login"), json=login_json)
    assert response.status_code == HTTP_200_OK


@pytest.mark.parametrize(
    "credentials_part, credentials_value",
    (("email", "wrong@test.com"), ("password", "wrong")),
)
async def test_user_login_when_credential_part_does_not_match(
    app: FastAPI,
    client: AsyncClient,
    test_user: UserInDB,
    credentials_part: str,
    credentials_value: str,
) -> None:
    login_json = {"user": {"email": "test@test.com", "password": "password"}}
    login_json["user"][credentials_part] = credentials_value
    response = await client.post(app.url_path_for("auth:login"), json=login_json)
    assert response.status_code == HTTP_400_BAD_REQUEST



================================================
FILE: tests/test_api/test_routes/test_profiles.py
================================================
import pytest
from asyncpg.pool import Pool
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status

from app.db.repositories.profiles import ProfilesRepository
from app.db.repositories.users import UsersRepository
from app.models.domain.users import UserInDB
from app.models.schemas.profiles import ProfileInResponse

pytestmark = pytest.mark.asyncio


async def test_unregistered_user_will_receive_profile_without_following(
    app: FastAPI, client: AsyncClient, test_user: UserInDB
) -> None:
    response = await client.get(
        app.url_path_for("profiles:get-profile", username=test_user.username)
    )
    profile = ProfileInResponse(**response.json())
    assert profile.profile.username == test_user.username
    assert not profile.profile.following


async def test_user_that_does_not_follows_another_will_receive_profile_without_follow(
    app: FastAPI, authorized_client: AsyncClient, pool: Pool
) -> None:
    async with pool.acquire() as conn:
        users_repo = UsersRepository(conn)
        user = await users_repo.create_user(
            username="user_for_following",
            email="test-for-following@email.com",
            password="password",
        )

    response = await authorized_client.get(
        app.url_path_for("profiles:get-profile", username=user.username)
    )
    profile = ProfileInResponse(**response.json())
    assert profile.profile.username == user.username
    assert not profile.profile.following


async def test_user_that_follows_another_will_receive_profile_with_follow(
    app: FastAPI, authorized_client: AsyncClient, pool: Pool, test_user: UserInDB
) -> None:
    async with pool.acquire() as conn:
        users_repo = UsersRepository(conn)
        user = await users_repo.create_user(
            username="user_for_following",
            email="test-for-following@email.com",
            password="password",
        )

        profiles_repo = ProfilesRepository(conn)
        await profiles_repo.add_user_into_followers(
            target_user=user, requested_user=test_user
        )
    
    response = await authorized_client.get(
        app.url_path_for("profiles:get-profile", username=user.username)
    )
    profile = ProfileInResponse(**response.json())
    assert profile.profile.username == user.username
    assert profile.profile.following


@pytest.mark.parametrize(
    "api_method, route_name",
    (
        ("GET", "profiles:get-profile"),
        ("POST", "profiles:follow-user"),
        ("DELETE", "profiles:unsubscribe-from-user"),
    ),
)
async def test_user_can_not_retrieve_not_existing_profile(
    app: FastAPI, authorized_client: AsyncClient, api_method: str, route_name: str
) -> None:
    response = await authorized_client.request(
        api_method, app.url_path_for(route_name, username="not_existing_user")
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize(
    "api_method, route_name, following",
    (
        ("POST", "profiles:follow-user", True),
        ("DELETE", "profiles:unsubscribe-from-user", False),
    ),
)
async def test_user_can_change_following_for_another_user(
    app: FastAPI,
    authorized_client: AsyncClient,
    pool: Pool,
    test_user: UserInDB,
    api_method: str,
    route_name: str,
    following: bool,
) -> None:
    async with pool.acquire() as conn:
        users_repo = UsersRepository(conn)
        user = await users_repo.create_user(
            username="user_for_following",
            email="test-for-following@email.com",
            password="password",
        )

        if not following:
            profiles_repo = ProfilesRepository(conn)
            await profiles_repo.add_user_into_followers(
                target_user=user, requested_user=test_user
            )
    
    change_following_response = await authorized_client.request(
        api_method, app.url_path_for(route_name, username=user.username)
    )
    assert change_following_response.status_code == status.HTTP_200_OK
    
    response = await authorized_client.get(
        app.url_path_for("profiles:get-profile", username=user.username)
    )
    profile = ProfileInResponse(**response.json())
    assert profile.profile.username == user.username
    assert profile.profile.following == following


@pytest.mark.parametrize(
    "api_method, route_name, following",
    (
        ("POST", "profiles:follow-user", True),
        ("DELETE", "profiles:unsubscribe-from-user", False),
    ),
)
async def test_user_can_not_change_following_state_to_the_same_twice(
    app: FastAPI,
    authorized_client: AsyncClient,
    pool: Pool,
    test_user: UserInDB,
    api_method: str,
    route_name: str,
    following: bool,
) -> None:
    async with pool.acquire() as conn:
        users_repo = UsersRepository(conn)
        user = await users_repo.create_user(
            username="user_for_following",
            email="test-for-following@email.com",
            password="password",
        )

        if following:
            profiles_repo = ProfilesRepository(conn)
            await profiles_repo.add_user_into_followers(
                target_user=user, requested_user=test_user
            )
    
    response = await authorized_client.request(
        api_method, app.url_path_for(route_name, username=user.username)
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.parametrize(
    "api_method, route_name",
    (("POST", "profiles:follow-user"), ("DELETE", "profiles:unsubscribe-from-user")),
)
async def test_user_can_not_change_following_state_for_him_self(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_user: UserInDB,
    api_method: str,
    route_name: str,
) -> None:
    response = await authorized_client.request(
        api_method, app.url_path_for(route_name, username=test_user.username)
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST



================================================
FILE: tests/test_api/test_routes/test_registration.py
================================================
import pytest
from asyncpg.pool import Pool
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST

from app.db.repositories.users import UsersRepository
from app.models.domain.users import UserInDB

pytestmark = pytest.mark.asyncio


async def test_user_success_registration(
    app: FastAPI, client: AsyncClient, pool: Pool
) -> None:
    email, username, password = "test@test.com", "username", "password"
    registration_json = {
        "user": {"email": email, "username": username, "password": password}
    }
    response = await client.post(
        app.url_path_for("auth:register"), json=registration_json
    )
    assert response.status_code == HTTP_201_CREATED

    async with pool.acquire() as conn:
        repo = UsersRepository(conn)
        user = await repo.get_user_by_email(email=email)
        assert user.email == email
        assert user.username == username
        assert user.check_password(password)


@pytest.mark.parametrize(
    "credentials_part, credentials_value",
    (("username", "free_username"), ("email", "free-email@tset.com")),
)
async def test_failed_user_registration_when_some_credentials_are_taken(
    app: FastAPI,
    client: AsyncClient,
    test_user: UserInDB,
    credentials_part: str,
    credentials_value: str,
) -> None:
    registration_json = {
        "user": {
            "email": "test@test.com",
            "username": "username",
            "password": "password",
        }
    }
    registration_json["user"][credentials_part] = credentials_value

    response = await client.post(
        app.url_path_for("auth:register"), json=registration_json
    )
    assert response.status_code == HTTP_400_BAD_REQUEST



================================================
FILE: tests/test_api/test_routes/test_tags.py
================================================
import pytest
from asyncpg.pool import Pool
from fastapi import FastAPI
from httpx import AsyncClient

from app.db.repositories.tags import TagsRepository

pytestmark = pytest.mark.asyncio


async def test_empty_list_when_no_tags_exist(app: FastAPI, client: AsyncClient) -> None:
    response = await client.get(app.url_path_for("tags:get-all"))
    assert response.json() == {"tags": []}


async def test_list_of_tags_when_tags_exist(
    app: FastAPI, client: AsyncClient, pool: Pool
) -> None:
    tags = ["tag1", "tag2", "tag3", "tag4", "tag1"]

    async with pool.acquire() as conn:
        tags_repo = TagsRepository(conn)
        await tags_repo.create_tags_that_dont_exist(tags=tags)
    
    response = await client.get(app.url_path_for("tags:get-all"))
    tags_from_response = response.json()["tags"]
    assert len(tags_from_response) == len(set(tags))
    assert all((tag in tags for tag in tags_from_response))



================================================
FILE: tests/test_api/test_routes/test_users.py
================================================
import pytest
from asyncpg.pool import Pool
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status

from app.db.repositories.users import UsersRepository
from app.models.domain.users import UserInDB
from app.models.schemas.users import UserInResponse

pytestmark = pytest.mark.asyncio


@pytest.fixture(params=("", "value", "Token value", "JWT value", "Bearer value"))
def wrong_authorization_header(request) -> str:
    return request.param


@pytest.mark.parametrize(
    "api_method, route_name",
    (("GET", "users:get-current-user"), ("PUT", "users:update-current-user")),
)
async def test_user_can_not_access_own_profile_if_not_logged_in(
    app: FastAPI,
    client: AsyncClient,
    test_user: UserInDB,
    api_method: str,
    route_name: str,
) -> None:
    response = await client.request(api_method, app.url_path_for(route_name))
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize(
    "api_method, route_name",
    (("GET", "users:get-current-user"), ("PUT", "users:update-current-user")),
)
async def test_user_can_not_retrieve_own_profile_if_wrong_token(
    app: FastAPI,
    client: AsyncClient,
    test_user: UserInDB,
    api_method: str,
    route_name: str,
    wrong_authorization_header: str,
) -> None:
    response = await client.request(
        api_method,
        app.url_path_for(route_name),
        headers={"Authorization": wrong_authorization_header},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_user_can_retrieve_own_profile(
    app: FastAPI, authorized_client: AsyncClient, test_user: UserInDB, token: str
) -> None:
    response = await authorized_client.get(app.url_path_for("users:get-current-user"))
    assert response.status_code == status.HTTP_200_OK

    user_profile = UserInResponse(**response.json())
    assert user_profile.user.email == test_user.email


@pytest.mark.parametrize(
    "update_field, update_value",
    (
        ("username", "new_username"),
        ("email", "new_email@email.com"),
        ("bio", "new bio"),
        ("image", "http://testhost.com/imageurl"),
    ),
)
async def test_user_can_update_own_profile(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_user: UserInDB,
    token: str,
    update_value: str,
    update_field: str,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": {update_field: update_value}},
    )
    assert response.status_code == status.HTTP_200_OK

    user_profile = UserInResponse(**response.json()).dict()
    assert user_profile["user"][update_field] == update_value


async def test_user_can_change_password(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_user: UserInDB,
    token: str,
    pool: Pool,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": {"password": "new_password"}},
    )
    assert response.status_code == status.HTTP_200_OK
    user_profile = UserInResponse(**response.json())

    async with pool.acquire() as connection:
        users_repo = UsersRepository(connection)
        user = await users_repo.get_user_by_username(
            username=user_profile.user.username
        )
    
    assert user.check_password("new_password")


@pytest.mark.parametrize(
    "credentials_part, credentials_value",
    (("username", "taken_username"), ("email", "taken@email.com")),
)
async def test_user_can_not_take_already_used_credentials(
    app: FastAPI,
    authorized_client: AsyncClient,
    pool: Pool,
    token: str,
    credentials_part: str,
    credentials_value: str,
) -> None:
    user_dict = {
        "username": "not_taken_username",
        "password": "password",
        "email": "free_email@email.com",
    }
    user_dict.update({credentials_part: credentials_value})
    async with pool.acquire() as conn:
        users_repo = UsersRepository(conn)
        await users_repo.create_user(**user_dict)

    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": {credentials_part: credentials_value}},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST



================================================
FILE: tests/test_db/__init__.py
================================================
[Empty file]


================================================
FILE: tests/test_db/test_queries/__init__.py
================================================
[Empty file]


================================================
FILE: tests/test_db/test_queries/test_tables.py
================================================
from app.db.queries.tables import TypedTable


def test_typed_table_uses_explicit_name() -> None:
    assert TypedTable("table_name").get_sql() == "table_name"


def test_typed_table_use_class_attribute_as_table_name() -> None:
    class NewTable(TypedTable):
        __table__ = "new_table"

    assert NewTable().get_table_name() == "new_table"


def test_typed_table_use_class_name_as_table_name() -> None:
    class NewTable(TypedTable):
        ...

    assert NewTable().get_table_name() == "NewTable"



================================================
FILE: tests/test_schemas/__init__.py
================================================
[Empty file]


================================================
FILE: tests/test_schemas/test_rw_model.py
================================================
from datetime import datetime

from app.models.domain.rwmodel import convert_datetime_to_realworld


def test_api_datetime_is_in_realworld_format() -> None:
    dt = datetime.fromisoformat("2019-10-27T02:21:42.844640")
    assert convert_datetime_to_realworld(dt) == "2019-10-27T02:21:42.844640Z"



================================================
FILE: tests/test_services/__init__.py
================================================
[Empty file]


================================================
FILE: tests/test_services/test_jwt.py
================================================
from datetime import timedelta

import jwt
import pytest

from app.models.domain.users import UserInDB
from app.services.jwt import (
    ALGORITHM,
    create_access_token_for_user,
    create_jwt_token,
    get_username_from_token,
)


def test_creating_jwt_token() -> None:
    token = create_jwt_token(
        jwt_content={"content": "payload"},
        secret_key="secret",
        expires_delta=timedelta(minutes=1),
    )
    parsed_payload = jwt.decode(token, "secret", algorithms=[ALGORITHM])

    assert parsed_payload["content"] == "payload"


def test_creating_token_for_user(test_user: UserInDB) -> None:
    token = create_access_token_for_user(user=test_user, secret_key="secret")
    parsed_payload = jwt.decode(token, "secret", algorithms=[ALGORITHM])

    assert parsed_payload["username"] == test_user.username


def test_retrieving_token_from_user(test_user: UserInDB) -> None:
    token = create_access_token_for_user(user=test_user, secret_key="secret")
    username = get_username_from_token(token, "secret")
    assert username == test_user.username


def test_error_when_wrong_token() -> None:
    with pytest.raises(ValueError):
        get_username_from_token("asdf", "asdf")


def test_error_when_wrong_token_shape() -> None:
    token = create_jwt_token(
        jwt_content={"content": "payload"},
        secret_key="secret",
        expires_delta=timedelta(minutes=1),
    )
    with pytest.raises(ValueError):
        get_username_from_token(token, "secret")



================================================
FILE: .github/dependabot.yml
================================================
version: 2

updates:
  - package-ecosystem: pip
    directory: "/"
    schedule:
      interval: monthly
      time: "12:00"
    pull-request-branch-name:
      separator: "-"
    open-pull-requests-limit: 10

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: monthly
      time: "12:00"
    pull-request-branch-name:
      separator: "-"
    open-pull-requests-limit: 10



================================================
FILE: .github/workflows/conduit.yml
================================================
name: API spec

on:
  push:
    branches:
      - "master"

  pull_request:
    branches:
      - "*"

jobs:
  api-spec:
    name: API spec tests

    runs-on: ubuntu-18.04
    
    strategy:
      matrix:
        python-version: [3.9]
    
    services:
      postgres:
        image: postgres:11.5-alpine
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: postgres
        ports:
          - 5432:5432
        options: --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
    
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4.2.0
        with:
          python-version: ${{ matrix.python-version }}
    
      - name: Install Poetry
        uses: snok/install-poetry@v1
        with:
          version: "1.1.12"
          virtualenvs-in-project: true
    
      - name: Set up cache
        uses: actions/cache@v3
        id: cache
        with:
          path: .venv
          key: venv-${{ runner.os }}-py-${{ matrix.python-version }}-poetry-${{ hashFiles('poetry.lock') }}
    
      - name: Ensure cache is healthy
        if: steps.cache.outputs.cache-hit == 'true'
        run: poetry run pip --version >/dev/null 2>&1 || rm -rf .venv
    
      - name: Install dependencies
        run: poetry install --no-interaction
    
      - name: Run newman and test service
        env:
          SECRET_KEY: secret_key
          DATABASE_URL: postgresql://postgres:postgres@localhost/postgres
        run: |
          poetry run alembic upgrade head
          poetry run uvicorn app.main:app &
          APIURL=http://localhost:8000/api ./postman/run-api-tests.sh
          poetry run alembic downgrade base



================================================
FILE: .github/workflows/deploy.yml
================================================
name: Deploy

on:
  push:
    branches:
      - master

env:
  IMAGE_NAME: nsidnev/fastapi-realworld-example-app
  DOCKER_USER: ${{ secrets.DOCKER_USER }}
  DOCKER_PASSWORD: ${{ secrets.DOCKER_PASSWORD }}

jobs:
  build:
    name: Build Container

    runs-on: ubuntu-18.04
    
    steps:
      - uses: actions/checkout@v3
    
      - name: Build image and publish to registry
        run: |
          docker build -t $IMAGE_NAME:latest .
          echo $DOCKER_PASSWORD | docker login -u $DOCKER_USER --password-stdin
          docker push $IMAGE_NAME:latest



================================================
FILE: .github/workflows/styles.yml
================================================
name: Styles

on:
  push:
    branches:
      - "master"

  pull_request:
    branches:
      - "*"

jobs:
  lint:
    name: Lint code

    runs-on: ubuntu-18.04
    
    strategy:
      matrix:
        python-version: [3.9]
    
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4.2.0
        with:
          python-version: ${{ matrix.python-version }}
    
      - name: Install Poetry
        uses: snok/install-poetry@v1
        with:
          version: "1.1.12"
          virtualenvs-in-project: true
    
      - name: Set up cache
        uses: actions/cache@v3
        id: cache
        with:
          path: .venv
          key: venv-${{ runner.os }}-py-${{ matrix.python-version }}-poetry-${{ hashFiles('poetry.lock') }}
    
      - name: Ensure cache is healthy
        if: steps.cache.outputs.cache-hit == 'true'
        run: poetry run pip --version >/dev/null 2>&1 || rm -rf .venv
    
      - name: Install dependencies
        run: poetry install --no-interaction
    
      - name: Run linters
        run: poetry run ./scripts/lint



================================================
FILE: .github/workflows/tests.yml
================================================
name: Tests

on:
  push:
    branches:
      - "master"

  pull_request:
    branches:
      - "*"

jobs:
  lint:
    name: Run tests

    runs-on: ubuntu-18.04
    
    strategy:
      matrix:
        python-version: [3.9]
    
    services:
      postgres:
        image: postgres:11.5-alpine
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: postgres
        ports:
          - 5432:5432
        options: --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
    
    steps:
      - uses: actions/checkout@v3
    
      - name: Set up Python
        uses: actions/setup-python@v4.2.0
        with:
          python-version: ${{ matrix.python-version }}
    
      - name: Install Poetry
        uses: snok/install-poetry@v1
        with:
          version: "1.1.12"
          virtualenvs-in-project: true
    
      - name: Set up cache
        uses: actions/cache@v3
        id: cache
        with:
          path: .venv
          key: venv-${{ runner.os }}-py-${{ matrix.python-version }}-poetry-${{ hashFiles('poetry.lock') }}
    
      - name: Ensure cache is healthy
        if: steps.cache.outputs.cache-hit == 'true'
        run: poetry run pip --version >/dev/null 2>&1 || rm -rf .venv
    
      - name: Install dependencies
        run: poetry install --no-interaction
    
      - name: Run tests
        env:
          SECRET_KEY: secret_key
          DATABASE_URL: postgresql://postgres:postgres@localhost/postgres
        run: |
          poetry run alembic upgrade head
          poetry run ./scripts/test
    
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3.1.0