# 第4步｜编写

## change_summary

- `app/resources/strings.py`：改之前，邮箱重复时返回英文技术文案 `user with this email already exists`；改之后，改成中文友好提示 `该邮箱已注册，请直接登录或使用其他邮箱`。
- `tests/test_api/test_routes/test_registration.py`：改之前，失败注册只校验 400 状态码；改之后，增加对邮箱重复时返回文案的断言，避免后续回退成技术化提示。

## unified_diff

> 以下是给程序员看的具体代码改动。如果你只关心业务变化，看上面的 change_summary 就够了。

```diff
diff --git a/app/resources/strings.py b/app/resources/strings.py
index 0d7d5ff..b5b33da 100644
--- a/app/resources/strings.py
+++ b/app/resources/strings.py
@@ -7,7 +7,7 @@ USER_IS_NOT_AUTHOR_OF_ARTICLE = "you are not an author of this article"
 
 INCORRECT_LOGIN_INPUT = "incorrect email or password"
 USERNAME_TAKEN = "user with this username already exists"
-EMAIL_TAKEN = "user with this email already exists"
+EMAIL_TAKEN = "该邮箱已注册，请直接登录或使用其他邮箱"
 
 UNABLE_TO_FOLLOW_YOURSELF = "user can not follow him self"
 UNABLE_TO_UNSUBSCRIBE_FROM_YOURSELF = "user can not unsubscribe from him self"
diff --git a/tests/test_api/test_routes/test_registration.py b/tests/test_api/test_routes/test_registration.py
index 3cbca4c..617ec83 100644
--- a/tests/test_api/test_routes/test_registration.py
+++ b/tests/test_api/test_routes/test_registration.py
@@ -53,3 +53,6 @@ async def test_failed_user_registration_when_some_credentials_are_taken(
         app.url_path_for("auth:register"), json=registration_json
     )
     assert response.status_code == HTTP_400_BAD_REQUEST
+    if credentials_part == "email":
+        assert response.json()["detail"] == "该邮箱已注册，请直接登录或使用其他邮箱"
+
```

## blast_radius

- `app/resources/strings.py`：`EMAIL_TAKEN` 常量被改成中文友好提示，因此所有直接复用这个常量的邮箱重复报错都会一起变成中文。
- `app/api/routes/authentication.py`：逻辑本身不需要改，但注册接口会在 `app/api/routes/authentication.py:L73-L77` 继续读取新的 `EMAIL_TAKEN` 值并返回给前端。
- `tests/test_api/test_routes/test_registration.py`：测试从“只验证 400 状态码”升级为“同时验证具体文案”，以后只要有人改坏这个提示，测试就会直接失败。

## verification_steps

```json
[
  {
    "step": "先注册一个邮箱为 `test@test.com` 的新用户。",
    "expected_result": "接口返回 201（创建成功），用户注册完成。"
  },
  {
    "step": "再次使用相同邮箱发起注册。",
    "expected_result": "接口返回 400（请求有误），错误文案为 `该邮箱已注册，请直接登录或使用其他邮箱`。"
  },
  {
    "step": "再使用一个未注册邮箱发起注册。",
    "expected_result": "接口仍然正常成功，说明只影响邮箱重复分支。"
  }
]
```
