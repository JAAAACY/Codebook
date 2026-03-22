# 数据库连接与仓库层 · 编写

> 模拟修改：启动时把连接池 min/max 打进日志，并把开发环境默认池大小调成 1-5，避免本地误占满数据库。

## change_summary

- `app/db/events.py`：启动日志只写“Connecting to PostgreSQL”，看不到连接池范围。 -> 补充 min/max，排查环境配置时一眼可见。
- `app/core/settings/development.py`：开发环境沿用 10/10 的默认池大小。 -> 显式调成 `min=1, max=5`，更适合本地调试。

## unified_diff

```diff
diff --git a/app/db/events.py b/app/db/events.py
@@
-    logger.info("Connecting to PostgreSQL")
+    logger.info(
+        "Connecting to PostgreSQL (pool min={}, max={})",
+        settings.min_connection_count,
+        settings.max_connection_count,
+    )
diff --git a/app/core/settings/development.py b/app/core/settings/development.py
@@
 class DevAppSettings(AppSettings):
     debug: bool = True
     title: str = "Dev FastAPI example application"
+    min_connection_count: int = 1
+    max_connection_count: int = 5
```

## blast_radius

- 只影响开发环境默认配置与启动日志，不改变生产逻辑。
- 运维或本地开发排障时会更容易判断是否因为连接池配置导致问题。

## verification_steps

```json
[
  {
    "step": "以开发环境启动应用并观察控制台日志。",
    "expected_result": "日志中能看到连接池的 min/max 配置值。"
  },
  {
    "step": "在本地数据库资源有限的环境下重复启动多个服务实例。",
    "expected_result": "相比原来更不容易因为默认连接数过大而占满本地数据库连接。"
  }
]
```
