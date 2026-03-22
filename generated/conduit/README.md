# Conduit（fastapi-realworld-example-app） 模块化代码书

这套产物把测试项目拆成了「先蓝图，再看懂，再定位，再编写」四层能力，并且按模块分别落盘，避免一次读整仓库造成长上下文质量衰减。

## 目录结构

- `00_source/gitingest.txt`：用 gitingest 导出的仓库全文本。
- `01_blueprint/blueprint.md`：系统级蓝图与模块总览。
- `02_understand/*.md`：逐模块的理解卡片。
- `03_locate/*.md`：逐模块的模拟问题定位。
- `04_codegen/*.md`：逐模块的模拟修改方案。

## 当前模块

- `01_user-auth`: 用户认证
- `02_user-management`: 用户管理
- `03_social-follow`: 社交关系
- `04_article-authoring`: 文章发布
- `05_comments`: 评论互动
- `06_tags`: 标签分类
- `07_favorites`: 收藏系统
- `08_feed`: 信息流
- `09_storage`: 数据库连接与仓库层
- `10_startup-config`: 系统启动与配置

## 复跑方式

```bash
python3 scripts/generate_conduit_module_books.py
python3 scripts/generate_conduit_module_books.py --stage understand --module 04_article-authoring
python3 scripts/generate_conduit_module_books.py --stage locate --module 08_feed --skip-ingest
```
