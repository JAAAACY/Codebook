"""
CodeBook Codegen — 端到端示例

演示如何用 codegen_prompt 模块将 locate 结果 + 用户指令
组装为 LLM prompt，以及如何解析 LLM 输出。

示例场景：conduit 项目注册报错文案中文化
"""

from codegen_prompt import (
    CodegenPromptBuilder,
    CodegenOutputParser,
    LocateResult,
    ExactLocation,
    build_codegen_prompt,
    parse_codegen_output,
)
import json


# ═══════════════════════════════════════════
# 示例 1：构建 Prompt
# ═══════════════════════════════════════════

def demo_build_prompt():
    """演示：从 locate 结果构建完整的 codegen prompt。"""

    # ── Step 1: 准备 locate 结果 ──
    locate_result = LocateResult(
        matched_modules="\n".join([
            "- **用户注册**：注册流程中的邮箱重复检查直接相关，"
            "报错文案从 `resources/strings.py` 读取",
            "- **注册重复检查**：`check_email_is_taken()` 执行实际的数据库查询，"
            "返回结果后由注册流程决定报错方式",
        ]),

        call_chain_mermaid="""\
```mermaid
graph TD
    A["用户提交注册表单"] --> B["接收注册请求<br/>authentication.py:L62-66"]
    B --> C["检查用户名是否重复<br/>services/authentication.py:L5-11"]
    C -->|用户名没重复| D["检查邮箱是否重复<br/>services/authentication.py:L14-20"]
    C -->|用户名已占用| E["返回 400 错误<br/>authentication.py:L67-71"]
    D -->|邮箱已注册| F["返回 400 错误<br/>authentication.py:L73-77"]
    D -->|邮箱可用| G["创建用户记录<br/>repositories/users.py:L29-48"]
    G --> H["生成登录令牌<br/>jwt.py:L27-32"]
    H --> I["返回用户信息 + 令牌"]
    style E fill:#ffcdd2
    style F fill:#ffcdd2
    style I fill:#c8e6c9
```""",

        exact_locations=[
            ExactLocation(
                file="app/resources/strings.py",
                line=1,
                why_it_matters="所有报错文案的定义位置，当前全是英文技术语言",
                certainty="非常确定",
            ),
            ExactLocation(
                file="app/api/routes/authentication.py",
                line=73,
                why_it_matters="邮箱重复时的错误处理位置，当前只返回纯文字报错",
                certainty="非常确定",
            ),
        ],

        diagnosis=(
            "问题不在后端逻辑，而在错误信息的表达方式。"
            "邮箱重复检查本身工作正常，但报错文案用英文技术语言写成，"
            "普通用户看不懂。同时，邮箱已注册时只报错不引导，"
            "用户不知道可以去登录。"
        ),
    )

    # ── Step 2: 准备当前代码 ──
    current_code = {
        "app/resources/strings.py": '''\
# Strings for error messages and responses

INCORRECT_LOGIN_INPUT = "incorrect email or password"
USERNAME_TAKEN = "user with this username already exists"
EMAIL_TAKEN = "user with this email already exists"
USER_DOES_NOT_EXIST_ERROR = "user does not exist"
ARTICLE_DOES_NOT_EXIST_ERROR = "article does not exist"
ARTICLE_ALREADY_EXISTS = "article already exists"
''',
        "app/api/routes/authentication.py": '''\
from fastapi import APIRouter, Body, Depends, HTTPException
from starlette.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST

from app.api.dependencies.database import get_repository
from app.db.repositories.users import UsersRepository
from app.models.schemas.users import UserInCreate, UserInResponse, UserWithToken
from app.resources import strings
from app.services.authentication import check_email_is_taken, check_username_is_taken
from app.services.jwt import create_jwt_token

router = APIRouter()


@router.post("/users/login", response_model=UserInResponse, name="auth:login")
async def login(
    user_login: UserInLogin = Body(..., embed=True, alias="user"),
    users_repo: UsersRepository = Depends(get_repository(UsersRepository)),
) -> UserInResponse:
    wrong_login_error = HTTPException(
        status_code=HTTP_400_BAD_REQUEST,
        detail=strings.INCORRECT_LOGIN_INPUT,
    )

    try:
        user = await users_repo.get_user_by_email(email=user_login.email)
    except EntityDoesNotExist:
        raise wrong_login_error

    if not user.check_password(user_login.password):
        raise wrong_login_error

    token = create_jwt_token(
        jwt_content=JWTUser(username=user.username),
        secret_key=str(settings.secret_key),
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
    "/users",
    status_code=HTTP_201_CREATED,
    response_model=UserInResponse,
    name="auth:register",
)
async def register(
    user_create: UserInCreate = Body(..., embed=True, alias="user"),
    users_repo: UsersRepository = Depends(get_repository(UsersRepository)),
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

    user = await users_repo.create_user(
        username=user_create.username,
        email=user_create.email,
        password=user_create.password,
    )

    token = create_jwt_token(
        jwt_content=JWTUser(username=user.username),
        secret_key=str(settings.secret_key),
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
''',
    }

    # ── Step 3: 构建 prompt ──
    messages = build_codegen_prompt(
        user_instruction="把注册时的报错文案改成中文友好提示，邮箱已注册时引导用户去登录",
        locate_result=locate_result,
        current_code=current_code,
    )

    # ── 输出 ──
    print("=" * 60)
    print("构建的 Prompt Messages")
    print("=" * 60)
    for msg in messages:
        print(f"\n{'─' * 40}")
        print(f"Role: {msg['role']}")
        print(f"{'─' * 40}")
        # 打印前 200 字符预览
        content = msg["content"]
        if len(content) > 500:
            print(content[:500])
            print(f"\n... (共 {len(content)} 字符)")
        else:
            print(content)

    return messages


