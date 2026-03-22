#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT / "repos" / "fastapi-realworld-example-app"
OUTPUT_ROOT = ROOT / "generated" / "conduit"
SOURCE_DIR = OUTPUT_ROOT / "00_source"
BLUEPRINT_DIR = OUTPUT_ROOT / "01_blueprint"
UNDERSTAND_DIR = OUTPUT_ROOT / "02_understand"
LOCATE_DIR = OUTPUT_ROOT / "03_locate"
CODEGEN_DIR = OUTPUT_ROOT / "04_codegen"

PROJECT_NAME = "Conduit（fastapi-realworld-example-app）"
PROJECT_CONTEXT = (
    "Conduit 是一个 Medium 风格的内容发布与社交平台。用户可以注册登录、"
    "发布文章、关注作者、收藏内容、发表评论，并通过标签与关注关系发现内容。"
)

GLOBAL_DEPENDENCY_GRAPH = """graph TD
    Startup["系统启动与配置"] --> Auth["用户认证"]
    Startup --> UserMgmt["用户管理"]
    Startup --> Social["社交关系"]
    Startup --> Article["文章发布"]
    Startup --> Comment["评论互动"]
    Startup --> Tag["标签分类"]
    Startup --> Favorite["收藏系统"]
    Startup --> Feed["信息流"]
    Startup --> Storage["数据库连接与仓库层"]

    Auth --> UserMgmt
    Auth --> Social
    Auth --> Article
    Auth --> Comment
    Auth --> Favorite
    Auth --> Feed

    Social --> Feed
    Article --> Comment
    Article --> Favorite
    Article --> Feed
    Tag --> Article

    UserMgmt --> Storage
    Auth --> Storage
    Social --> Storage
    Article --> Storage
    Comment --> Storage
    Tag --> Storage
    Favorite --> Storage
    Feed --> Storage
"""


