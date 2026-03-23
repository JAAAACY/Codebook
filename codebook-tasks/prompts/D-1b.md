# Task: D-1b — 存储层：迁移 + RepoCache 集成 + 回归
# Wave: W1
# Project: CodeBook (mcp-server/)
# Working Dir: The repo root where files/CLAUDE.md exists

先读取以下文件，建立核心上下文：
1. files/CLAUDE.md — 全量读取（产品定义 + 技术栈约束 + 编码规范 + 禁止事项，~6K tokens）
2. files/CONTEXT.md — 全量读取（当前 sprint 进度 + 流水线状态 + 已知问题 + 待确认决策，~5K tokens）
3. files/INTERFACES.md — 只读 §1 数据结构（SummaryContext 等）, §2.1 scan_repo（其余跳过，节约上下文空间）

📊 上下文预算：文档 ~12K + 源码 ~15K + 产出 ~10K + 执行 ~10K = ~47K tokens (24%) 🟢

【任务】流水线 D / 持久化存储层 — Part B（迁移 + 集成）
【所属】Wave 1（D-1a 完成后串行执行）
【前置】D-1a 已完成

额外读取源码：
- mcp-server/src/tools/_repo_cache.py — 全量读取，理解当前缓存逻辑
- mcp-server/src/memory/project_memory.py — D-1a 的产出，理解公开 API

执行步骤：

1. 创建 src/memory/migration.py：
   - 检测 ~/.codebook_cache/ 旧目录
   - 自动迁移到 ~/.codebook/memory/
   - 迁移后留 .migrated marker
   - 迁移失败不崩溃，降级到全新状态

2. 修改 src/tools/_repo_cache.py：
   - RepoCache.store() 内部委托 ProjectMemory.store_context()
   - RepoCache.get() 内部委托 ProjectMemory.get_context()
   - 保持公开 API 完全不变
   - 启动时触发 migration.py 的迁移检查

3. 测试（至少 6 个用例）：
   - test_migration.py：旧→新迁移 + 迁移幂等性 + 迁移失败降级
   - test_repo_cache_compat.py：确认 RepoCache 行为不变（回归测试）

4. 回归验证重点：
   修改 _repo_cache.py 后，现有的 scan_repo → read_chapter → diagnose → ask_about 链路不能断。
   至少手动跑一次 scan_repo + read_chapter 确认无报错。

═══ 质量自检清单（任务完成前逐项确认）═══

□ 1. 代码规范：所有新代码有类型注解 + structlog 日志 + 无 print
□ 2. 测试覆盖：新功能有正常路径 + 至少 1 个异常路径测试
□ 3. 回归验证：cd mcp-server && python -m pytest tests/ -x -q → 记录结果
□ 4. 接口一致：如修改了 tool 输入输出 → INTERFACES.md 已同步更新
□ 5. 错误处理：对外返回 {"status": "error", "error": str, "hint": str}
□ 6. 无硬编码：无 API Key / 模型名 / 绝对路径 硬编码
□ 7. 产出物完整：所有声称的产出文件确实存在且内容完整
□ 8. CONTEXT.md 已更新：追加任务日志（固定格式）
