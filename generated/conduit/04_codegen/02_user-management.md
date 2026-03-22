# 用户管理 · 编写

> 模拟修改：给修改密码接口增加最小长度 8 的校验，避免弱密码直接生效。

## change_summary

- `app/models/schemas/users.py`：密码字段只有类型约束，没有最小长度要求。 -> 用 `Field(min_length=8)` 给更新场景加最基本的安全门槛。
- `tests/test_api/test_routes/test_users.py`：测试只覆盖修改成功，不覆盖弱密码被拒绝。 -> 增加 422 场景，确保短密码不能通过校验。

## unified_diff

```diff
diff --git a/app/models/schemas/users.py b/app/models/schemas/users.py
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
```

## blast_radius

- 设置页如果允许小于 8 位的密码，需要同步前端表单规则。
- 相关自动化测试和接口文档都需要更新预期。

## verification_steps

```json
[
  {
    "step": "使用已登录用户调用 `PUT /api/user`，传入 `password=short`。",
    "expected_result": "接口返回 422，提示密码长度不满足要求。"
  },
  {
    "step": "再次传入一个长度不少于 8 的新密码。",
    "expected_result": "接口返回 200，且新密码可用于后续登录。"
  }
]
```
