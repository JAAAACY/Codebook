# Task: B-2a — 角色系统实现：Prompt 改造 + engine 角色逻辑
# Wave: W3
# Project: CodeBook (mcp-server/)
# Working Dir: The repo root where files/CLAUDE.md exists

先读取以下文件，建立核心上下文：
1. files/CLAUDE.md — 全量读取（产品定义 + 技术栈约束 + 编码规范 + 禁止事项，~6K tokens）
2. files/CONTEXT.md — 全量读取（当前 sprint 进度 + 流水线状态 + 已知问题 + 待确认决策，~5K tokens）
3. files/INTERFACES.md — 只读 §3 角色系统（其余跳过，节约上下文空间）

📊 上下文预算：文档 ~10K + 源码 ~15K + 产出 ~15K + 执行 ~8K = ~48K tokens (24%) 🟢

【任务】流水线 B / 角色系统实现 — Part A（Prompt + engine 改造）
【所属】Wave 3（B-2a 先做，B-2b 后做）
【前置】B-1 已完成
【子 session 说明】原 B-2 拆为两个子 session。本 session 只改 prompt 配置和 engine.py

额外读取：
- docs/role_system_v3_design.md — B-1 产出的设计文档，全量读取
- mcp-server/prompts/codebook_config_v0.2.json — 当前配置

如果 D-2b 已完成：
- 读取 src/glossary/term_resolver.py 公开接口
- 角色逻辑中用 TermResolver 替代硬编码 banned_terms
如果 D-2b 未完成：
- 保持 _get_banned_terms() 不变，加 TODO: 接入 TermResolver

执行步骤：
1. 更新 prompts/ 配置：dev/pm/domain_expert 三视图的 prompt 模板
2. 修改 engine.py 中的角色相关逻辑
3. 向后兼容映射：ceo/investor → pm, qa → dev
4. 单元测试：验证三种角色输出差异

⚠️ 本 session 不改 ask_about.py / diagnose.py / read_chapter.py / codegen.py，那是 B-2b 的事。

═══ 质量自检清单（任务完成前逐项确认）═══

□ 1. 代码规范：所有新代码有类型注解 + structlog 日志 + 无 print
□ 2. 测试覆盖：新功能有正常路径 + 至少 1 个异常路径测试
□ 3. 回归验证：cd mcp-server && python -m pytest tests/ -x -q → 记录结果
□ 4. 接口一致：如修改了 tool 输入输出 → INTERFACES.md 已同步更新
□ 5. 错误处理：对外返回 {"status": "error", "error": str, "hint": str}
□ 6. 无硬编码：无 API Key / 模型名 / 绝对路径 硬编码
□ 7. 产出物完整：所有声称的产出文件确实存在且内容完整
□ 8. CONTEXT.md 已更新：追加任务日志（固定格式）
