# CodeBook MCP v0.1 真实仓库验证 — 用户视角问题清单

> 验证对象：pallets/flask（91 文件，18411 行）
> 验证日期：2026-03-22

---

## P0 · 影响基本可用性

### 1. 重启即失忆 — 缓存全部丢失

**现象**：用户重启 Claude Desktop 后调 diagnose，返回"请先运行 scan_repo"。
**用户感受**：刚花 15 秒扫描完的仓库，重启就没了，又得重来。
**根因**：`repo_cache` 是纯内存 dict，进程退出即清空。
**建议**：将 SummaryContext 序列化到 `~/.codebook_cache/` 下的 JSON/pickle 文件，启动时自动恢复。scan_repo 可检测仓库未变化时直接复用缓存。

### 2. read_chapter 返回 268K 字符，Claude Desktop 截断

**现象**：read_chapter("src/flask") 返回被保存到临时文件，提示"exceeds maximum allowed tokens"。
**用户感受**：想看 Flask 核心模块的概览，结果什么都没显示出来。
**根因**：src/flask 有 23 个文件、9201 行代码，read_chapter 把所有文件的全部源码都塞进了返回值。
**建议**：
- 返回摘要模式（只含函数签名 + 调用关系），而非完整源码
- 大模块自动拆分为子章节，每次只返回一个子章节
- 加 `max_tokens` 或 `detail_level` 参数让用户控制粒度

---

## P1 · 影响体验质量

### 3. diagnose 中文 query 匹配能力弱

**现象**：query="Flask 的路由注册流程是怎样的？" 时，如果不手动加上英文关键词 "route add_url_rule"，很难匹配到目标函数。
**用户感受**：PM 用中文描述问题，但代码里是英文函数名，query 和代码之间有语言鸿沟。
**根因**：当前关键词匹配是纯字符串 contains，中文词拆分后和英文函数名无法对应。
**建议**：
- 用 docstring 和注释做辅助匹配（很多 Flask 函数有详细 docstring）
- 构建"中文意图 → 英文函数名"的简易映射（如"路由" → route/url_rule/add_url_rule）
- 返回 context 时附上模块的函数列表，让 Claude Desktop 做语义匹配

### 4. diagnose 匹配到无关节点

**现象**：搜 "route add_url_rule" 时，第 5 个匹配结果是 `FlaskProxy`（仅因 file 路径含"flask"得 3 分），还匹配到了 celery 示例里的 `add()` 函数（因"add"关键词）。
**用户感受**：结果里混了不相关的东西，噪音大。
**建议**：
- 函数名完整匹配的权重远高于部分匹配（"add_url_rule" 完整匹配 >> "add" 部分匹配）
- class 节点的匹配阈值应高于 function
- 路径匹配的权重应低于名称匹配

### 5. scan_repo 首次扫描约 15 秒，体验偏慢

**现象**：首次 scan_repo 耗时 14.8s（clone 3.2s + parse 11.5s），第二次有缓存只要 3.8s。
**用户感受**：能接受但有等待感。Flask 只是中型项目，大型项目可能更久。
**建议**：
- 增量解析：只解析变化的文件
- 扫描过程中返回进度信息（已 clone / 正在解析 / 构建图…）

---

## P2 · 可优化项

### 6. 角色系统还是 4 角色（ceo/pm/investor/qa）

**现象**：server.py 的 Role 枚举仍然是 ceo/pm/investor/qa，与已确认的 PM↔Dev 桥接定位不符。
**用户感受**：选择角色时会困惑 — 我是 PM 还是 Dev？为什么有 CEO 和 investor？
**状态**：已识别，排入下个 sprint。

### 7. ask_about 返回原始上下文，未经加工

**现象**：ask_about 返回几千字的原始模块源码 + 一个 guidance prompt，全靠 Claude Desktop 来理解。
**用户感受**：响应可能很慢（Claude 需要处理大量上下文），且回答质量完全取决于 Claude 的推理。
**建议**：
- 在 MCP 侧做预筛选，只返回与 question 相关的函数/类，而非整个模块
- 对超大模块（如 src/flask 的 9201 行），按 question 关键词做初步裁剪

### 8. codegen 无法在 MCP 侧验证

**现象**：codegen 需要 repo_path（本地绝对路径），但 scan_repo 是通过 git URL clone 到缓存目录的，用户不知道缓存路径在哪。
**用户感受**：不知道该填什么路径。
**建议**：
- codegen 自动从 repo_cache 获取 clone 路径，不需要用户手动传
- 或在 scan_repo 的返回结果中暴露 local_path 字段

### 9. 模块健康度标记缺乏解释

**现象**：scan_repo 返回 src/flask 的 health 为 "red"，但没有说明原因。
**用户感受**：看到红色会紧张，但不知道为什么红、该怎么办。
**建议**：health 字段附带 reason（如"9201 行代码，建议拆分"已在 project_overview 里提到，但没关联到模块级别）。

---

## 总结

| 优先级 | 数量 | 关键词 |
|--------|------|--------|
| P0 | 2 | 缓存持久化、大模块截断 |
| P1 | 3 | 中文匹配、噪音过滤、扫描速度 |
| P2 | 4 | 角色重构、上下文裁剪、codegen 路径、健康度 |

**建议下一步优先处理 P0**，因为"重启失忆"和"核心模块看不了"直接阻断用户流程。