# ═══════════════════════════════════════════
# 示例 2：解析 LLM 输出
# ═══════════════════════════════════════════

SAMPLE_LLM_OUTPUT = """\
## 变更摘要

| 文件 | 行号 | 改之前（当前做什么） | 改之后（变更做什么） |
|------|------|---------------------|---------------------|
| `app/resources/strings.py` | L全文 | 报错信息用英文技术语言 | 改为中文友好提示，引导用户下一步操作 |
| `app/api/routes/authentication.py` | L73-77 | 邮箱重复时只报错 | 报错信息中增加「去登录」的引导 |

---

## 代码变更

> 以下是给程序员看的具体代码改动。如果你只关心业务变化，看上面的变更摘要就够了。

### 变更 1：更新错误提示文案

**文件**：`app/resources/strings.py`

```diff
- INCORRECT_LOGIN_INPUT = "incorrect email or password"
+ INCORRECT_LOGIN_INPUT = "邮箱或密码不正确，请重试或找回密码"

- USERNAME_TAKEN = "user with this username already exists"
+ USERNAME_TAKEN = "该用户名已被使用，请换一个试试"

- EMAIL_TAKEN = "user with this email already exists"
+ EMAIL_TAKEN = "该邮箱已注册。如果是您的账号，请直接登录"

- USER_DOES_NOT_EXIST_ERROR = "user does not exist"
+ USER_DOES_NOT_EXIST_ERROR = "找不到该用户"

- ARTICLE_DOES_NOT_EXIST_ERROR = "article does not exist"
+ ARTICLE_DOES_NOT_EXIST_ERROR = "文章不存在或已被删除"

- ARTICLE_ALREADY_EXISTS = "article already exists"
+ ARTICLE_ALREADY_EXISTS = "文章标题重复，请修改后重试"
```

**改之前**：所有错误提示用英文技术语言，用户看不懂。
**改之后**：中文友好提示，每条都告诉用户「怎么办」而不只是「什么错」。

---

### 变更 2：邮箱重复时返回更丰富的错误信息

**文件**：`app/api/routes/authentication.py`

```diff
     if await check_email_is_taken(users_repo, user_create.email):
         raise HTTPException(
             status_code=HTTP_400_BAD_REQUEST,
-            detail=strings.EMAIL_TAKEN,
+            detail={
+                "message": strings.EMAIL_TAKEN,
+                "action": "login",
+                "action_label": "去登录"
+            },
         )
```

**改之前**：返回纯文字错误信息，前端只能展示一行文字。
**改之后**：返回结构化错误，包含引导动作，前端可以据此展示「去登录」按钮。

---

## 影响范围

| 受影响的模块/文件 | 影响说明 | 是否需要同步修改 |
|-------------------|----------|-----------------|
| **前端注册页面** | 需要适配新的错误返回格式——原来是纯字符串，现在邮箱重复时会返回包含引导动作的结构化数据 | 需要 |
| **前端登录页面** | 错误文案从英文变中文，如果前端有自己的文案映射层，需要同步更新 | 建议 |
| **现有测试用例** | 测试中检查错误文案的断言会失败——因为预期的文案从英文变成了中文 | 需要 |
| **API 文档** | 如果有 API 文档记录了错误格式，需要更新邮箱重复时的返回结构 | 建议 |

---

## 验证方式

验证这个改动生效的操作步骤：

1. **注册一个新用户**（用户名：testuser，邮箱：test@test.com）→ 应该正常注册成功，返回 201（创建成功）
2. **再次用同一个邮箱注册**（用户名：testuser2，邮箱：test@test.com）→ 应该看到中文提示「该邮箱已注册。如果是您的账号，请直接登录」，并且返回数据里包含「去登录」的引导动作
3. **用已存在的用户名注册**（用户名：testuser，邮箱：new@test.com）→ 应该看到「该用户名已被使用，请换一个试试」
4. **用错误密码登录**（邮箱：test@test.com，密码：wrongpass）→ 应该看到「邮箱或密码不正确，请重试或找回密码」
"""


