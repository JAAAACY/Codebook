# CodeBook 原型验证：编写（Codegen）

> 用户指令：「把注册时的报错文案改成中文友好提示，邮箱已注册时引导用户去登录」

---

## 变更方案

| 文件 | 行号 | 改之前（当前做什么） | 改之后（变更做什么） |
|------|------|---------------------|---------------------|
| `resources/strings.py` | L全文 | 报错信息用英文技术语言 | 改为中文友好提示，引导用户下一步操作 |
| `authentication.py` | L73-77 | 邮箱重复时只报错 | 报错信息中增加「去登录」的引导 |

---

## 代码变更

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

**文件**：`app/api/routes/authentication.py:L73-77`

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
**改之后**：返回结构化错误，包含引导动作（`action: "login"`），前端可以据此展示「去登录」按钮。

---

## 影响范围

| 受影响的模块/文件 | 影响说明 |
|-------------------|----------|
| **前端注册页面** | 需要适配新的错误返回格式——原来是纯字符串，现在邮箱重复时会返回 JSON 对象。前端需要判断 `detail` 是字符串还是对象。 |
| **前端登录页面** | 错误文案从英文变中文，如果前端有自己的文案映射层，需要同步更新。 |
| **现有测试用例** | `tests/test_api/test_routes/test_registration.py` 中检查错误文案的测试会失败——因为预期的文案从英文变成了中文。 |
| **API 文档** | 如果有 API 文档记录了错误格式，需要更新邮箱重复时的返回结构。 |

---

## 验证方式

验证这个改动生效的操作步骤：

1. **注册一个新用户**（用户名：testuser，邮箱：test@test.com）→ 应该正常注册成功
2. **再次用同一个邮箱注册**（用户名：testuser2，邮箱：test@test.com）→ 应该看到中文提示「该邮箱已注册。如果是您的账号，请直接登录」，并且返回数据里包含 `action: "login"`
3. **用已存在的用户名注册**（用户名：testuser，邮箱：new@test.com）→ 应该看到「该用户名已被使用，请换一个试试」
4. **用错误密码登录**（邮箱：test@test.com，密码：wrongpass）→ 应该看到「邮箱或密码不正确，请重试或找回密码」
