# 系统启动与配置 · 编写

> 模拟修改：在生产环境关闭 Swagger / ReDoc / OpenAPI 暴露，减少公开 API 面。

## change_summary

- `app/core/settings/production.py`：生产环境仅指定 `env_file`，其他配置沿用默认值。 -> 显式关闭 `docs_url`、`redoc_url` 与 `openapi_url`。

## unified_diff

```diff
diff --git a/app/core/settings/production.py b/app/core/settings/production.py
@@
 class ProdAppSettings(AppSettings):
+    docs_url: str = ""
+    redoc_url: str = ""
+    openapi_url: str = ""
+
     class Config(AppSettings.Config):
         env_file = "prod.env"
```

## blast_radius

- 线上运维与开发如果依赖 `/docs` 调试，需要改用本地或非生产环境。
- 任何自动拉取线上 OpenAPI 的脚本都要改成从构建产物或非生产环境获取。

## verification_steps

```json
[
  {
    "step": "用 `APP_ENV=prod` 启动应用后访问 `/docs`、`/redoc`、`/openapi.json`。",
    "expected_result": "这三个地址都不再公开可访问。"
  },
  {
    "step": "切回 `APP_ENV=dev` 再访问相同地址。",
    "expected_result": "开发环境仍保留文档入口，方便联调与调试。"
  }
]
```
