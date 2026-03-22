# 收藏系统 · 编写

> 模拟修改：新增 `GET /api/articles/favorites/me`，让前端不用自己拼用户名也能直接拿当前用户收藏列表。

## change_summary

- `app/api/routes/articles/articles_common.py`：只有按用户名的底层筛选，没有面向当前用户的显式收藏接口。 -> 新增一个复用现有仓库逻辑的 `favorites/me` 路由。
- `tests/test_api/test_routes/test_articles.py`：测试只覆盖收藏状态切换，不覆盖“我的收藏列表”。 -> 补上当前用户获取自己收藏文章列表的回归测试。

## unified_diff

```diff
diff --git a/app/api/routes/articles/articles_common.py b/app/api/routes/articles/articles_common.py
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
```

## blast_radius

- 前端会多一个更稳定的收藏入口，不再依赖把用户名塞进 query 参数。
- 如果未来有“我的收藏”页面，这条接口可以直接复用。

## verification_steps

```json
[
  {
    "step": "先收藏两篇文章，再请求 `GET /api/articles/favorites/me`。",
    "expected_result": "返回当前用户收藏的文章列表，数量与收藏数一致。"
  },
  {
    "step": "取消其中一篇收藏后再次请求该接口。",
    "expected_result": "返回列表即时减少一篇，被取消的文章不再出现。"
  }
]
```
