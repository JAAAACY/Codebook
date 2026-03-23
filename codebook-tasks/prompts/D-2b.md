# Task: D-2b — 术语飞轮：engine 集成 + term_correct + 端到端
# Wave: W2
# Project: CodeBook (mcp-server/)
# Working Dir: The repo root where files/CLAUDE.md exists

先读取以下文件，建立核心上下文：
1. files/CLAUDE.md — 全量读取（产品定义 + 技术栈约束 + 编码规范 + 禁止事项，~6K tokens）
2. files/CONTEXT.md — 全量读取（当前 sprint 进度 + 流水线状态 + 已知问题 + 待确认决策，~5K tokens）
3. files/INTERFACES.md — 只读 §2.1 scan_repo, §2.2 read_chapter（其余跳过，节约上下文空间）

📊 上下文预算：文档 ~10K + 源码 ~12K + 产出 ~10K + 执行 ~8K = ~40K tokens (20%) 🟢

【任务】流水线 D / 术语飞轮 MVP — Part B（集成 + 新 tool + 端到端验证）
【所属】Wave 2（D-2a 完成后串行执行）
【前置】D-2a 已完成

额外读取源码：
- mcp-server/src/summarizer/engine.py — 重点读 L100-150 的 _get_banned_terms() 和 build_l2_prompt/build_l3_prompt
- mcp-server/src/glossary/term_resolver.py — D-2a 的产出

当前术语注入链路确认：
- engine.py: _get_banned_terms() 读 codebook_config_v0.2.json → banned_terms_in_pm_fields.terms
- engine.py: build_l2_prompt 注入 {banned_terms}
- engine.py: build_l3_prompt 注入 {banned_terms} + {http_status_annotations}
- ask_about.py: ROLE_CONFIG 各角色 banned_terms 字符串（B 线职责，不碰）

执行步骤：

1. 创建 src/tools/term_correct.py：
   新 MCP tool，输入：source_term, correct_translation, wrong_translation?, context?
   输出：{"status": "ok", "message": str, "affected_scope": "当前项目"}

2. 修改 engine.py：
   _get_banned_terms() 内部：
   - 尝试用 TermResolver.resolve()
   - 如果 TermResolver 不可用（无 repo_url），降级到原 JSON 读取
   - 不改变函数签名和返回格式

3. 修改 server.py 注册 term_correct

4. 注意：不要改 ask_about.py 的角色逻辑（B 线职责）

5. 端到端验证：
   a. 对测试仓库运行 scan_repo
   b. 调用 term_correct 纠正一个术语
   c. 再运行 read_chapter 确认新术语已生效
   d. 记录验证结果

═══ 质量自检清单（任务完成前逐项确认）═══

□ 1. 代码规范：所有新代码有类型注解 + structlog 日志 + 无 print
□ 2. 测试覆盖：新功能有正常路径 + 至少 1 个异常路径测试
□ 3. 回归验证：cd mcp-server && python -m pytest tests/ -x -q → 记录结果
□ 4. 接口一致：如修改了 tool 输入输出 → INTERFACES.md 已同步更新
□ 5. 错误处理：对外返回 {"status": "error", "error": str, "hint": str}
□ 6. 无硬编码：无 API Key / 模型名 / 绝对路径 硬编码
□ 7. 产出物完整：所有声称的产出文件确实存在且内容完整
□ 8. CONTEXT.md 已更新：追加任务日志（固定格式）
