# 社交关系 · 编写

> 模拟修改：把关注/取关接口改成幂等设计，重复请求直接返回当前状态，不再报错。

## change_summary

- `app/api/routes/profiles.py`：重复关注或重复取关都会抛 400。 -> 改成直接返回当前 profile，让接口天然支持前端重试。
- `tests/test_api/test_routes/test_profiles.py`：测试把重复请求视作失败场景。 -> 改成验证重复请求也返回 200，并保持状态不变。

## unified_diff

```diff
diff --git a/app/api/routes/profiles.py b/app/api/routes/profiles.py
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
```

## blast_radius

- 前端如果依赖 400 来区分“已关注”状态，需要改成根据返回的 `profile.following` 判断。
- 与关注按钮相关的自动化测试需要同步调整预期。

## verification_steps

```json
[
  {
    "step": "对同一作者连续发送两次 `POST /api/profiles/{username}/follow`。",
    "expected_result": "两次都返回 200，第二次不会新增重复关注关系。"
  },
  {
    "step": "对未关注作者连续发送两次 `DELETE /api/profiles/{username}/follow`。",
    "expected_result": "两次都返回 200，最终状态仍是 `following=false`。"
  }
]
```
