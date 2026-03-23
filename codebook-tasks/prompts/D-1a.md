# Task: D-1a — 存储层：数据模型 + ProjectMemory 核心
# Wave: W1
# Project: CodeBook (mcp-server/)
# Working Dir: The repo root where files/CLAUDE.md exists

先读取以下文件，建立核心上下文：
1. files/CLAUDE.md — 全量读取（产品定义 + 技术栈约束 + 编码规范 + 禁止事项，~6K tokens）
2. files/CONTEXT.md — 全量读取（当前 sprint 进度 + 流水线状态 + 已知问题 + 待确认决策，~5K tokens）
3. files/INTERFACES.md — 只读 §1 数据结构（SummaryContext 等）（其余跳过，节约上下文空间）
4. docs/self_evolution_design.md — 只读 第一章：系统概述, §3.2 存储设计 + §3.3 三层记忆

📊 上下文预算：文档 ~20K + 源码 ~5K + 产出 ~20K + 执行 ~8K = ~53K tokens (26%) 🟢

【任务】流水线 D / 持久化存储层 — Part A（数据模型 + 核心存储）
【所属】Wave 1（D-1a 和 D-1b 串行，D-1a 先做）
【前置】W0-1 对齐确认完成
【子 session 说明】原 D-1 拆为两个子 session，本 session 只做模型和核心存储，不碰 RepoCache

执行步骤：

1. 创建 mcp-server/src/memory/__init__.py

2. 创建 mcp-server/src/memory/models.py：
   - DiagnosisRecord(query, diagnosis_summary, matched_locations, timestamp)
   - QARecord(question, answer_summary, confidence, follow_ups_used, timestamp)
   - AnnotationRecord(content, author, timestamp)
   - ModuleUnderstanding(module_name, diagnoses, qa_history, annotations, view_count, diagnose_count, ask_count, last_accessed)
   - Hotspot(module_name, topic, question_count, typical_questions, suggested_doc)
   - SessionSummary(session_id, timestamp, modules_explored, key_findings, unresolved_questions)
   - InteractionMemory(hotspots, focus_profile, session_summaries)

3. 创建 mcp-server/src/memory/project_memory.py：
   class ProjectMemory:
       存储：~/.codebook/memory/{repo_hash}/
       ├── context.json, understanding.json, interactions.json, glossary.json, meta.json

       方法：
       - store_context(ctx) / get_context() → SummaryContext | None
       - add_diagnosis(module, record) / get_module_understanding(module)
       - add_qa_record(module, record)
       - add_session_summary(summary) / get_hotspots(module=None)
       - get_meta() / update_meta(**kwargs)
       - finalize_session()

   所有 JSON 读写要加 try/except + structlog 日志。
   文件不存在时返回空结构，不报错。

4. 单元测试（至少 8 个用例）：
   - test_project_memory.py：各层记忆的 CRUD
   - 读写一致性、文件不存在降级、并发安全基本检查

⚠️ 本 session 不修改 _repo_cache.py，不做迁移，那是 D-1b 的事。

═══ 质量自检清单（任务完成前逐项确认）═══

□ 1. 代码规范：所有新代码有类型注解 + structlog 日志 + 无 print
□ 2. 测试覆盖：新功能有正常路径 + 至少 1 个异常路径测试
□ 3. 回归验证：cd mcp-server && python -m pytest tests/ -x -q → 记录结果
□ 4. 接口一致：如修改了 tool 输入输出 → INTERFACES.md 已同步更新
□ 5. 错误处理：对外返回 {"status": "error", "error": str, "hint": str}
□ 6. 无硬编码：无 API Key / 模型名 / 绝对路径 硬编码
□ 7. 产出物完整：所有声称的产出文件确实存在且内容完整
□ 8. CONTEXT.md 已更新：追加任务日志（固定格式）
