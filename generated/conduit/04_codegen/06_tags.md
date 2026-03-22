# 标签分类 · 编写

> 模拟修改：把标签接口升级为“标签名 + 被多少篇文章使用”，并按热度倒序返回。

## change_summary

- `app/models/schemas/tags.py`：标签响应模型只有字符串数组。 -> 新增标签对象结构，包含 `name` 和 `articles_count`。
- `app/db/queries/sql/tags.sql`：只查标签名，不做聚合。 -> 按标签聚合文章数，并按热度倒序返回。
- `app/db/repositories/tags.py`：仓库返回 `List[str]`。 -> 仓库返回结构化标签对象列表。
- `tests/test_api/test_routes/test_tags.py`：测试只关心标签是否去重。 -> 增加对 `articles_count` 和排序的断言。

## unified_diff

```diff
diff --git a/app/models/schemas/tags.py b/app/models/schemas/tags.py
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
```

## blast_radius

- 前端消费 `/api/tags` 的地方需要适配从字符串数组变成对象数组。
- 如果产品只展示标签名，需要明确取 `tag.name` 字段。

## verification_steps

```json
[
  {
    "step": "创建多篇带重复标签的文章后请求 `GET /api/tags`。",
    "expected_result": "返回数组项含 `name` 与 `articles_count`，且按使用次数从高到低排序。"
  },
  {
    "step": "发文页重新加载标签选择器。",
    "expected_result": "标签仍能正常显示，只是多了热度可用信息。"
  }
]
```