MODULES: list[dict[str, Any]] = [
    {
        "index": 1,
        "slug": "01_user-auth",
        "name": "用户认证",
        "paths": [
            "app/api/routes/authentication.py",
            "app/api/dependencies/authentication.py",
            "app/services/authentication.py",
            "app/services/jwt.py",
            "app/db/repositories/users.py",
            "app/models/domain/users.py",
            "app/resources/strings.py",
        ],
        "responsibility": "负责账号注册、邮箱密码登录，以及后续受保护接口的身份校验。",
        "entry_points": [
            "POST /api/users",
            "POST /api/users/login",
            "所有带 Authorization 头的受保护接口",
        ],
        "depends_on": ["数据库连接与仓库层", "系统启动与配置"],
        "used_by": ["用户管理", "社交关系", "文章发布", "评论互动", "收藏系统", "信息流"],
        "pm_note": "主链路已经可用，但没有登录失败限流，也没有令牌吊销机制，安全边界偏薄。",
        "card_path": "app/api/routes/authentication.py",
        "what": "访客提交注册或登录表单后，系统验证账号信息并返回后续请求可复用的 JWT 令牌。",
        "inputs": [
            "注册表单 `user.email / user.username / user.password`（来自访客）",
            "登录表单 `user.email / user.password`（来自已注册用户）",
            "Authorization 请求头（来自后续所有受保护请求）",
            "系统密钥与令牌前缀（来自配置）",
        ],
        "outputs": [
            "注册成功后的用户资料与登录令牌",
            "登录成功后的用户资料与登录令牌",
            "鉴权成功后注入到路由中的当前用户对象",
            "失败时的 400/403 错误响应",
        ],
        "branches": [
            {
                "condition": "注册时用户名已存在",
                "result": "直接返回 400 和 `USERNAME_TAKEN`，不创建账号。",
                "code_ref": "app/api/routes/authentication.py:L67-L71",
            },
            {
                "condition": "注册时邮箱已存在",
                "result": "直接返回 400 和 `EMAIL_TAKEN`，不创建账号。",
                "code_ref": "app/api/routes/authentication.py:L73-L77",
            },
            {
                "condition": "登录时邮箱不存在或密码不匹配",
                "result": "统一返回 400 和 `INCORRECT_LOGIN_INPUT`，避免暴露账号是否存在。",
                "code_ref": "app/api/routes/authentication.py:L28-L39",
            },
            {
                "condition": "受保护请求的 token 格式错误、签名错误或用户不存在",
                "result": "统一返回 403 和 `MALFORMED_PAYLOAD`。",
                "code_ref": "app/api/dependencies/authentication.py:L46-L109",
            },
        ],
        "side_effects": [
            "注册会向 `users` 表写入新账号，并同时写入新的 salt 与加密密码。证据：`app/db/repositories/users.py:L29-L48`。",
            "注册和登录都会签发 7 天有效的 JWT。证据：`app/services/jwt.py:L12-L32`。",
            "后续受保护请求会从 token 反解出用户名，再回库查一次用户。证据：`app/api/dependencies/authentication.py:L78-L100`。",
        ],
        "blast_radius": [
            "任何依赖 `get_current_user_authorizer()` 的接口都会被影响，包括资料修改、关注、发文、评论、收藏和信息流。",
            "登录文案或错误格式变化会直接影响前端表单提示与相关 API 测试。",
        ],
        "key_code_refs": [
            "app/api/routes/authentication.py:L22-L93",
            "app/api/dependencies/authentication.py:L35-L109",
            "app/services/authentication.py:L5-L20",
            "app/services/jwt.py:L15-L40",
            "app/db/repositories/users.py:L29-L81",
            "app/models/domain/users.py:L15-L24",
            "app/resources/strings.py:L3-L25",
        ],
        "understand_pm_note": "当前错误表达偏技术化，且没有任何登录限流或设备级撤销机制，后续产品化时需要优先补。",
        "understand_graph": """graph TD
    A["访客提交注册/登录表单"] --> B["认证路由\\napp/api/routes/authentication.py:L22-L93"]
    B --> C["重复凭证检查\\napp/services/authentication.py:L5-L20"]
    B --> D["用户仓库\\napp/db/repositories/users.py:L10-L81"]
    B --> E["JWT 服务\\napp/services/jwt.py:L15-L40"]
    F["受保护接口"] --> G["鉴权依赖\\napp/api/dependencies/authentication.py:L35-L109"]
    G --> D
    G --> E
""",
        "locate_issue": "用户注册时填了已存在邮箱，为什么看到的是生硬英文报错？",
        "locate_matched_modules": [
            "用户认证：注册接口直接决定返回什么错误结构和错误文案。",
            "数据库连接与仓库层：邮箱是否已存在最终由 `users` 仓库查库决定。",
        ],
        "locate_call_chain": """graph TD
    A["用户提交注册表单"] --> B["register()\\napp/api/routes/authentication.py:L62-L79"]
    B --> C["check_email_is_taken()\\napp/services/authentication.py:L14-L20"]
    C --> D["get_user_by_email()\\napp/db/repositories/users.py:L10-L15"]
    D --> E["EMAIL_TAKEN 常量\\napp/resources/strings.py:L8-L10"]
    E --> F["返回 400 错误响应"]
""",
        "locate_exact_locations": [
            {
                "file": "app/api/routes/authentication.py",
                "line": 73,
                "why_it_matters": "邮箱命中重复检查后，注册路由在这里直接把 `strings.EMAIL_TAKEN` 放进错误响应。",
                "confidence": 0.99,
            },
            {
                "file": "app/services/authentication.py",
                "line": 14,
                "why_it_matters": "这里只负责判断邮箱是否存在，不负责文案表达，所以真正的问题不在这里。",
                "confidence": 0.93,
            },
            {
                "file": "app/resources/strings.py",
                "line": 10,
                "why_it_matters": "这里定义了用户最终看到的英文提示文本。",
                "confidence": 0.98,
            },
        ],
        "locate_diagnosis": (
            "相关模块是用户认证。当前链路本身没有判错：注册接口先查邮箱，命中后正常返回 400。"
            "真正导致“像系统报错”的原因，是错误文本直接取自 `app/resources/strings.py:L10`，"
            "内容仍是后端内部表达。开发者应该优先打开 `app/api/routes/authentication.py:L73-L76` "
            "和 `app/resources/strings.py:L8-L10`。"
        ),
        "codegen_request": "把邮箱已注册提示改成中文友好文案，并在错误响应里带一个供前端识别的去登录动作。",
        "codegen_change_summary": [
            {
                "file": "app/resources/strings.py",
                "before": "邮箱重复时只返回英文技术文案。",
                "after": "改成中文友好提示，让用户知道下一步该去登录。",
            },
            {
                "file": "app/api/routes/authentication.py",
                "before": "邮箱重复时只返回纯字符串 `detail`。",
                "after": "改成结构化错误对象，补充 `action=login` 和按钮文案。",
            },
            {
                "file": "tests/test_api/test_routes/test_registration.py",
                "before": "测试只校验 400 状态码，没有验证错误结构。",
                "after": "补上邮箱重复场景的结构化错误断言，避免回归。",
            },
        ],
        "codegen_diff": """diff --git a/app/resources/strings.py b/app/resources/strings.py
@@
-EMAIL_TAKEN = "user with this email already exists"
+EMAIL_TAKEN = "该邮箱已注册，请直接登录或使用其他邮箱"
diff --git a/app/api/routes/authentication.py b/app/api/routes/authentication.py
@@
     if await check_email_is_taken(users_repo, user_create.email):
         raise HTTPException(
             status_code=HTTP_400_BAD_REQUEST,
-            detail=strings.EMAIL_TAKEN,
+            detail={
+                "message": strings.EMAIL_TAKEN,
+                "action": "login",
+                "action_label": "去登录",
+            },
         )
diff --git a/tests/test_api/test_routes/test_registration.py b/tests/test_api/test_routes/test_registration.py
@@
     response = await client.post(
         app.url_path_for("auth:register"), json=registration_json
     )
     assert response.status_code == HTTP_400_BAD_REQUEST
+    if credentials_part == "email":
+        assert response.json()["detail"]["action"] == "login"
+        assert "登录" in response.json()["detail"]["action_label"]
""",
        "codegen_blast_radius": [
            "注册页前端如果默认把 `detail` 当字符串渲染，需要兼容邮箱重复时的对象格式。",
            "测试用例与 API 文档需要同步更新错误结构说明。",
        ],
        "codegen_verification_steps": [
            {
                "step": "先注册一个邮箱为 `test@test.com` 的新账号。",
                "expected_result": "注册成功，返回用户信息和 token。",
            },
            {
                "step": "再次使用相同邮箱发起注册。",
                "expected_result": "返回 400，`detail.action` 为 `login`，提示文案为中文友好表达。",
            },
        ],
    },
    {
        "index": 2,
        "slug": "02_user-management",
        "name": "用户管理",
        "paths": [
            "app/api/routes/users.py",
            "app/models/schemas/users.py",
            "app/db/repositories/users.py",
            "app/services/jwt.py",
        ],
        "responsibility": "负责读取当前用户资料、修改用户名/邮箱/密码/简介/头像，并在修改后返回新的登录令牌。",
        "entry_points": [
            "GET /api/user",
            "PUT /api/user",
        ],
        "depends_on": ["用户认证", "数据库连接与仓库层"],
        "used_by": ["头像展示", "文章作者信息", "个人资料页", "后续所有带新 token 的请求"],
        "pm_note": "修改资料链路能跑通，但缺少密码强度校验和邮箱真实性校验。",
        "card_path": "app/api/routes/users.py",
        "what": "已登录用户进入个人设置后，系统允许他查看或修改自己的公开资料与密码。",
        "inputs": [
            "Authorization 请求头（来自已登录用户）",
            "资料更新体 `user.username / email / password / bio / image`（来自设置页）",
        ],
        "outputs": [
            "当前用户资料",
            "修改成功后的最新用户资料与新 token",
            "用户名/邮箱冲突时的 400 错误",
        ],
        "branches": [
            {
                "condition": "用户修改成已被占用的用户名",
                "result": "返回 400 和 `USERNAME_TAKEN`，不落库。",
                "code_ref": "app/api/routes/users.py:L45-L50",
            },
            {
                "condition": "用户修改成已被占用的邮箱",
                "result": "返回 400 和 `EMAIL_TAKEN`，不落库。",
                "code_ref": "app/api/routes/users.py:L52-L57",
            },
            {
                "condition": "用户提交了新密码",
                "result": "仓库层会重新生成 salt 并重算哈希密码。",
                "code_ref": "app/db/repositories/users.py:L66-L79",
            },
            {
                "condition": "请求没有合法 token",
                "result": "鉴权依赖直接返回 403，请求进不到资料路由。",
                "code_ref": "app/api/dependencies/authentication.py:L46-L109",
            },
        ],
        "side_effects": [
            "修改资料会更新 `users` 表，并覆盖 username/email/bio/image 或密码哈希。证据：`app/db/repositories/users.py:L50-L81`。",
            "资料读写完成后，会重新签发一个新 token。证据：`app/api/routes/users.py:L59-L72`。",
        ],
        "blast_radius": [
            "用户名和头像变化会影响文章作者展示、评论作者展示以及 profile 页面。",
            "密码修改策略会直接影响登录成功率与账号安全性。",
        ],
        "key_code_refs": [
            "app/api/routes/users.py:L18-L72",
            "app/models/schemas/users.py:L18-L31",
            "app/db/repositories/users.py:L50-L81",
            "app/services/jwt.py:L27-L40",
        ],
        "understand_pm_note": "密码字段在更新场景里没有最小长度约束，意味着弱密码可以直接生效。",
        "understand_graph": """graph TD
    A["用户打开资料页"] --> B["GET /api/user\\napp/api/routes/users.py:L18-L35"]
    A --> C["PUT /api/user\\napp/api/routes/users.py:L38-L72"]
    B --> D["鉴权依赖\\napp/api/dependencies/authentication.py:L78-L109"]
    C --> D
    C --> E["重复凭证检查\\napp/services/authentication.py:L5-L20"]
    C --> F["用户仓库更新\\napp/db/repositories/users.py:L50-L81"]
    C --> G["重新签发 token\\napp/services/jwt.py:L27-L32"]
""",
        "locate_issue": "为什么用户可以把密码改成非常短的值？",
        "locate_matched_modules": [
            "用户管理：密码更新请求的 schema 和路由都在这里。",
            "用户认证：真正写入的新密码会继续影响后续登录行为。",
        ],
        "locate_call_chain": """graph TD
    A["用户提交 PUT /api/user"] --> B["UserInUpdate\\napp/models/schemas/users.py:L18-L23"]
    B --> C["update_current_user()\\napp/api/routes/users.py:L38-L59"]
    C --> D["update_user()\\napp/db/repositories/users.py:L50-L79"]
    D --> E["change_password()\\napp/models/domain/users.py:L22-L24"]
""",
        "locate_exact_locations": [
            {
                "file": "app/models/schemas/users.py",
                "line": 21,
                "why_it_matters": "更新场景的密码字段是 `Optional[str]`，没有任何 `min_length` 或复杂度约束。",
                "confidence": 0.99,
            },
            {
                "file": "app/api/routes/users.py",
                "line": 59,
                "why_it_matters": "路由拿到请求体后会直接把密码透传给仓库层，没有额外业务校验。",
                "confidence": 0.95,
            },
            {
                "file": "app/db/repositories/users.py",
                "line": 66,
                "why_it_matters": "只要 `password` 非空，这里就会立即重算哈希并落库。",
                "confidence": 0.97,
            },
        ],
        "locate_diagnosis": (
            "相关模块是用户管理。当前逻辑对密码更新几乎没有产品层防线："
            "`UserInUpdate.password` 只是一个可选字符串，没有长度或复杂度要求，"
            "路由也直接把它透传给仓库层。最该先看的位置是 `app/models/schemas/users.py:L18-L23`。"
        ),
        "codegen_request": "给修改密码接口增加最小长度 8 的校验，避免弱密码直接生效。",
        "codegen_change_summary": [
            {
                "file": "app/models/schemas/users.py",
                "before": "密码字段只有类型约束，没有最小长度要求。",
                "after": "用 `Field(min_length=8)` 给更新场景加最基本的安全门槛。",
            },
            {
                "file": "tests/test_api/test_routes/test_users.py",
                "before": "测试只覆盖修改成功，不覆盖弱密码被拒绝。",
                "after": "增加 422 场景，确保短密码不能通过校验。",
            },
        ],
        "codegen_diff": """diff --git a/app/models/schemas/users.py b/app/models/schemas/users.py
@@
-from pydantic import BaseModel, EmailStr, HttpUrl
+from pydantic import BaseModel, EmailStr, Field, HttpUrl
@@
-    password: Optional[str] = None
+    password: Optional[str] = Field(None, min_length=8)
diff --git a/tests/test_api/test_routes/test_users.py b/tests/test_api/test_routes/test_users.py
@@
 async def test_user_can_change_password(
@@
     assert user.check_password("new_password")
+
+async def test_user_can_not_change_password_to_too_short_value(
+    app: FastAPI,
+    authorized_client: AsyncClient,
+    token: str,
+) -> None:
+    response = await authorized_client.put(
+        app.url_path_for("users:update-current-user"),
+        json={"user": {"password": "short"}},
+    )
+    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
""",
        "codegen_blast_radius": [
            "设置页如果允许小于 8 位的密码，需要同步前端表单规则。",
            "相关自动化测试和接口文档都需要更新预期。",
        ],
        "codegen_verification_steps": [
            {
                "step": "使用已登录用户调用 `PUT /api/user`，传入 `password=short`。",
                "expected_result": "接口返回 422，提示密码长度不满足要求。",
            },
            {
                "step": "再次传入一个长度不少于 8 的新密码。",
                "expected_result": "接口返回 200，且新密码可用于后续登录。",
            },
        ],
    },
    {
        "index": 3,
        "slug": "03_social-follow",
        "name": "社交关系",
        "paths": [
            "app/api/routes/profiles.py",
            "app/api/dependencies/profiles.py",
            "app/db/repositories/profiles.py",
            "app/db/queries/sql/profiles.sql",
            "app/models/domain/profiles.py",
        ],
        "responsibility": "负责查看作者资料，以及建立或取消用户之间的关注关系。",
        "entry_points": [
            "GET /api/profiles/{username}",
            "POST /api/profiles/{username}/follow",
            "DELETE /api/profiles/{username}/follow",
        ],
        "depends_on": ["用户认证", "数据库连接与仓库层"],
        "used_by": ["文章详情页作者卡片", "信息流"],
        "pm_note": "关注接口不是幂等设计，前端重试或重复点击会直接收到 400。",
        "card_path": "app/api/routes/profiles.py",
        "what": "用户查看某个作者主页时，系统需要告诉他对方资料以及当前是否已关注；点击关注按钮时则写入关注关系。",
        "inputs": [
            "路径参数 `username`（来自作者资料页或文章作者卡片）",
            "Authorization 请求头（来自已登录用户的关注/取关操作）",
        ],
        "outputs": [
            "作者资料对象 `profile`",
            "关注或取关后的最新 `following` 状态",
            "自关注、重复关注、重复取关等异常时的 400 错误",
        ],
        "branches": [
            {
                "condition": "查询的用户名不存在",
                "result": "依赖层直接返回 404 和 `USER_DOES_NOT_EXIST_ERROR`。",
                "code_ref": "app/api/dependencies/profiles.py:L15-L29",
            },
            {
                "condition": "用户试图关注自己",
                "result": "返回 400 和 `UNABLE_TO_FOLLOW_YOURSELF`。",
                "code_ref": "app/api/routes/profiles.py:L37-L41",
            },
            {
                "condition": "用户重复点击关注",
                "result": "返回 400 和 `USER_IS_ALREADY_FOLLOWED`。",
                "code_ref": "app/api/routes/profiles.py:L43-L47",
            },
            {
                "condition": "用户重复点击取关",
                "result": "返回 400 和 `USER_IS_NOT_FOLLOWED`。",
                "code_ref": "app/api/routes/profiles.py:L73-L77",
            },
        ],
        "side_effects": [
            "关注成功会向 `followers_to_followings` 表插入一条关系记录。证据：`app/db/repositories/profiles.py:L50-L61`。",
            "取关成功会删除对应关系记录。证据：`app/db/repositories/profiles.py:L63-L74`。",
        ],
        "blast_radius": [
            "关注关系变化会直接影响 feed 内容是否出现某位作者的文章。",
            "作者资料接口的 `following` 状态会影响文章详情页和 profile 页按钮文案。",
        ],
        "key_code_refs": [
            "app/api/routes/profiles.py:L16-L84",
            "app/api/dependencies/profiles.py:L15-L29",
            "app/db/repositories/profiles.py:L19-L74",
            "app/db/queries/sql/profiles.sql:L1-L36",
        ],
        "understand_pm_note": "接口已经保护了“不能关注自己”，但对重复请求的处理偏硬，前端重试体验不好。",
        "understand_graph": """graph TD
    A["用户打开作者资料页"] --> B["资料依赖\\napp/api/dependencies/profiles.py:L15-L29"]
    B --> C["ProfilesRepository\\napp/db/repositories/profiles.py:L19-L34"]
    C --> D["UsersRepository\\napp/db/repositories/users.py:L17-L27"]
    C --> E["关注关系 SQL\\napp/db/queries/sql/profiles.sql:L1-L36"]
    F["用户点击关注/取关"] --> G["资料路由\\napp/api/routes/profiles.py:L27-L84"]
    G --> E
""",
        "locate_issue": "为什么前端重复发送关注请求会直接报 400？",
        "locate_matched_modules": [
            "社交关系：重复关注的错误就是在 follow 路由里直接抛出的。",
            "信息流：虽然问题发生在关注按钮，但它最终会影响 feed 是否继续刷新。",
        ],
        "locate_call_chain": """graph TD
    A["用户再次点击 Follow"] --> B["follow_for_user()\\napp/api/routes/profiles.py:L32-L54"]
    B --> C["get_profile_by_username_from_path()\\napp/api/dependencies/profiles.py:L15-L29"]
    C --> D["Profile.following 已为 True\\napp/db/repositories/profiles.py:L27-L34"]
    D --> E["抛出 USER_IS_ALREADY_FOLLOWED\\napp/api/routes/profiles.py:L43-L47"]
""",
        "locate_exact_locations": [
            {
                "file": "app/api/routes/profiles.py",
                "line": 43,
                "why_it_matters": "这里明确规定：如果 `profile.following` 已经是真，接口就返回 400。",
                "confidence": 0.99,
            },
            {
                "file": "app/db/repositories/profiles.py",
                "line": 27,
                "why_it_matters": "资料对象在仓库层被注入了 `following` 状态，后续路由就是根据它决定是否报错。",
                "confidence": 0.94,
            },
        ],
        "locate_diagnosis": (
            "相关模块是社交关系。当前逻辑把重复关注视为业务错误而不是幂等重试，"
            "因此前端如果因双击、重试或网络抖动发出第二次请求，就会在 "
            "`app/api/routes/profiles.py:L43-L47` 收到 400。"
        ),
        "codegen_request": "把关注/取关接口改成幂等设计，重复请求直接返回当前状态，不再报错。",
        "codegen_change_summary": [
            {
                "file": "app/api/routes/profiles.py",
                "before": "重复关注或重复取关都会抛 400。",
                "after": "改成直接返回当前 profile，让接口天然支持前端重试。",
            },
            {
                "file": "tests/test_api/test_routes/test_profiles.py",
                "before": "测试把重复请求视作失败场景。",
                "after": "改成验证重复请求也返回 200，并保持状态不变。",
            },
        ],
        "codegen_diff": """diff --git a/app/api/routes/profiles.py b/app/api/routes/profiles.py
@@
-    if profile.following:
-        raise HTTPException(
-            status_code=HTTP_400_BAD_REQUEST,
-            detail=strings.USER_IS_ALREADY_FOLLOWED,
-        )
+    if profile.following:
+        return ProfileInResponse(profile=profile)
@@
-    if not profile.following:
-        raise HTTPException(
-            status_code=HTTP_400_BAD_REQUEST,
-            detail=strings.USER_IS_NOT_FOLLOWED,
-        )
+    if not profile.following:
+        return ProfileInResponse(profile=profile)
diff --git a/tests/test_api/test_routes/test_profiles.py b/tests/test_api/test_routes/test_profiles.py
@@
-async def test_user_can_not_change_following_state_to_the_same_twice(
+async def test_follow_endpoints_are_idempotent(
@@
-    assert response.status_code == status.HTTP_400_BAD_REQUEST
+    assert response.status_code == status.HTTP_200_OK
""",
        "codegen_blast_radius": [
            "前端如果依赖 400 来区分“已关注”状态，需要改成根据返回的 `profile.following` 判断。",
            "与关注按钮相关的自动化测试需要同步调整预期。",
        ],
        "codegen_verification_steps": [
            {
                "step": "对同一作者连续发送两次 `POST /api/profiles/{username}/follow`。",
                "expected_result": "两次都返回 200，第二次不会新增重复关注关系。",
            },
            {
                "step": "对未关注作者连续发送两次 `DELETE /api/profiles/{username}/follow`。",
                "expected_result": "两次都返回 200，最终状态仍是 `following=false`。",
            },
        ],
    },
    {
        "index": 4,
        "slug": "04_article-authoring",
        "name": "文章发布",
        "paths": [
            "app/api/routes/articles/articles_resource.py",
            "app/api/dependencies/articles.py",
            "app/services/articles.py",
            "app/db/repositories/articles.py",
            "app/db/queries/sql/articles.sql",
        ],
        "responsibility": "负责文章的创建、列表查询、详情读取、编辑与删除。",
        "entry_points": [
            "GET /api/articles",
            "POST /api/articles",
            "GET /api/articles/{slug}",
            "PUT /api/articles/{slug}",
            "DELETE /api/articles/{slug}",
        ],
        "depends_on": ["用户认证", "标签分类", "社交关系", "数据库连接与仓库层"],
        "used_by": ["评论互动", "收藏系统", "信息流"],
        "pm_note": "文章标题会直接被 slugify 成 slug；同标题二次发布时当前实现直接报错，没有兜底生成唯一 slug。",
        "card_path": "app/api/routes/articles/articles_resource.py",
        "what": "创作者发布文章时，系统负责生成 slug、写入正文与标签，并在后续支持列表、详情、编辑、删除等主流程。",
        "inputs": [
            "文章发布体 `title / description / body / tagList`（来自编辑器）",
            "可选查询参数 `tag / author / favorited / limit / offset`（来自列表页）",
            "路径参数 `slug`（来自文章详情和编辑页）",
        ],
        "outputs": [
            "文章详情对象或文章列表",
            "创建成功后的文章 slug",
            "作者无权限或文章不存在时的 403/404",
        ],
        "branches": [
            {
                "condition": "创建文章时 slug 已存在",
                "result": "直接返回 400 和 `ARTICLE_ALREADY_EXISTS`。",
                "code_ref": "app/api/routes/articles/articles_resource.py:L64-L69",
            },
            {
                "condition": "用户编辑或删除不是自己写的文章",
                "result": "权限依赖直接返回 403。",
                "code_ref": "app/api/dependencies/articles.py:L51-L59",
            },
            {
                "condition": "文章带有新标签",
                "result": "先补建不存在的标签，再建立文章和标签的关联关系。",
                "code_ref": "app/db/repositories/articles.py:L44-L57",
            },
            {
                "condition": "文章 slug 在库里不存在",
                "result": "读取依赖返回 404 和 `ARTICLE_DOES_NOT_EXIST_ERROR`。",
                "code_ref": "app/api/dependencies/articles.py:L37-L48",
            },
        ],
        "side_effects": [
            "创建文章会写入 `articles` 表，并可能顺带创建 `tags` 与 `articles_to_tags` 关系。证据：`app/db/repositories/articles.py:L34-L63`。",
            "删除文章会从 `articles` 表移除记录。证据：`app/db/repositories/articles.py:L93-L100`。",
            "列表和详情查询会额外补出作者资料、标签列表与收藏数。证据：`app/db/repositories/articles.py:L294-L330`。",
        ],
        "blast_radius": [
            "slug 生成规则变化会影响文章详情页 URL、评论路径、收藏路径与 feed 中的文章链接。",
            "标签写入规则变化会影响标签页与文章详情的 tagList。",
        ],
        "key_code_refs": [
            "app/api/routes/articles/articles_resource.py:L30-L120",
            "app/api/dependencies/articles.py:L21-L59",
            "app/services/articles.py:L9-L23",
            "app/db/repositories/articles.py:L34-L330",
            "app/db/queries/sql/articles.sql:L37-L116",
        ],
        "understand_pm_note": "创建链路很直接，但 slug 冲突的处理还是“拒绝用户”，不是“帮用户自动化兜底”。",
        "understand_graph": """graph TD
    A["创作者提交文章"] --> B["文章路由\\napp/api/routes/articles/articles_resource.py:L53-L79"]
    B --> C["slug 生成\\napp/services/articles.py:L18-L19"]
    B --> D["ArticlesRepository.create_article\\napp/db/repositories/articles.py:L34-L63"]
    D --> E["标签仓库\\napp/db/repositories/tags.py:L7-L13"]
    F["文章详情/编辑/删除"] --> G["文章依赖\\napp/api/dependencies/articles.py:L37-L59"]
    G --> D
""",
        "locate_issue": "为什么同标题文章第二次发布会失败？",
        "locate_matched_modules": [
            "文章发布：slug 的生成与冲突检查都发生在创建文章主链路里。",
            "标签分类：虽然问题不在标签，但创建文章时会顺带触发标签写入。",
        ],
        "locate_call_chain": """graph TD
    A["用户提交标题相同的新文章"] --> B["create_new_article()\\napp/api/routes/articles/articles_resource.py:L59-L79"]
    B --> C["get_slug_for_article()\\napp/services/articles.py:L18-L19"]
    C --> D["check_article_exists()\\napp/services/articles.py:L9-L15"]
    D --> E["get_article_by_slug()\\napp/db/repositories/articles.py:L237-L252"]
    E --> F["ARTICLE_ALREADY_EXISTS\\napp/api/routes/articles/articles_resource.py:L65-L69"]
""",
        "locate_exact_locations": [
            {
                "file": "app/services/articles.py",
                "line": 18,
                "why_it_matters": "标题会被直接 slugify，重复标题自然会得到同一个 slug。",
                "confidence": 0.98,
            },
            {
                "file": "app/api/routes/articles/articles_resource.py",
                "line": 65,
                "why_it_matters": "命中已存在 slug 后，路由直接返回 400，没有任何自动补救逻辑。",
                "confidence": 0.99,
            },
        ],
        "locate_diagnosis": (
            "相关模块是文章发布。问题根源不是数据库异常，而是当前产品规则只允许“标题转 slug 后唯一”。"
            "同标题会生成同一 slug，并在 `app/api/routes/articles/articles_resource.py:L64-L69` 被直接拒绝。"
        ),
        "codegen_request": "当标题冲突时自动生成递增 slug，例如 `test-slug-2`，而不是直接报错。",
        "codegen_change_summary": [
            {
                "file": "app/services/articles.py",
                "before": "只有 `get_slug_for_article()`，没有唯一 slug 生成器。",
                "after": "增加异步唯一 slug 生成逻辑，循环检查冲突并追加序号。",
            },
            {
                "file": "app/api/routes/articles/articles_resource.py",
                "before": "创建文章时一旦 slug 冲突就立即返回 400。",
                "after": "改成调用唯一 slug 生成器，继续完成创建。",
            },
            {
                "file": "tests/test_api/test_routes/test_articles.py",
                "before": "测试把重复标题视作失败。",
                "after": "改成验证第二篇文章也能创建成功，并拿到带序号的新 slug。",
            },
        ],
        "codegen_diff": """diff --git a/app/services/articles.py b/app/services/articles.py
@@
 def get_slug_for_article(title: str) -> str:
     return slugify(title)
+
+async def get_unique_slug_for_article(
+    articles_repo: ArticlesRepository,
+    title: str,
+) -> str:
+    base_slug = get_slug_for_article(title)
+    slug = base_slug
+    suffix = 1
+    while await check_article_exists(articles_repo, slug):
+        suffix += 1
+        slug = f"{base_slug}-{suffix}"
+    return slug
diff --git a/app/api/routes/articles/articles_resource.py b/app/api/routes/articles/articles_resource.py
@@
-from app.services.articles import check_article_exists, get_slug_for_article
+from app.services.articles import get_unique_slug_for_article
@@
-    slug = get_slug_for_article(article_create.title)
-    if await check_article_exists(articles_repo, slug):
-        raise HTTPException(
-            status_code=status.HTTP_400_BAD_REQUEST,
-            detail=strings.ARTICLE_ALREADY_EXISTS,
-        )
+    slug = await get_unique_slug_for_article(articles_repo, article_create.title)
diff --git a/tests/test_api/test_routes/test_articles.py b/tests/test_api/test_routes/test_articles.py
@@
-async def test_user_can_not_create_article_with_duplicated_slug(
+async def test_user_can_create_article_with_duplicated_title_and_receive_unique_slug(
@@
-    assert response.status_code == status.HTTP_400_BAD_REQUEST
+    assert response.status_code == status.HTTP_201_CREATED
+    assert ArticleInResponse(**response.json()).article.slug == "test-slug-2"
""",
        "codegen_blast_radius": [
            "文章 URL 规则会变化，前端与 SEO 相关逻辑要接受递增 slug。",
            "任何基于 slug 唯一失败提示的前端交互都需要同步更新。",
        ],
        "codegen_verification_steps": [
            {
                "step": "先创建标题为 `Test Slug` 的文章，再重复创建一次同标题文章。",
                "expected_result": "第二次也返回 201，新文章 slug 自动变成 `test-slug-2`。",
            },
            {
                "step": "访问两篇文章的详情页与编辑页。",
                "expected_result": "两篇文章都能独立打开，不会互相覆盖。",
            },
        ],
    },
    {
        "index": 5,
        "slug": "05_comments",
        "name": "评论互动",
        "paths": [
            "app/api/routes/comments.py",
            "app/api/dependencies/comments.py",
            "app/db/repositories/comments.py",
            "app/db/queries/sql/comments.sql",
            "app/models/schemas/comments.py",
        ],
        "responsibility": "负责按文章查看评论、发表评论，以及删除自己写的评论。",
        "entry_points": [
            "GET /api/articles/{slug}/comments",
            "POST /api/articles/{slug}/comments",
            "DELETE /api/articles/{slug}/comments/{comment_id}",
        ],
        "depends_on": ["用户认证", "文章发布", "社交关系", "数据库连接与仓库层"],
        "used_by": ["文章详情页"],
        "pm_note": "评论功能只有增删，没有编辑、审核和频率限制。",
        "card_path": "app/api/routes/comments.py",
        "what": "读者进入文章详情页后，可以查看评论并发表新评论；作者本人也可以删除自己的评论。",
        "inputs": [
            "路径参数 `slug` 与 `comment_id`（来自文章详情页）",
            "评论创建体 `comment.body`（来自评论输入框）",
            "Authorization 请求头（来自已登录用户）",
        ],
        "outputs": [
            "评论列表",
            "新创建的评论对象",
            "删除成功后的 204 响应",
            "无权限或评论不存在时的 403/404",
        ],
        "branches": [
            {
                "condition": "文章不存在",
                "result": "评论路由依赖先返回 404，后续评论逻辑不会执行。",
                "code_ref": "app/api/dependencies/articles.py:L37-L48",
            },
            {
                "condition": "用户新增评论",
                "result": "向 `commentaries` 表插入一条记录，并回填作者资料。",
                "code_ref": "app/db/repositories/comments.py:L61-L78",
            },
            {
                "condition": "用户尝试删除别人的评论",
                "result": "评论权限依赖返回 403。",
                "code_ref": "app/api/dependencies/comments.py:L39-L47",
            },
            {
                "condition": "评论 id 不存在",
                "result": "评论依赖返回 404 和 `COMMENT_DOES_NOT_EXIST`。",
                "code_ref": "app/api/dependencies/comments.py:L16-L36",
            },
        ],
        "side_effects": [
            "新增评论会向 `commentaries` 表写入记录。证据：`app/db/queries/sql/comments.sql:L20-L34`。",
            "删除评论会真正从表中移除对应数据。证据：`app/db/queries/sql/comments.sql:L36-L40`。",
        ],
        "blast_radius": [
            "评论删除权限变化会影响文章详情页的操作按钮展示。",
            "评论模型变化会影响文章详情的评论列表结构。",
        ],
        "key_code_refs": [
            "app/api/routes/comments.py:L26-L71",
            "app/api/dependencies/comments.py:L16-L47",
            "app/db/repositories/comments.py:L19-L103",
            "app/db/queries/sql/comments.sql:L1-L40",
            "app/models/schemas/comments.py:L7-L16",
        ],
        "understand_pm_note": "评论从产品角度还停留在“留言板 1.0”，没有编辑、审核和回复树结构。",
        "understand_graph": """graph TD
    A["文章详情页"] --> B["评论路由\\napp/api/routes/comments.py:L26-L71"]
    B --> C["文章依赖\\napp/api/dependencies/articles.py:L37-L48"]
    B --> D["评论依赖\\napp/api/dependencies/comments.py:L16-L47"]
    B --> E["CommentsRepository\\napp/db/repositories/comments.py:L19-L103"]
    E --> F["评论 SQL\\napp/db/queries/sql/comments.sql:L1-L40"]
""",
        "locate_issue": "为什么用户不能编辑自己写的评论？",
        "locate_matched_modules": [
            "评论互动：是否支持编辑评论，取决于这里有没有路由、schema 和更新 SQL。",
            "文章发布：评论入口挂在文章详情页下面，但真正缺失的是评论子模块本身。",
        ],
        "locate_call_chain": """graph TD
    A["用户点击 Edit Comment"] --> B["评论路由注册\\napp/api/routes/comments.py:L26-L71"]
    B --> C{"是否存在 PUT /{comment_id}?"}
    C -->|否| D["只能新增或删除评论"]
    D --> E["没有更新 schema\\napp/models/schemas/comments.py:L7-L16"]
    D --> F["没有更新 SQL\\napp/db/queries/sql/comments.sql:L1-L40"]
""",
        "locate_exact_locations": [
            {
                "file": "app/api/routes/comments.py",
                "line": 40,
                "why_it_matters": "评论路由只注册了 GET、POST、DELETE，没有任何 PUT/PATCH 编辑入口。",
                "confidence": 0.99,
            },
            {
                "file": "app/models/schemas/comments.py",
                "line": 15,
                "why_it_matters": "schema 里只有 `CommentInCreate`，没有 `CommentInUpdate`。",
                "confidence": 0.98,
            },
            {
                "file": "app/db/queries/sql/comments.sql",
                "line": 20,
                "why_it_matters": "SQL 文件只有新增和删除查询，没有评论更新语句。",
                "confidence": 0.96,
            },
        ],
        "locate_diagnosis": (
            "这不是“某个条件没放开”，而是评论编辑功能压根没有实现。"
            "最值得先看的位置是 `app/api/routes/comments.py:L26-L71`，因为这里已经能确认没有编辑路由。"
        ),
        "codegen_request": "给评论模块补一个编辑接口，让作者本人可以修改自己的评论内容。",
        "codegen_change_summary": [
            {
                "file": "app/models/schemas/comments.py",
                "before": "只有创建评论的请求模型。",
                "after": "新增 `CommentInUpdate`，承接评论编辑表单。",
            },
            {
                "file": "app/db/queries/sql/comments.sql",
                "before": "只有创建与删除评论的 SQL。",
                "after": "新增按评论 id 与作者身份更新正文的 SQL 语句。",
            },
            {
                "file": "app/db/repositories/comments.py",
                "before": "仓库只支持新增、读取、删除。",
                "after": "新增 `update_comment()` 封装，返回更新后的评论对象。",
            },
            {
                "file": "app/api/routes/comments.py",
                "before": "API 没有评论编辑入口。",
                "after": "新增 `PUT /articles/{slug}/comments/{comment_id}`。",
            },
            {
                "file": "tests/test_api/test_routes/test_comments.py",
                "before": "测试不覆盖评论编辑。",
                "after": "补上作者本人成功编辑评论的回归测试。",
            },
        ],
        "codegen_diff": """diff --git a/app/models/schemas/comments.py b/app/models/schemas/comments.py
@@
 class CommentInCreate(RWSchema):
     body: str
+
+class CommentInUpdate(RWSchema):
+    body: str
diff --git a/app/db/queries/sql/comments.sql b/app/db/queries/sql/comments.sql
@@
 -- name: delete-comment-by-id!
 DELETE
 FROM commentaries
 WHERE id = :comment_id
   AND author_id = (SELECT id FROM users WHERE username = :author_username);
+
+-- name: update-comment-by-id<!
+UPDATE commentaries
+SET body = :body
+WHERE id = :comment_id
+  AND author_id = (SELECT id FROM users WHERE username = :author_username)
+RETURNING updated_at;
diff --git a/app/db/repositories/comments.py b/app/db/repositories/comments.py
@@
+    async def update_comment(self, *, comment: Comment, body: str, user: User) -> Comment:
+        updated_at = await queries.update_comment_by_id(
+            self.connection,
+            comment_id=comment.id_,
+            author_username=user.username,
+            body=body,
+        )
+        return comment.copy(update={"body": body, "updated_at": updated_at})
diff --git a/app/api/routes/comments.py b/app/api/routes/comments.py
@@
-from app.models.schemas.comments import (
-    CommentInCreate,
-    CommentInResponse,
-    ListOfCommentsInResponse,
-)
+from app.models.schemas.comments import (
+    CommentInCreate,
+    CommentInResponse,
+    CommentInUpdate,
+    ListOfCommentsInResponse,
+)
@@
+@router.put(
+    "/{comment_id}",
+    response_model=CommentInResponse,
+    name="comments:update-comment-for-article",
+    dependencies=[Depends(check_comment_modification_permissions)],
+)
+async def update_comment_for_article(
+    comment_update: CommentInUpdate = Body(..., embed=True, alias="comment"),
+    comment: Comment = Depends(get_comment_by_id_from_path),
+    user: User = Depends(get_current_user_authorizer()),
+    comments_repo: CommentsRepository = Depends(get_repository(CommentsRepository)),
+) -> CommentInResponse:
+    updated_comment = await comments_repo.update_comment(
+        comment=comment,
+        body=comment_update.body,
+        user=user,
+    )
+    return CommentInResponse(comment=updated_comment)
""",
        "codegen_blast_radius": [
            "文章详情页的评论操作区会多一个编辑入口与保存交互。",
            "评论模型里的 `updated_at` 展示逻辑可能需要同步利用起来。",
        ],
        "codegen_verification_steps": [
            {
                "step": "创建一条评论后，作者本人调用 `PUT /api/articles/{slug}/comments/{comment_id}` 修改正文。",
                "expected_result": "接口返回 200，评论正文更新成功，`updated_at` 发生变化。",
            },
            {
                "step": "换一个非作者账号尝试编辑同一条评论。",
                "expected_result": "接口返回 403，不允许越权修改。",
            },
        ],
    },
    {
        "index": 6,
        "slug": "06_tags",
        "name": "标签分类",
        "paths": [
            "app/api/routes/tags.py",
            "app/db/repositories/tags.py",
            "app/db/queries/sql/tags.sql",
            "app/models/schemas/tags.py",
        ],
        "responsibility": "负责返回全站标签列表，供发文时选择标签、浏览时按标签筛选内容。",
        "entry_points": ["GET /api/tags"],
        "depends_on": ["数据库连接与仓库层", "文章发布"],
        "used_by": ["文章发布", "文章列表筛选"],
        "pm_note": "当前只返回字符串数组，没有热度信息，也没有默认排序策略。",
        "card_path": "app/api/routes/tags.py",
        "what": "系统把所有已存在的标签收集起来，供用户发文时复用，或供首页做标签发现。",
        "inputs": [
            "无请求体；只依赖数据库中的标签表。",
        ],
        "outputs": [
            "标签字符串数组 `tags`",
            "没有标签时返回空列表",
        ],
        "branches": [
            {
                "condition": "库里还没有任何标签",
                "result": "返回空数组。",
                "code_ref": "tests/test_api/test_routes/test_tags.py:L11-L13",
            },
            {
                "condition": "文章创建时带入了新标签",
                "result": "不存在的标签会被自动插入 `tags` 表，重复值依赖 SQL 去重。",
                "code_ref": "app/db/repositories/tags.py:L12-L13",
            },
            {
                "condition": "请求获取标签列表",
                "result": "直接 `SELECT tag FROM tags`，不附带热度或排序信息。",
                "code_ref": "app/db/queries/sql/tags.sql:L1-L3",
            },
        ],
        "side_effects": [
            "标签接口本身只读，但文章发布会调用标签仓库补建缺失标签。证据：`app/db/repositories/tags.py:L12-L13`。",
        ],
        "blast_radius": [
            "标签返回结构变化会影响发文页标签选择器与首页标签推荐区。",
            "标签排序策略会影响用户首先看到哪些话题。",
        ],
        "key_code_refs": [
            "app/api/routes/tags.py:L10-L15",
            "app/db/repositories/tags.py:L7-L13",
            "app/db/queries/sql/tags.sql:L1-L8",
            "app/models/schemas/tags.py:L1-L7",
        ],
        "understand_pm_note": "这个模块更像“标签字典服务”，不是“热门话题引擎”，所以天然缺少热度感知。",
        "understand_graph": """graph TD
    A["标签页或发文页"] --> B["GET /api/tags\\napp/api/routes/tags.py:L10-L15"]
    B --> C["TagsRepository\\napp/db/repositories/tags.py:L7-L13"]
    C --> D["标签 SQL\\napp/db/queries/sql/tags.sql:L1-L8"]
""",
        "locate_issue": "为什么标签接口只返回平铺列表，看不到热门程度？",
        "locate_matched_modules": [
            "标签分类：返回结构与 SQL 都在这里定义。",
            "文章发布：标签会被写入，但并没有维护任何单独的热度字段。",
        ],
        "locate_call_chain": """graph TD
    A["前端请求 /api/tags"] --> B["get_all_tags()\\napp/api/routes/tags.py:L10-L15"]
    B --> C["TagsRepository.get_all_tags()\\napp/db/repositories/tags.py:L8-L10"]
    C --> D["SELECT tag FROM tags\\napp/db/queries/sql/tags.sql:L1-L3"]
    D --> E["返回纯字符串数组"]
""",
        "locate_exact_locations": [
            {
                "file": "app/db/queries/sql/tags.sql",
                "line": 1,
                "why_it_matters": "SQL 只选了 `tag` 字段，没有统计文章数，也没有排序逻辑。",
                "confidence": 0.99,
            },
            {
                "file": "app/models/schemas/tags.py",
                "line": 6,
                "why_it_matters": "响应模型把 `tags` 固定成了 `List[str]`，天然放不下热度字段。",
                "confidence": 0.98,
            },
        ],
        "locate_diagnosis": (
            "相关模块是标签分类。当前接口只能回答“有哪些标签”，不能回答“哪些标签更热”，"
            "因为 SQL 和响应模型都只支持字符串数组。"
        ),
        "codegen_request": "把标签接口升级为“标签名 + 被多少篇文章使用”，并按热度倒序返回。",
        "codegen_change_summary": [
            {
                "file": "app/models/schemas/tags.py",
                "before": "标签响应模型只有字符串数组。",
                "after": "新增标签对象结构，包含 `name` 和 `articles_count`。",
            },
            {
                "file": "app/db/queries/sql/tags.sql",
                "before": "只查标签名，不做聚合。",
                "after": "按标签聚合文章数，并按热度倒序返回。",
            },
            {
                "file": "app/db/repositories/tags.py",
                "before": "仓库返回 `List[str]`。",
                "after": "仓库返回结构化标签对象列表。",
            },
            {
                "file": "tests/test_api/test_routes/test_tags.py",
                "before": "测试只关心标签是否去重。",
                "after": "增加对 `articles_count` 和排序的断言。",
            },
        ],
        "codegen_diff": """diff --git a/app/models/schemas/tags.py b/app/models/schemas/tags.py
@@
-from typing import List
+from typing import List
@@
-class TagsInList(BaseModel):
-    tags: List[str]
+class TagItem(BaseModel):
+    name: str
+    articles_count: int
+
+class TagsInList(BaseModel):
+    tags: List[TagItem]
diff --git a/app/db/queries/sql/tags.sql b/app/db/queries/sql/tags.sql
@@
-SELECT tag
-FROM tags;
+SELECT
+    t.tag AS name,
+    count(att.article_id) AS articles_count
+FROM tags t
+LEFT JOIN articles_to_tags att ON att.tag = t.tag
+GROUP BY t.tag
+ORDER BY articles_count DESC, name ASC;
diff --git a/app/db/repositories/tags.py b/app/db/repositories/tags.py
@@
-    async def get_all_tags(self) -> List[str]:
+    async def get_all_tags(self) -> List[dict]:
         tags_row = await queries.get_all_tags(self.connection)
-        return [tag[0] for tag in tags_row]
+        return [
+            {"name": row["name"], "articles_count": row["articles_count"]}
+            for row in tags_row
+        ]
""",
        "codegen_blast_radius": [
            "前端消费 `/api/tags` 的地方需要适配从字符串数组变成对象数组。",
            "如果产品只展示标签名，需要明确取 `tag.name` 字段。",
        ],
        "codegen_verification_steps": [
            {
                "step": "创建多篇带重复标签的文章后请求 `GET /api/tags`。",
                "expected_result": "返回数组项含 `name` 与 `articles_count`，且按使用次数从高到低排序。",
            },
            {
                "step": "发文页重新加载标签选择器。",
                "expected_result": "标签仍能正常显示，只是多了热度可用信息。",
            },
        ],
    },
    {
        "index": 7,
        "slug": "07_favorites",
        "name": "收藏系统",
        "paths": [
            "app/api/routes/articles/articles_common.py",
            "app/api/dependencies/articles.py",
            "app/db/repositories/articles.py",
            "app/db/queries/sql/articles.sql",
        ],
        "responsibility": "负责收藏/取消收藏文章，以及基于收藏关系筛选文章列表。",
        "entry_points": [
            "POST /api/articles/{slug}/favorite",
            "DELETE /api/articles/{slug}/favorite",
            "GET /api/articles?favorited={username}",
        ],
        "depends_on": ["用户认证", "文章发布", "数据库连接与仓库层"],
        "used_by": ["文章详情页", "用户个人收藏页（如前端自行组装）"],
        "pm_note": "后端其实已经支持按收藏用户筛文章，但没有给当前登录用户一个显式入口，能力偏隐藏。",
        "card_path": "app/api/routes/articles/articles_common.py",
        "what": "用户在文章详情页点击心形按钮后，系统会写入收藏关系，并在文章列表中反映收藏状态与收藏数。",
        "inputs": [
            "路径参数 `slug`（来自文章详情）",
            "可选查询参数 `favorited=username`（来自文章列表筛选）",
            "Authorization 请求头（来自已登录用户）",
        ],
        "outputs": [
            "更新后的文章收藏状态与收藏数",
            "按收藏关系筛出的文章列表",
            "重复收藏或重复取消收藏时的 400 错误",
        ],
        "branches": [
            {
                "condition": "文章尚未被当前用户收藏",
                "result": "写入 `favorites` 表并把 `favorited` 改成 `true`。",
                "code_ref": "app/api/routes/articles/articles_common.py:L52-L69",
            },
            {
                "condition": "文章已被当前用户收藏后再次收藏",
                "result": "直接返回 400 和 `ARTICLE_IS_ALREADY_FAVORITED`。",
                "code_ref": "app/api/routes/articles/articles_common.py:L71-L74",
            },
            {
                "condition": "文章已被收藏后取消收藏",
                "result": "删除 `favorites` 关系并把计数减一。",
                "code_ref": "app/api/routes/articles/articles_common.py:L82-L99",
            },
            {
                "condition": "列表请求带 `favorited` 参数",
                "result": "仓库层通过 `favorites` 表关联筛出对应用户收藏过的文章。",
                "code_ref": "app/db/repositories/articles.py:L177-L212",
            },
        ],
        "side_effects": [
            "收藏和取消收藏都会改写 `favorites` 关系表。证据：`app/db/queries/sql/articles.sql:L1-L19`。",
            "读取文章详情或列表时，系统会额外查一次当前用户是否已收藏。证据：`app/db/repositories/articles.py:L266-L323`。",
        ],
        "blast_radius": [
            "收藏关系变化会影响文章详情页的心形按钮与收藏数。",
            "列表筛选规则变化会影响用户个人页、文章流与潜在的“我的收藏”页面。",
        ],
        "key_code_refs": [
            "app/api/routes/articles/articles_common.py:L47-L104",
            "app/db/repositories/articles.py:L101-L323",
            "app/db/queries/sql/articles.sql:L1-L25",
        ],
        "understand_pm_note": "收藏并不是“没有入口”，而是“入口不够产品化”：当前只有底层 query 参数，没有面向当前用户的直接 API。",
        "understand_graph": """graph TD
    A["用户点击 Favorite"] --> B["收藏路由\\napp/api/routes/articles/articles_common.py:L47-L104"]
    B --> C["文章依赖\\napp/api/dependencies/articles.py:L37-L59"]
    B --> D["ArticlesRepository\\napp/db/repositories/articles.py:L275-L292"]
    D --> E["favorites SQL\\napp/db/queries/sql/articles.sql:L1-L19"]
    F["文章列表 ?favorited=username"] --> G["filter_articles()\\napp/db/repositories/articles.py:L101-L212"]
    G --> E
""",
        "locate_issue": "想查当前用户收藏的文章，应该看哪里？",
        "locate_matched_modules": [
            "收藏系统：真正的能力入口藏在文章列表筛选参数里。",
            "文章发布：收藏结果最终仍通过文章列表接口返回文章对象。",
        ],
        "locate_call_chain": """graph TD
    A["前端想要“我的收藏”"] --> B["list_articles()\\napp/api/routes/articles/articles_resource.py:L30-L50"]
    B --> C["get_articles_filters()\\napp/api/dependencies/articles.py:L21-L34"]
    C --> D["favorited=username"]
    D --> E["filter_articles()\\napp/db/repositories/articles.py:L177-L212"]
    E --> F["favorites 表关联筛选"]
""",
        "locate_exact_locations": [
            {
                "file": "app/api/dependencies/articles.py",
                "line": 24,
                "why_it_matters": "文章列表过滤器已经定义了 `favorited` 参数，说明收藏列表能力底层存在。",
                "confidence": 0.97,
            },
            {
                "file": "app/db/repositories/articles.py",
                "line": 177,
                "why_it_matters": "仓库层在这里通过 `favorites` 表把收藏筛选真正落实成 SQL 条件。",
                "confidence": 0.99,
            },
        ],
        "locate_diagnosis": (
            "相关模块是收藏系统，但它并没有一个对当前用户友好的显式接口。"
            "现成能力藏在 `GET /api/articles?favorited={username}` 这条列表链路里。"
        ),
        "codegen_request": "新增 `GET /api/articles/favorites/me`，让前端不用自己拼用户名也能直接拿当前用户收藏列表。",
        "codegen_change_summary": [
            {
                "file": "app/api/routes/articles/articles_common.py",
                "before": "只有按用户名的底层筛选，没有面向当前用户的显式收藏接口。",
                "after": "新增一个复用现有仓库逻辑的 `favorites/me` 路由。",
            },
            {
                "file": "tests/test_api/test_routes/test_articles.py",
                "before": "测试只覆盖收藏状态切换，不覆盖“我的收藏列表”。",
                "after": "补上当前用户获取自己收藏文章列表的回归测试。",
            },
        ],
        "codegen_diff": """diff --git a/app/api/routes/articles/articles_common.py b/app/api/routes/articles/articles_common.py
@@
 @router.get(
+    "/favorites/me",
+    response_model=ListOfArticlesInResponse,
+    name="articles:get-current-user-favorites",
+)
+async def get_current_user_favorites(
+    limit: int = Query(DEFAULT_ARTICLES_LIMIT, ge=1),
+    offset: int = Query(DEFAULT_ARTICLES_OFFSET, ge=0),
+    user: User = Depends(get_current_user_authorizer()),
+    articles_repo: ArticlesRepository = Depends(get_repository(ArticlesRepository)),
+) -> ListOfArticlesInResponse:
+    articles = await articles_repo.filter_articles(
+        favorited=user.username,
+        limit=limit,
+        offset=offset,
+        requested_user=user,
+    )
+    return ListOfArticlesInResponse(
+        articles=[ArticleForResponse.from_orm(article) for article in articles],
+        articles_count=len(articles),
+    )
""",
        "codegen_blast_radius": [
            "前端会多一个更稳定的收藏入口，不再依赖把用户名塞进 query 参数。",
            "如果未来有“我的收藏”页面，这条接口可以直接复用。",
        ],
        "codegen_verification_steps": [
            {
                "step": "先收藏两篇文章，再请求 `GET /api/articles/favorites/me`。",
                "expected_result": "返回当前用户收藏的文章列表，数量与收藏数一致。",
            },
            {
                "step": "取消其中一篇收藏后再次请求该接口。",
                "expected_result": "返回列表即时减少一篇，被取消的文章不再出现。",
            },
        ],
    },
    {
        "index": 8,
        "slug": "08_feed",
        "name": "信息流",
        "paths": [
            "app/api/routes/articles/articles_common.py",
            "app/db/repositories/articles.py",
            "app/db/queries/sql/articles.sql",
            "app/db/queries/sql/profiles.sql",
        ],
        "responsibility": "负责给已登录用户返回“我关注的人最近发了什么”的专属内容流。",
        "entry_points": ["GET /api/articles/feed"],
        "depends_on": ["用户认证", "社交关系", "文章发布", "数据库连接与仓库层"],
        "used_by": ["登录后首页"],
        "pm_note": "当前 feed 只认关注关系；如果用户还没关注任何作者，就会直接得到空列表，冷启动体验很差。",
        "card_path": "app/api/routes/articles/articles_common.py",
        "what": "已登录用户打开首页时，系统根据他的关注关系，筛出被关注作者发布的文章并返回分页结果。",
        "inputs": [
            "Authorization 请求头（来自已登录用户）",
            "分页参数 `limit / offset`（来自首页滚动加载）",
        ],
        "outputs": [
            "只包含被关注作者文章的 feed 列表",
            "关注为空时的空列表",
        ],
        "branches": [
            {
                "condition": "请求没有合法 token",
                "result": "鉴权依赖直接返回 403。",
                "code_ref": "app/api/dependencies/authentication.py:L46-L109",
            },
            {
                "condition": "用户没有关注任何作者",
                "result": "feed SQL 关联不到任何记录，返回空数组。",
                "code_ref": "app/db/queries/sql/articles.sql:L96-L116",
            },
            {
                "condition": "用户已关注部分作者",
                "result": "只返回这些作者的文章，不包含其他人的内容。",
                "code_ref": "app/db/repositories/articles.py:L214-L235",
            },
        ],
        "side_effects": [
            "feed 自身不写库，但它强依赖关注关系表和文章表的一致性。",
        ],
        "blast_radius": [
            "关注规则、文章发布时间排序或分页策略变化都会直接影响登录后首页。",
            "feed 冷启动策略会直接影响新用户首次留存。",
        ],
        "key_code_refs": [
            "app/api/routes/articles/articles_common.py:L22-L44",
            "app/db/repositories/articles.py:L214-L235",
            "app/db/queries/sql/articles.sql:L96-L116",
            "tests/test_api/test_routes/test_articles.py:L246-L322",
        ],
        "understand_pm_note": "这是一个非常“纯关注驱动”的 feed，没有推荐兜底，所以越早关注作者，体验越好；反之就是冷启动空白。",
        "understand_graph": """graph TD
    A["登录用户打开首页"] --> B["GET /api/articles/feed\\napp/api/routes/articles/articles_common.py:L22-L44"]
    B --> C["鉴权依赖\\napp/api/dependencies/authentication.py:L78-L109"]
    B --> D["ArticlesRepository.get_articles_for_user_feed\\napp/db/repositories/articles.py:L214-L235"]
    D --> E["feed SQL\\napp/db/queries/sql/articles.sql:L96-L116"]
    E --> F["followers_to_followings 关系表"]
""",
        "locate_issue": "新用户关注页为什么一直是空白？",
        "locate_matched_modules": [
            "信息流：空白结果就发生在 feed 专用查询里。",
            "社交关系：feed 是否有内容，完全取决于用户是否已经建立关注关系。",
        ],
        "locate_call_chain": """graph TD
    A["用户请求 /api/articles/feed"] --> B["get_articles_for_user_feed()\\napp/api/routes/articles/articles_common.py:L27-L44"]
    B --> C["ArticlesRepository.get_articles_for_user_feed()\\napp/db/repositories/articles.py:L214-L235"]
    C --> D["feed SQL 内连接 followers_to_followings\\napp/db/queries/sql/articles.sql:L96-L116"]
    D --> E["没有 follow 记录 => 返回 []"]
""",
        "locate_exact_locations": [
            {
                "file": "app/db/queries/sql/articles.sql",
                "line": 110,
                "why_it_matters": "feed 查询使用 `INNER JOIN followers_to_followings`，没有关注关系就不会返回任何文章。",
                "confidence": 0.99,
            },
            {
                "file": "tests/test_api/test_routes/test_articles.py",
                "line": 246,
                "why_it_matters": "测试已经明确把“无关注返回空列表”定义成当前行为。",
                "confidence": 0.95,
            },
        ],
        "locate_diagnosis": (
            "相关模块是信息流。当前实现不是“查不到推荐”，而是产品规则明确写成了“只看关注的人”。"
            "如果用户还没关注任何作者，feed SQL 就会自然返回空数组。"
        ),
        "codegen_request": "给 feed 增加冷启动兜底：当用户还没关注任何作者时，回退到全站最新文章。",
        "codegen_change_summary": [
            {
                "file": "app/api/routes/articles/articles_common.py",
                "before": "feed 查询结果为空时，接口直接把空列表返回给前端。",
                "after": "如果关注流为空，就回退到全站文章列表作为冷启动兜底。",
            },
            {
                "file": "tests/test_api/test_routes/test_articles.py",
                "before": "测试把无关注用户收到空列表当成预期。",
                "after": "改成验证接口会返回可浏览的兜底内容。",
            },
        ],
        "codegen_diff": """diff --git a/app/api/routes/articles/articles_common.py b/app/api/routes/articles/articles_common.py
@@
 async def get_articles_for_user_feed(
@@
     articles = await articles_repo.get_articles_for_user_feed(
         user=user,
         limit=limit,
         offset=offset,
     )
+    if not articles:
+        articles = await articles_repo.filter_articles(
+            limit=limit,
+            offset=offset,
+            requested_user=user,
+        )
diff --git a/tests/test_api/test_routes/test_articles.py b/tests/test_api/test_routes/test_articles.py
@@
-async def test_empty_feed_if_user_has_not_followings(
+async def test_feed_falls_back_to_global_articles_if_user_has_not_followings(
@@
-    assert articles.articles == []
+    assert len(articles.articles) == 5
""",
        "codegen_blast_radius": [
            "登录首页会从“空白”变成“兜底推荐”，需要确认产品是否接受这种心智变化。",
            "feed 指标与推荐策略会被冷启动兜底影响，需要单独埋点区分。",
        ],
        "codegen_verification_steps": [
            {
                "step": "准备一个没有关注任何作者的新用户，并确保全站已有文章。",
                "expected_result": "请求 `GET /api/articles/feed` 时不再返回空列表，而是返回全站文章。",
            },
            {
                "step": "给同一个用户新增一条关注关系后再次请求 feed。",
                "expected_result": "接口重新回到只返回被关注作者文章的专属流。",
            },
        ],
    },
    {
        "index": 9,
        "slug": "09_storage",
        "name": "数据库连接与仓库层",
        "paths": [
            "app/api/dependencies/database.py",
            "app/db/events.py",
            "app/db/repositories/base.py",
            "app/db/queries/queries.py",
            "app/db/queries/tables.py",
            "app/db/queries/sql/*.sql",
            "tests/conftest.py",
        ],
        "responsibility": "负责创建全局 asyncpg 连接池、为每个请求注入数据库连接，并承接各仓库层的 SQL 执行。",
        "entry_points": [
            "应用启动时创建连接池",
            "所有 `Depends(get_repository(...))` 的业务路由",
        ],
        "depends_on": ["系统启动与配置"],
        "used_by": ["用户认证", "用户管理", "社交关系", "文章发布", "评论互动", "标签分类", "收藏系统", "信息流"],
        "pm_note": "这里是全站共用的单点基础设施。默认最大连接数只有 10，一旦池满，所有业务接口都会一起排队。",
        "card_path": "app/api/dependencies/database.py",
        "what": "应用启动时系统先建立一个共享连接池；后续每个请求通过依赖注入从池里借一条连接，仓库层再用这条连接执行 SQL。",
        "inputs": [
            "数据库连接串与连接池大小（来自配置）",
            "每个请求注入的 `Request` 对象与连接池状态",
        ],
        "outputs": [
            "可供仓库层复用的数据库连接",
            "启动时挂在 `app.state.pool` 上的全局连接池",
        ],
        "branches": [
            {
                "condition": "应用启动",
                "result": "创建 asyncpg 连接池并挂到 `app.state.pool`。",
                "code_ref": "app/db/events.py:L8-L17",
            },
            {
                "condition": "业务请求进入仓库依赖",
                "result": "从共享池里 `acquire()` 一条连接并在请求结束后归还。",
                "code_ref": "app/api/dependencies/database.py:L15-L29",
            },
            {
                "condition": "应用关闭",
                "result": "统一关闭连接池，释放数据库资源。",
                "code_ref": "app/db/events.py:L20-L25",
            },
        ],
        "side_effects": [
            "连接池大小会直接限制全站并发请求可同时访问数据库的数量。",
            "测试环境会在生命周期里把真实池替换成 `FakeAsyncPGPool`，以便集成测试。证据：`tests/conftest.py:L27-L35`。",
        ],
        "blast_radius": [
            "任何连接池配置调整都会影响所有模块，而不是单个接口。",
            "仓库注入方式变化会影响全站依赖写法与测试夹具。",
        ],
        "key_code_refs": [
            "app/api/dependencies/database.py:L11-L29",
            "app/db/events.py:L8-L25",
            "app/db/repositories/base.py:L4-L10",
            "app/db/queries/queries.py:L1-L5",
            "app/db/queries/tables.py:L7-L75",
            "tests/conftest.py:L19-L35",
        ],
        "understand_pm_note": "这层不是一个“功能页”，而是所有功能页共享的高速公路收费站；收费站堵了，整站都会慢。",
        "understand_graph": """graph TD
    A["应用启动"] --> B["connect_to_db()\\napp/db/events.py:L8-L17"]
    B --> C["app.state.pool"]
    D["业务路由"] --> E["get_repository()\\napp/api/dependencies/database.py:L22-L29"]
    E --> F["_get_connection_from_pool()\\napp/api/dependencies/database.py:L15-L19"]
    F --> C
    F --> G["各类 Repository\\napp/db/repositories/*.py"]
    G --> H["SQL 装载器\\napp/db/queries/queries.py:L1-L5"]
""",
        "locate_issue": "为什么并发一上来，全站接口都会一起变慢？",
        "locate_matched_modules": [
            "数据库连接与仓库层：所有业务请求都必须先从同一个连接池借连接。",
            "系统启动与配置：连接池上限由配置层决定。",
        ],
        "locate_call_chain": """graph TD
    A["任意业务请求"] --> B["get_repository()\\napp/api/dependencies/database.py:L22-L29"]
    B --> C["_get_connection_from_pool()\\napp/api/dependencies/database.py:L15-L19"]
    C --> D["共享连接池 app.state.pool"]
    D --> E["create_pool(max_size=...)\\napp/db/events.py:L11-L15"]
    E --> F["max_connection_count 默认 10\\napp/core/settings/app.py:L21-L23"]
""",
        "locate_exact_locations": [
            {
                "file": "app/api/dependencies/database.py",
                "line": 18,
                "why_it_matters": "所有请求都会在这里统一从连接池 `acquire()` 数据库连接。",
                "confidence": 0.97,
            },
            {
                "file": "app/db/events.py",
                "line": 11,
                "why_it_matters": "共享池是在这里创建的，说明全站共用一个池。",
                "confidence": 0.96,
            },
            {
                "file": "app/core/settings/app.py",
                "line": 22,
                "why_it_matters": "默认最大连接数只有 10，并发量一高就可能进入排队。",
                "confidence": 0.88,
            },
        ],
        "locate_diagnosis": (
            "相关模块是数据库连接与仓库层。当前实现采用单个共享连接池承接全站请求，"
            "默认 `max_connection_count=10`。当并发请求都要访问数据库时，额外请求只能等待空闲连接归还，"
            "于是全站一起变慢。这里包含性能层面的推断，但证据链是充分的。"
        ),
        "codegen_request": "启动时把连接池 min/max 打进日志，并把开发环境默认池大小调成 1-5，避免本地误占满数据库。",
        "codegen_change_summary": [
            {
                "file": "app/db/events.py",
                "before": "启动日志只写“Connecting to PostgreSQL”，看不到连接池范围。",
                "after": "补充 min/max，排查环境配置时一眼可见。",
            },
            {
                "file": "app/core/settings/development.py",
                "before": "开发环境沿用 10/10 的默认池大小。",
                "after": "显式调成 `min=1, max=5`，更适合本地调试。",
            },
        ],
        "codegen_diff": """diff --git a/app/db/events.py b/app/db/events.py
@@
-    logger.info("Connecting to PostgreSQL")
+    logger.info(
+        "Connecting to PostgreSQL (pool min={}, max={})",
+        settings.min_connection_count,
+        settings.max_connection_count,
+    )
diff --git a/app/core/settings/development.py b/app/core/settings/development.py
@@
 class DevAppSettings(AppSettings):
     debug: bool = True
     title: str = "Dev FastAPI example application"
+    min_connection_count: int = 1
+    max_connection_count: int = 5
""",
        "codegen_blast_radius": [
            "只影响开发环境默认配置与启动日志，不改变生产逻辑。",
            "运维或本地开发排障时会更容易判断是否因为连接池配置导致问题。",
        ],
        "codegen_verification_steps": [
            {
                "step": "以开发环境启动应用并观察控制台日志。",
                "expected_result": "日志中能看到连接池的 min/max 配置值。",
            },
            {
                "step": "在本地数据库资源有限的环境下重复启动多个服务实例。",
                "expected_result": "相比原来更不容易因为默认连接数过大而占满本地数据库连接。",
            },
        ],
    },
    {
        "index": 10,
        "slug": "10_startup-config",
        "name": "系统启动与配置",
        "paths": [
            "app/main.py",
            "app/core/config.py",
            "app/core/events.py",
            "app/core/settings/app.py",
            "app/core/settings/base.py",
            "app/core/settings/development.py",
            "app/core/settings/production.py",
            "app/core/settings/test.py",
            "app/api/routes/api.py",
        ],
        "responsibility": "负责按环境装配 FastAPI 应用、挂载中间件与路由，并把数据库生命周期钩子接进启动关闭流程。",
        "entry_points": [
            "`app = get_application()`",
            "`APP_ENV` 环境变量",
        ],
        "depends_on": [],
        "used_by": ["用户认证", "用户管理", "社交关系", "文章发布", "评论互动", "标签分类", "收藏系统", "信息流", "数据库连接与仓库层"],
        "pm_note": "生产环境配置目前只改了 `env_file`，意味着 `/docs`、`/redoc`、`/openapi.json` 仍默认暴露。",
        "card_path": "app/main.py",
        "what": "应用进程启动后，系统先读环境配置，再创建 FastAPI 实例、挂载中间件、注册路由，并串起数据库启动/关闭钩子。",
        "inputs": [
            "`APP_ENV` 环境变量",
            "各环境 settings 类上的字段值",
        ],
        "outputs": [
            "已经装配完毕的 FastAPI 应用对象",
            "按环境定制的 docs / openapi / 数据库连接池配置",
        ],
        "branches": [
            {
                "condition": "APP_ENV=dev / prod / test",
                "result": "通过 `get_app_settings()` 选择对应的 settings 类。",
                "code_ref": "app/core/config.py:L10-L21",
            },
            {
                "condition": "应用启动",
                "result": "挂上 startup/shutdown 事件处理器，并注册 API 路由。",
                "code_ref": "app/main.py:L13-L42",
            },
            {
                "condition": "生产环境没有显式覆盖 docs 配置",
                "result": "FastAPI 会继续沿用 `AppSettings` 中默认开放的 docs/redoc/openapi。",
                "code_ref": "app/core/settings/app.py:L13-L18",
            },
        ],
        "side_effects": [
            "启动时会配置 logging、中间件、异常处理器和 API 路由前缀。",
            "生命周期钩子会进一步触发数据库连接池的建立与关闭。",
        ],
        "blast_radius": [
            "任何 settings 变更都会影响全站行为，而不是单一业务模块。",
            "docs/openapi 的暴露策略会直接影响对外可见面和安全基线。",
        ],
        "key_code_refs": [
            "app/main.py:L13-L45",
            "app/core/config.py:L10-L21",
            "app/core/events.py:L10-L25",
            "app/core/settings/app.py:L12-L57",
            "app/core/settings/production.py:L1-L6",
            "app/api/routes/api.py:L6-L16",
        ],
        "understand_pm_note": "这是全站装配层，最容易被忽略的问题不是“功能坏了”，而是“生产环境默认值没有被收紧”。",
        "understand_graph": """graph TD
    A["进程导入 app.main"] --> B["get_application()\\napp/main.py:L13-L42"]
    B --> C["get_app_settings()\\napp/core/config.py:L17-L21"]
    C --> D["环境 settings\\napp/core/settings/*.py"]
    B --> E["FastAPI(**settings.fastapi_kwargs)\\napp/core/settings/app.py:L39-L49"]
    B --> F["startup/shutdown hooks\\napp/core/events.py:L10-L25"]
    B --> G["API 路由总线\\napp/api/routes/api.py:L6-L16"]
""",
        "locate_issue": "为什么生产环境默认还暴露 /docs 和 /redoc？",
        "locate_matched_modules": [
            "系统启动与配置：是否暴露 docs 由 settings 和 FastAPI 初始化参数决定。",
            "数据库连接与仓库层：不是这次问题源头，但同样受启动装配层统一控制。",
        ],
        "locate_call_chain": """graph TD
    A["应用启动"] --> B["get_application()\\napp/main.py:L13-L18"]
    B --> C["get_app_settings()\\napp/core/config.py:L17-L21"]
    C --> D["ProdAppSettings\\napp/core/settings/production.py:L4-L6"]
    D --> E["继承 AppSettings 默认 docs 配置\\napp/core/settings/app.py:L13-L18"]
    E --> F["FastAPI(**settings.fastapi_kwargs)\\napp/core/settings/app.py:L39-L49"]
""",
        "locate_exact_locations": [
            {
                "file": "app/core/settings/app.py",
                "line": 14,
                "why_it_matters": "这里定义了 docs/openapi/redoc 的默认暴露路径。",
                "confidence": 0.99,
            },
            {
                "file": "app/core/settings/production.py",
                "line": 4,
                "why_it_matters": "生产配置没有覆盖 docs 相关字段，所以会继承默认值。",
                "confidence": 0.98,
            },
            {
                "file": "app/main.py",
                "line": 18,
                "why_it_matters": "FastAPI 实例就是用 `settings.fastapi_kwargs` 创建的，因此默认值会真正生效。",
                "confidence": 0.96,
            },
        ],
        "locate_diagnosis": (
            "相关模块是系统启动与配置。问题不在路由总线，而在生产环境 settings 继承了应用默认值。"
            "只要 `ProdAppSettings` 不覆写 docs 相关字段，线上 `/docs`、`/redoc` 和 `/openapi.json` 就会继续开放。"
        ),
        "codegen_request": "在生产环境关闭 Swagger / ReDoc / OpenAPI 暴露，减少公开 API 面。",
        "codegen_change_summary": [
            {
                "file": "app/core/settings/production.py",
                "before": "生产环境仅指定 `env_file`，其他配置沿用默认值。",
                "after": "显式关闭 `docs_url`、`redoc_url` 与 `openapi_url`。",
            },
        ],
        "codegen_diff": """diff --git a/app/core/settings/production.py b/app/core/settings/production.py
@@
 class ProdAppSettings(AppSettings):
+    docs_url: str = ""
+    redoc_url: str = ""
+    openapi_url: str = ""
+
     class Config(AppSettings.Config):
         env_file = "prod.env"
""",
        "codegen_blast_radius": [
            "线上运维与开发如果依赖 `/docs` 调试，需要改用本地或非生产环境。",
            "任何自动拉取线上 OpenAPI 的脚本都要改成从构建产物或非生产环境获取。",
        ],
        "codegen_verification_steps": [
            {
                "step": "用 `APP_ENV=prod` 启动应用后访问 `/docs`、`/redoc`、`/openapi.json`。",
                "expected_result": "这三个地址都不再公开可访问。",
            },
            {
                "step": "切回 `APP_ENV=dev` 再访问相同地址。",
                "expected_result": "开发环境仍保留文档入口，方便联调与调试。",
            },
        ],
    },
]


