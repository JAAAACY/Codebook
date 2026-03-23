---
name: codebook-tdd
description: Use when implementing any CodeBook feature or bugfix, before writing implementation code. Enforces RED-GREEN-REFACTOR cycle with CodeBook-specific testing patterns for tree-sitter parsers, CLI installer, and MCP tools.
---

# CodeBook TDD（测试驱动开发）

## 铁律

```
没有失败测试，不写生产代码。
```

先写了代码再补测试？删掉。重来。不保留"参考"。

**违反规则的字面意思，就是违反规则的精神。**

## RED-GREEN-REFACTOR 循环

### RED — 写失败测试

写一个最小测试，描述期望行为。

```python
async def test_free_func_not_marked_as_method(self):
    """class 之后的模块级函数不应被标记为方法。"""
    # ... 创建包含 class + 模块级函数的测试文件
    result = await parse_file(file_info)
    free1 = [f for f in result.functions if f.name == "free_func"][0]
    assert free1.is_method is False
    assert free1.parent_class is None
```

**运行它。确认失败。确认失败原因正确（功能缺失，不是拼写错误）。**

```bash
python -m pytest tests/test_parsers.py::TestAstParser::test_free_func -v
# 期望: FAILED - assert True is False
```

测试直接通过？说明你在测已有行为，重写测试。

### GREEN — 最小实现

写能让测试通过的**最少代码**。不多写。不优化。不"顺手改"。

```bash
python -m pytest tests/test_parsers.py::TestAstParser::test_free_func -v
# 期望: PASSED
```

### REFACTOR — 清理

测试全绿后才能重构。重构不能改变行为。每次重构后重新跑测试。

## CodeBook 特定测试模式

### 模式 1: Tree-sitter 解析器测试

**必须用真实源码文件，不用 mock。**

```python
with tempfile.NamedTemporaryFile(suffix=".swift", mode="w", delete=False) as f:
    f.write('''
struct MyService {
    func doWork() { }
}
func topLevel() { }
''')
    f.flush()
    file_info = FileInfo(path="test.swift", abs_path=f.name, language="swift", ...)
    result = await parse_file(file_info)
os.unlink(f.name)
```

**必须验证的属性：**
- `is_method` / `parent_class` 正确性
- `docstring` 提取
- `params` 列表
- `imports` 模块名
- `calls` 调用链（caller → callee）

### 模式 2: CLI 安装器 Round-Trip 测试

```python
# 写入 → 读回 → 验证一致
_write_toml(tmp_path, test_data)
read_back = _read_toml(tmp_path)
assert read_back["mcp_servers"]["codebook"]["command"] == expected
```

JSON、TOML、YAML 三种格式都要测。

### 模式 3: 多语言支持

新增语言时必须有完整测试覆盖：

```python
async def test_parse_<language>_file(self):
    # 覆盖: class/struct 检测、方法列表、函数参数、
    #        import 提取、调用链追踪、继承关系
```

### 模式 4: Bug 修复必须有回归测试

```
1. 写测试精确复现 bug
2. 运行 → 看到失败（确认复现）
3. 修复
4. 运行 → 看到通过
5. 跑全量回归 → 无破坏
```

## 红旗清单

- 先写了代码再补测试
- 测试第一次就通过了（你在测已有行为）
- 不理解测试为什么失败
- 一次测多个行为
- "手动测过了，不需要自动化"
- "太简单不需要测试"
- "先探索一下，之后再 TDD"（探索完了必须删掉，从 TDD 重来）

**看到以上任何一条：删代码，从 RED 重来。**

## 关联 Skill

- **系统化调试** → `codebook-debugging`：测试意外失败（不理解原因）时，切换到调试流程的 Phase 1 根因调查，不要盲目修改
- **开发工作流** → `codebook-dev-workflow`：TDD 完成后进入 Phase 4 验证 → Phase 5 子代理审查 → Phase 6 交付

## 验证命令

```bash
# 单个测试
python -m pytest tests/test_parsers.py::TestAstParser::test_name -v

# 全量回归
python -m pytest tests/ -v

# 语法检查
python -c "import ast; ast.parse(open('src/parsers/ast_parser.py').read())"
```