def demo_parse_output():
    """演示：解析 LLM 输出为结构化结果。"""

    result = parse_codegen_output(SAMPLE_LLM_OUTPUT)

    print("=" * 60)
    print("解析结果")
    print("=" * 60)

    print("\n📋 变更摘要:")
    for item in result.change_summary:
        print(f"  • {item.file} ({item.line_range})")
        print(f"    改之前: {item.before}")
        print(f"    改之后: {item.after}")

    print(f"\n📝 Diff 代码块: {len(result.diff_blocks)} 个")
    for block in result.diff_blocks:
        print(f"  • [{block.title}] {block.file}")
        diff_lines = block.diff_content.count("\n") + 1
        print(f"    diff 行数: {diff_lines}")
        print(f"    改之前: {block.before_desc}")
        print(f"    改之后: {block.after_desc}")

    print(f"\n💥 影响范围: {len(result.blast_radius)} 项")
    for item in result.blast_radius:
        print(f"  • {item.file_or_module} [{item.action_required.value}]")
        print(f"    {item.impact}")

    print(f"\n✅ 验证步骤: {len(result.verification_steps)} 步")
    for i, step in enumerate(result.verification_steps, 1):
        print(f"  {i}. {step.step}")
        print(f"     → {step.expected_result}")

    return result


# ═══════════════════════════════════════════
# 示例 3：导出为 JSON（用于 codebook_config 集成）
# ═══════════════════════════════════════════

def demo_export_config():
    """演示：导出 prompt 配置为 JSON 格式。"""
    from codegen_prompt import get_codegen_prompt_config
    config = get_codegen_prompt_config()
    print("=" * 60)
    print("Prompt 配置 (可合并到 codebook_config)")
    print("=" * 60)
    print(json.dumps(config, ensure_ascii=False, indent=2)[:1000])
    print("...")


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("\n🔧 Demo 1: 构建 Prompt\n")
    demo_build_prompt()

    print("\n\n🔧 Demo 2: 解析 LLM 输出\n")
    demo_parse_output()

    print("\n\n🔧 Demo 3: 导出配置\n")
    demo_export_config()
