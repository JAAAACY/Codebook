# 文章发布 · 编写

> 模拟修改：当标题冲突时自动生成递增 slug，例如 `test-slug-2`，而不是直接报错。

## change_summary

- `app/services/articles.py`：只有 `get_slug_for_article()`，没有唯一 slug 生成器。 -> 增加异步唯一 slug 生成逻辑，循环检查冲突并追加序号。
- `app/api/routes/articles/articles_resource.py`：创建文章时一旦 slug 冲突就立即返回 400。 -> 改成调用唯一 slug 生成器，继续完成创建。
- `tests/test_api/test_routes/test_articles.py`：测试把重复标题视作失败。 -> 改成验证第二篇文章也能创建成功，并拿到带序号的新 slug。

## unified_diff

```diff
diff --git a/app/services/articles.py b/app/services/articles.py
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
```

## blast_radius

- 文章 URL 规则会变化，前端与 SEO 相关逻辑要接受递增 slug。
- 任何基于 slug 唯一失败提示的前端交互都需要同步更新。

## verification_steps

```json
[
  {
    "step": "先创建标题为 `Test Slug` 的文章，再重复创建一次同标题文章。",
    "expected_result": "第二次也返回 201，新文章 slug 自动变成 `test-slug-2`。"
  },
  {
    "step": "访问两篇文章的详情页与编辑页。",
    "expected_result": "两篇文章都能独立打开，不会互相覆盖。"
  }
]
```
