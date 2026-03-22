# 评论互动 · 编写

> 模拟修改：给评论模块补一个编辑接口，让作者本人可以修改自己的评论内容。

## change_summary

- `app/models/schemas/comments.py`：只有创建评论的请求模型。 -> 新增 `CommentInUpdate`，承接评论编辑表单。
- `app/db/queries/sql/comments.sql`：只有创建与删除评论的 SQL。 -> 新增按评论 id 与作者身份更新正文的 SQL 语句。
- `app/db/repositories/comments.py`：仓库只支持新增、读取、删除。 -> 新增 `update_comment()` 封装，返回更新后的评论对象。
- `app/api/routes/comments.py`：API 没有评论编辑入口。 -> 新增 `PUT /articles/{slug}/comments/{comment_id}`。
- `tests/test_api/test_routes/test_comments.py`：测试不覆盖评论编辑。 -> 补上作者本人成功编辑评论的回归测试。

## unified_diff

```diff
diff --git a/app/models/schemas/comments.py b/app/models/schemas/comments.py
@@
 class CommentInCreate(RWSchema):
     body: str
+
+class CommentInUpdate(RWSchema):
+    body: str
diff --git a/app/db/queries/sql/comments.sql b/app/db/queries/sql/comments.sql
@@
 -- name: delete-comment-by-id!
 DELETE
 FROM commentaries
 WHERE id = :comment_id
   AND author_id = (SELECT id FROM users WHERE username = :author_username);
+
+-- name: update-comment-by-id<!
+UPDATE commentaries
+SET body = :body
+WHERE id = :comment_id
+  AND author_id = (SELECT id FROM users WHERE username = :author_username)
+RETURNING updated_at;
diff --git a/app/db/repositories/comments.py b/app/db/repositories/comments.py
@@
+    async def update_comment(self, *, comment: Comment, body: str, user: User) -> Comment:
+        updated_at = await queries.update_comment_by_id(
+            self.connection,
+            comment_id=comment.id_,
+            author_username=user.username,
+            body=body,
+        )
+        return comment.copy(update={"body": body, "updated_at": updated_at})
diff --git a/app/api/routes/comments.py b/app/api/routes/comments.py
@@
-from app.models.schemas.comments import (
-    CommentInCreate,
-    CommentInResponse,
-    ListOfCommentsInResponse,
-)
+from app.models.schemas.comments import (
+    CommentInCreate,
+    CommentInResponse,
+    CommentInUpdate,
+    ListOfCommentsInResponse,
+)
@@
+@router.put(
+    "/{comment_id}",
+    response_model=CommentInResponse,
+    name="comments:update-comment-for-article",
+    dependencies=[Depends(check_comment_modification_permissions)],
+)
+async def update_comment_for_article(
+    comment_update: CommentInUpdate = Body(..., embed=True, alias="comment"),
+    comment: Comment = Depends(get_comment_by_id_from_path),
+    user: User = Depends(get_current_user_authorizer()),
+    comments_repo: CommentsRepository = Depends(get_repository(CommentsRepository)),
+) -> CommentInResponse:
+    updated_comment = await comments_repo.update_comment(
+        comment=comment,
+        body=comment_update.body,
+        user=user,
+    )
+    return CommentInResponse(comment=updated_comment)
```

## blast_radius

- 文章详情页的评论操作区会多一个编辑入口与保存交互。
- 评论模型里的 `updated_at` 展示逻辑可能需要同步利用起来。

## verification_steps

```json
[
  {
    "step": "创建一条评论后，作者本人调用 `PUT /api/articles/{slug}/comments/{comment_id}` 修改正文。",
    "expected_result": "接口返回 200，评论正文更新成功，`updated_at` 发生变化。"
  },
  {
    "step": "换一个非作者账号尝试编辑同一条评论。",
    "expected_result": "接口返回 403，不允许越权修改。"
  }
]
```