def resolve_gitingest() -> str:
    candidates = [
        shutil.which("gitingest"),
        str(Path.home() / ".local/bin/gitingest"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise FileNotFoundError("gitingest is not installed. Run `uv tool install gitingest` first.")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def to_json_block(data: Any) -> str:
    return "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```"


def to_mermaid_block(graph: str) -> str:
    return "```mermaid\n" + graph.strip() + "\n```"


def render_readme() -> str:
    module_lines = "\n".join(
        f"- `{module['slug']}`: {module['name']}" for module in MODULES
    )
    return f"""
# {PROJECT_NAME} 模块化代码书

这套产物把测试项目拆成了「先蓝图，再看懂，再定位，再编写」四层能力，并且按模块分别落盘，避免一次读整仓库造成长上下文质量衰减。

## 目录结构

- `00_source/gitingest.txt`：用 gitingest 导出的仓库全文本。
- `01_blueprint/blueprint.md`：系统级蓝图与模块总览。
- `02_understand/*.md`：逐模块的理解卡片。
- `03_locate/*.md`：逐模块的模拟问题定位。
- `04_codegen/*.md`：逐模块的模拟修改方案。

## 当前模块

{module_lines}

## 复跑方式

```bash
python3 scripts/generate_conduit_module_books.py
python3 scripts/generate_conduit_module_books.py --stage understand --module 04_article-authoring
python3 scripts/generate_conduit_module_books.py --stage locate --module 08_feed --skip-ingest
```
"""


def render_blueprint() -> str:
    module_overview = [
        {
            "name": module["name"],
            "paths": module["paths"],
            "responsibility": module["responsibility"],
            "entry_points": module["entry_points"],
            "depends_on": module["depends_on"],
            "used_by": module["used_by"],
            "pm_note": module["pm_note"],
        }
        for module in MODULES
    ]
    return f"""
# {PROJECT_NAME} 蓝图

## project_summary

{PROJECT_CONTEXT}

它的主链路很清晰：用户注册登录后发布文章，读者围绕文章做关注、收藏、评论，再由标签与关注关系驱动内容发现和信息流。

## module_overview

{to_json_block(module_overview)}

## global_dependency_graph

{to_mermaid_block(GLOBAL_DEPENDENCY_GRAPH)}
"""


def render_understand(module: dict[str, Any]) -> str:
    module_card = {
        "name": module["name"],
        "path": module["card_path"],
        "what": module["what"],
        "inputs": module["inputs"],
        "outputs": module["outputs"],
        "branches": module["branches"],
        "side_effects": module["side_effects"],
        "blast_radius": module["blast_radius"],
        "key_code_refs": module["key_code_refs"],
        "pm_note": module["understand_pm_note"],
    }
    scope = "\n".join(f"- {path}" for path in module["paths"])
    return f"""
# {module["name"]} · 看懂

> 分析范围
{scope}

## module_cards

{to_json_block([module_card])}

## dependency_graph

{to_mermaid_block(module["understand_graph"])}
"""


def render_locate(module: dict[str, Any]) -> str:
    matched_modules = "\n".join(f"- {line}" for line in module["locate_matched_modules"])
    return f"""
# {module["name"]} · 定位

> 模拟问题：{module["locate_issue"]}

## matched_modules

{matched_modules}

## call_chain

{to_mermaid_block(module["locate_call_chain"])}

## exact_locations

{to_json_block(module["locate_exact_locations"])}

## diagnosis

{module["locate_diagnosis"]}
"""


def render_codegen(module: dict[str, Any]) -> str:
    change_summary = "\n".join(
        f"- `{item['file']}`：{item['before']} -> {item['after']}"
        for item in module["codegen_change_summary"]
    )
    blast_radius = "\n".join(f"- {item}" for item in module["codegen_blast_radius"])
    return f"""
# {module["name"]} · 编写

> 模拟修改：{module["codegen_request"]}

## change_summary

{change_summary}

## unified_diff

```diff
{module["codegen_diff"].strip()}
```

## blast_radius

{blast_radius}

## verification_steps

{to_json_block(module["codegen_verification_steps"])}
"""


def generate_sources(skip_ingest: bool) -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    if not skip_ingest:
        gitingest_bin = resolve_gitingest()
        subprocess.run(
            [gitingest_bin, str(REPO_ROOT), "-o", str(SOURCE_DIR / "gitingest.txt")],
            check=True,
        )
    write_text(
        SOURCE_DIR / "README.md",
        f"""
# {PROJECT_NAME} 源材料

- 仓库路径：`{REPO_ROOT}`
- 导出方式：`gitingest`
- 导出文件：`gitingest.txt`

这份全文本不会直接作为最终能力输出，而是作为逐模块拆分时的底层证据材料。
""",
    )


def generate_blueprint() -> None:
    write_text(BLUEPRINT_DIR / "blueprint.md", render_blueprint())


def generate_understand(modules: list[dict[str, Any]]) -> None:
    for module in modules:
        write_text(UNDERSTAND_DIR / f"{module['slug']}.md", render_understand(module))


def generate_locate(modules: list[dict[str, Any]]) -> None:
    for module in modules:
        write_text(LOCATE_DIR / f"{module['slug']}.md", render_locate(module))


def generate_codegen(modules: list[dict[str, Any]]) -> None:
    for module in modules:
        write_text(CODEGEN_DIR / f"{module['slug']}.md", render_codegen(module))


def select_modules(module_slug: str | None) -> list[dict[str, Any]]:
    if not module_slug:
        return MODULES
    for module in MODULES:
        if module["slug"] == module_slug:
            return [module]
    raise ValueError(f"Unknown module slug: {module_slug}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate modular CodeBook markdowns for the Conduit test project.",
    )
    parser.add_argument(
        "--stage",
        choices=["all", "blueprint", "understand", "locate", "codegen"],
        default="all",
        help="Only regenerate one capability stage.",
    )
    parser.add_argument(
        "--module",
        choices=[module["slug"] for module in MODULES],
        help="Only regenerate one module.",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip rerunning gitingest and reuse the existing exported text.",
    )
    args = parser.parse_args()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    write_text(OUTPUT_ROOT / "README.md", render_readme())
    generate_sources(skip_ingest=args.skip_ingest)

    selected_modules = select_modules(args.module)

    if args.stage in {"all", "blueprint"}:
        generate_blueprint()
    if args.stage in {"all", "understand"}:
        generate_understand(selected_modules)
    if args.stage in {"all", "locate"}:
        generate_locate(selected_modules)
    if args.stage in {"all", "codegen"}:
        generate_codegen(selected_modules)


if __name__ == "__main__":
    main()
