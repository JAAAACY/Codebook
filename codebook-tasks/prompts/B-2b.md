# Task: B-2b — 角色系统实现：5 Tool 适配 + 回归测试
# Wave: W3
# Project: CodeBook (mcp-server/)
# Working Dir: The repo root where files/CLAUDE.md exists

先读取以下文件，建立核心上下文：
1. files/CLAUDE.md — 全量读取（产品定义 + 技术栈约束 + 编码规范 + 禁止事项，~6K tokens）
2. files/CONTEXT.md — 全量读取（当前 sprint 进度 + 流水线状态 + 已知问题 + 待确认决策，~5K tokens）
3. files/INTERFACES.md — 只读 §2 Tool 契约, §3 角色系统（其余跳过，节约上下文空间）

📊 上下文预算：文档 ~14K + 源码 ~20K + 产出 ~12K + 执行 ~12K = ~58K tokens (29%) 🟢

【任务】流水线 B / 角色系统实现 — Part B（5 Tool 角色适配 + 回归）
【所属】Wave 3（B-2a 完成后串行执行）
【前置】B-2a 已完成

额外读取：
- docs/role_system_v3_design.md — 全量
- B-2a 修改后的 engine.py 和 prompts/ — 理解新角色逻辑

【并行注意】D-3 同 Wave 也在修改 ask_about.py / diagnose.py：
- B-2b 只改角色逻辑（ROLE_CONFIG / ROLE_GUIDANCE / prompt 模板）
- D-3 只改记忆读写（DiagnosisCache → ProjectMemory）
- 两者改动点不重叠
- 如果 D-3 已完成：DiagnosisCache 已替换为 ProjectMemory，注意适配
- 如果 D-3 未完成：保持现有 DiagnosisCache 不变

执行步骤：
1. 修改 ask_about.py 的 ROLE_CONFIG → 三视图
2. 修改 diagnose.py 的 ROLE_GUIDANCE → 三视图
3. 修改 read_chapter.py / codegen.py 的角色逻辑
4. 新增 domain_expert 角色处理
5. 对 2 个测试仓库跑对比测试：
   - ask_about: pm 视角 vs dev 视角 vs domain_expert 视角
   - read_chapter: pm vs dev
6. 质量评估：PM 视角 ≥ 9.0/10
7. 回归测试：现有 pytest 全部通过
8. 更新 INTERFACES.md §3

═══ 质量自检清单（任务完成前逐项确认）═══

□ 1. 代码规范：所有新代码有类型注解 + structlog 日志 + 无 print
□ 2. 测试覆盖：新功能有正常路径 + 至少 1 个异常路径测试
□ 3. 回归验证：cd mcp-server && python -m pytest tests/ -x -q → 记录结果
□ 4. 接口一致：如修改了 tool 输入输出 → INTERFACES.md 已同步更新
□ 5. 错误处理：对外返回 {"status": "error", "error": str, "hint": str}
□ 6. 无硬编码：无 API Key / 模型名 / 绝对路径 硬编码
□ 7. 产出物完整：所有声称的产出文件确实存在且内容完整
□ 8. CONTEXT.md 已更新：追加任务日志（固定格式）
