# Task: D-2a — 术语飞轮：TermStore + TermResolver + 行业包
# Wave: W2
# Project: CodeBook (mcp-server/)
# Working Dir: The repo root where files/CLAUDE.md exists

先读取以下文件，建立核心上下文：
1. files/CLAUDE.md — 全量读取（产品定义 + 技术栈约束 + 编码规范 + 禁止事项，~6K tokens）
2. files/CONTEXT.md — 全量读取（当前 sprint 进度 + 流水线状态 + 已知问题 + 待确认决策，~5K tokens）
3. files/INTERFACES.md — 只读 §1 数据结构（SummaryContext 等）（其余跳过，节约上下文空间）
4. docs/self_evolution_design.md — 只读 第二章：术语飞轮

📊 上下文预算：文档 ~18K + 源码 ~8K + 产出 ~18K + 执行 ~8K = ~52K tokens (26%) 🟢

【任务】流水线 D / 术语飞轮 MVP — Part A（核心数据结构 + 解析器 + 行业包）
【所属】Wave 2（D-2a 先做，D-2b 后做）
【前置】D-1b 已完成
【子 session 说明】原 D-2 拆为两个子 session。本 session 做独立模块，不碰 engine.py

额外读取源码：
- mcp-server/src/memory/project_memory.py — 理解 glossary.json 的读写接口

执行步骤：

1. 创建 mcp-server/src/glossary/__init__.py

2. 创建 src/glossary/term_store.py：
   TermEntry(source_term, target_phrase, context, domain, source, confidence, usage_count, created_at, updated_at)
   ProjectGlossary(repo_url)：
   - add_correction(source_term, target_phrase, context)
   - get_all_terms() → list[TermEntry]
   - import_terms(terms, domain)
   - 存储在 ProjectMemory 的 glossary.json 中

3. 创建 src/glossary/term_resolver.py：
   TermResolver(repo_url, project_domain=None)：
   - resolve() → str  # 合并后的术语禁用表文本
   - resolve_as_list() → list[TermEntry]
   - track_usage(term)  # 记录使用
   合并优先级：用户纠正(1.0) > 项目库 > 行业包 > 全局默认

4. 创建 mcp-server/domain_packs/：
   - general.json（从 config_v0.2.json 迁移 11 个映射 + HTTP 注释）
   - fintech.json（15 个金融术语：KYC/AML/settlement/ledger/...）
   - healthcare.json（15 个医疗术语：FHIR/diagnosis/prescription/...）

5. 单元测试（至少 8 个用例）：
   - 优先级合并：用户纠正覆盖行业包
   - 行业包加载
   - 空术语库降级
   - usage tracking

⚠️ 本 session 不修改 engine.py / server.py，那是 D-2b 的事。

═══ 质量自检清单（任务完成前逐项确认）═══

□ 1. 代码规范：所有新代码有类型注解 + structlog 日志 + 无 print
□ 2. 测试覆盖：新功能有正常路径 + 至少 1 个异常路径测试
□ 3. 回归验证：cd mcp-server && python -m pytest tests/ -x -q → 记录结果
□ 4. 接口一致：如修改了 tool 输入输出 → INTERFACES.md 已同步更新
□ 5. 错误处理：对外返回 {"status": "error", "error": str, "hint": str}
□ 6. 无硬编码：无 API Key / 模型名 / 绝对路径 硬编码
□ 7. 产出物完整：所有声称的产出文件确实存在且内容完整
□ 8. CONTEXT.md 已更新：追加任务日志（固定格式）
