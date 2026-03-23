# CodeBook Sprint 2 — 验收操作手册

> **你只需要在 5 个节点介入。其余全自动。**

---

## 快速开始

```bash
cd codebook-tasks

# 全自动模式（验收节点会暂停等你按回车）
./dispatcher.sh all

# 或者逐 Wave 执行（推荐，更可控）
./dispatcher.sh W0
./dispatcher.sh W1
./checkpoint.sh W1      # 验收
./dispatcher.sh W2
./checkpoint.sh W2      # 验收 + 决策
./dispatcher.sh W3
./checkpoint.sh W3      # 验收
./dispatcher.sh W4
./checkpoint.sh W4      # 验收
./dispatcher.sh W5
./dispatcher.sh W6
./checkpoint.sh W6      # 最终验收
```

---

## 5 个验收节点

### 节点 #1: Wave 1 完成后

**你需要做的**：运行 `./checkpoint.sh W1`，确认：
- [ ] 4 个测试仓库已 clone
- [ ] pytest 全绿，0 skip
- [ ] `src/memory/` 目录存在且有 models.py + project_memory.py + migration.py

**预计耗时**：2 分钟看报告

**通过后**：`./dispatcher.sh W2`

---

### 节点 #2: Wave 2 完成后 ⭐ 最重要

**你需要做的**：

1. 运行 `./checkpoint.sh W2`
2. **看压测报告**：`mcp-server/test_results/scan_repo_summary.md`
3. **做两个决策**：
   - **D-001**：增量扫描的 30% 阈值是否合理？大型项目的 scan_time 是否需要增量优化？
   - **D-002**：Mermaid 图在大型项目上可读性评分如何？需要分层展示吗？
4. **看角色设计**：`docs/role_system_v3_design.md` — 三视图设计是否符合你的预期？
5. **看术语飞轮**：试跑 term_correct 确认纠正→生效链路

**预计耗时**：15-30 分钟（这是最重要的验收节点）

**通过后**：如果 D-001/D-002 有调整，更新 CONTEXT.md 后再 `./dispatcher.sh W3`

---

### 节点 #3: Wave 3 完成后

**你需要做的**：运行 `./checkpoint.sh W3`，确认：
- [ ] diagnose 命中率 ≥ 80%（看 test_results 中的抽查结果）
- [ ] 角色系统 PM 视角 ≥ 9.0/10
- [ ] 记忆持久化可用（重启后诊断结果保留）

**预计耗时**：5-10 分钟

**通过后**：`./dispatcher.sh W4`

---

### 节点 #4: Wave 4 完成后

**你需要做的**：运行 `./checkpoint.sh W4`，确认：
- [ ] codegen diff_valid ≥ 90%
- [ ] CI Pipeline 存在且语法正确
- [ ] 增量扫描可用

**预计耗时**：5 分钟

**通过后**：`./dispatcher.sh W5 && ./dispatcher.sh W6`（W5 轻量，可以一起跑）

---

### 节点 #5: Wave 6 完成后（最终验收）

**你需要做的**：运行 `./checkpoint.sh W6`，确认全部 18 项验收指标。

**预计耗时**：10 分钟

---

## 工具命令

```bash
# 查看当前进度
./dispatcher.sh status

# 查看某个任务的完整日志
cat logs/D-1a.log

# 重跑某个失败的任务（先清除完成标记）
rm .locks/D-1a.done
./dispatcher.sh W1    # 会跳过已完成的，只跑未完成的

# 全部重置
./dispatcher.sh reset
```

---

## 故障排除

**任务失败了怎么办？**
1. 看日志：`cat logs/{task_id}.log`
2. 日志末尾通常有错误原因
3. 修复后删除 lock：`rm .locks/{task_id}.done`
4. 重新运行对应 Wave

**想修改某个任务的 Prompt？**
直接编辑 `prompts/{task_id}.md`，然后重跑。

**并行任务中一个失败了？**
dispatcher 会报告哪个失败。成功的不需要重跑（有 .done lock）。修复失败的那个后重新运行 Wave 即可。
