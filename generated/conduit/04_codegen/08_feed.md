# 信息流 · 编写

> 模拟修改：给 feed 增加冷启动兜底：当用户还没关注任何作者时，回退到全站最新文章。

## change_summary

- `app/api/routes/articles/articles_common.py`：feed 查询结果为空时，接口直接把空列表返回给前端。 -> 如果关注流为空，就回退到全站文章列表作为冷启动兜底。
- `tests/test_api/test_routes/test_articles.py`：测试把无关注用户收到空列表当成预期。 -> 改成验证接口会返回可浏览的兜底内容。

## unified_diff

```diff
diff --git a/app/api/routes/articles/articles_common.py b/app/api/routes/articles/articles_common.py
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
```

## blast_radius

- 登录首页会从“空白”变成“兜底推荐”，需要确认产品是否接受这种心智变化。
- feed 指标与推荐策略会被冷启动兜底影响，需要单独埋点区分。

## verification_steps

```json
[
  {
    "step": "准备一个没有关注任何作者的新用户，并确保全站已有文章。",
    "expected_result": "请求 `GET /api/articles/feed` 时不再返回空列表，而是返回全站文章。"
  },
  {
    "step": "给同一个用户新增一条关注关系后再次请求 feed。",
    "expected_result": "接口重新回到只返回被关注作者文章的专属流。"
  }
]
```
