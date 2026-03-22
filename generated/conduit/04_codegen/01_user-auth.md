# 用户认证 · 编写

> 模拟修改：把邮箱已注册提示改成中文友好文案，并在错误响应里带一个供前端识别的去登录动作。

## change_summary

- `app/resources/strings.py`：邮箱重复时只返回英文技术文案。 -> 改成中文友好提示，让用户知道下一步该去登录。
- `app/api/routes/authentication.py`：邮箱重复时只返回纯字符串 `detail`。 -> 改成结构化错误对象，补充 `action=login` 和按钮文案。
- `tests/test_api/test_routes/test_registration.py`：测试只校验 400 状态码，没有验证错误结构。 -> 补上邮箱重复场景的结构化错误断言，避免回归。

## unified_diff

```diff
diff --git a/app/resources/strings.py b/app/resources/strings.py
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
```

## blast_radius

- 注册页前端如果默认把 `detail` 当字符串渲染，需要兼容邮箱重复时的对象格式。
- 测试用例与 API 文档需要同步更新错误结构说明。

## verification_steps

```json
[
  {
    "step": "先注册一个邮箱为 `test@test.com` 的新账号。",
    "expected_result": "注册成功，返回用户信息和 token。"
  },
  {
    "step": "再次使用相同邮箱发起注册。",
    "expected_result": "返回 400，`detail.action` 为 `login`，提示文案为中文友好表达。"
  }
]
```
