# Blueprint v2 Phase 1: LLM 摘要管线 + 蓝图数据模型

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Codebook 的蓝图输出包含业务语言的模块名、功能说明和函数逻辑解释，替代当前的代码目录名和技术统计。

**Architecture:** 新增 `summarize_for_blueprint` MCP 工具，遵循现有 MCP 架构（Server 组装上下文 → 宿主 LLM 推理 → 结果通过 `save_blueprint_summary` 工具回写缓存）。同时实现基于规则的降级方案，LLM 不可用时自动回退。蓝图数据模型新增 `business_name`、`business_description`、`function_explanations` 等字段。

**Tech Stack:** Python 3.10+, MCP SDK (FastMCP), NetworkX, structlog

**关键设计决策：** Codebook 不直接调用 LLM API。所有 LLM 推理都由 MCP 宿主（Claude Desktop）完成。因此 LLM 摘要分两步：(1) `summarize_for_blueprint` 工具返回结构化上下文+提示词给宿主；(2) 宿主推理完成后调用 `save_blueprint_summary` 工具回写结果。

---

### 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/summarizer/business_namer.py` | 新建 | 基于规则的降级命名（目录名→业务名映射） |
| `src/summarizer/blueprint_summary.py` | 新建 | 组装 LLM 摘要上下文 + 解析 LLM 返回结果 |
| `src/tools/summarize_for_blueprint.py` | 新建 | MCP 工具：返回摘要上下文给宿主 |
| `src/tools/save_blueprint_summary.py` | 新建 | MCP 工具：接收宿主 LLM 的摘要结果并缓存 |
| `src/server.py` | 修改 | 注册两个新 MCP 工具 |
| `src/tools/codebook_explore.py` | 修改 | 在 Phase 1 scan 后调用摘要管线 |
| `src/tools/_repo_cache.py` | 修改 | 缓存增加 blueprint_summary 字段 |
| `tests/test_business_namer.py` | 新建 | 降级命名测试 |
| `tests/test_blueprint_summary.py` | 新建 | 摘要数据结构和组装测试 |
| `tests/test_summarize_tools.py` | 新建 | MCP 工具注册和返回格式测试 |

---

### Task 1: 基于规则的降级命名器

**Files:**
- Create: `src/summarizer/business_namer.py`
- Test: `tests/test_business_namer.py`

- [ ] **Step 1: 写失败测试 — 目录名到业务名映射**

```python
# tests/test_business_namer.py
"""business_namer 降级命名测试。"""

import pytest
from src.summarizer.business_namer import (
    infer_business_name,
    infer_business_description,
    infer_function_explanation,
    infer_connection_verb,
)


class TestInferBusinessName:
    def test_auth_module(self):
        assert infer_business_name("src/auth") == "认证系统"

    def test_plugins_module(self):
        assert infer_business_name("rust/crates/plugins") == "插件系统"

    def test_api_module(self):
        assert infer_business_name("rust/crates/api") == "API 接口"

    def test_database_module(self):
        assert infer_business_name("src/db") == "数据库"

    def test_unknown_module(self):
        """未知模块应返回目录名的中文化版本。"""
        result = infer_business_name("src/foobar")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_nested_path_uses_leaf(self):
        """应使用路径最后一级做推断。"""
        assert infer_business_name("rust/crates/runtime") == "运行时引擎"

    def test_cli_module(self):
        assert infer_business_name("src/cli") == "命令行工具"


class TestInferBusinessDescription:
    def test_with_functions_and_classes(self):
        desc = infer_business_description(
            module_name="src/auth",
            function_names=["login", "logout", "verify_token"],
            class_names=["UserSession", "AuthMiddleware"],
            file_count=5,
            line_count=800,
        )
        assert isinstance(desc, str)
        assert len(desc) > 10

    def test_empty_module(self):
        desc = infer_business_description(
            module_name="src/utils",
            function_names=[],
            class_names=[],
            file_count=1,
            line_count=20,
        )
        assert isinstance(desc, str)


class TestInferFunctionExplanation:
    def test_check_permission(self):
        explanation = infer_function_explanation(
            func_name="check_permission",
            params=["user_id", "action"],
            return_type="bool",
            docstring=None,
        )
        assert isinstance(explanation, str)
        assert len(explanation) > 5

    def test_with_docstring(self):
        """有 docstring 时应优先使用。"""
        explanation = infer_function_explanation(
            func_name="foo",
            params=[],
            return_type=None,
            docstring="Validate user input and return sanitized result",
        )
        assert "validate" in explanation.lower() or "验证" in explanation


class TestInferConnectionVerb:
    def test_call_relationship(self):
        verb = infer_connection_verb(
            from_module="src/server",
            to_module="src/auth",
            call_count=5,
        )
        assert isinstance(verb, str)
        assert len(verb) > 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/jacky/Codebook/mcp-server && python3 -m pytest tests/test_business_namer.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.summarizer.business_namer'"

- [ ] **Step 3: 实现降级命名器**

```python
# src/summarizer/business_namer.py
"""business_namer — 基于规则的业务命名降级方案。

当 LLM 不可用时，从代码目录名、函数名、类名推断业务语义。
质量低于 LLM 但保证可用。
"""

from __future__ import annotations

# 目录名关键词 → 业务名映射
_KEYWORD_MAP: dict[str, str] = {
    "auth": "认证系统",
    "login": "登录系统",
    "user": "用户管理",
    "permission": "权限控制",
    "permissions": "权限控制",
    "plugin": "插件系统",
    "plugins": "插件系统",
    "api": "API 接口",
    "server": "服务端",
    "client": "客户端",
    "cli": "命令行工具",
    "cmd": "命令行工具",
    "commands": "命令系统",
    "db": "数据库",
    "database": "数据库",
    "models": "数据模型",
    "schema": "数据结构",
    "schemas": "数据结构",
    "config": "配置管理",
    "settings": "配置管理",
    "runtime": "运行时引擎",
    "engine": "核心引擎",
    "core": "核心模块",
    "tools": "工具集",
    "utils": "工具函数",
    "helpers": "辅助函数",
    "middleware": "中间件",
    "router": "路由系统",
    "routes": "路由系统",
    "views": "视图层",
    "controllers": "控制器",
    "services": "业务服务",
    "handlers": "请求处理",
    "tests": "测试",
    "test": "测试",
    "migrations": "数据库迁移",
    "static": "静态资源",
    "templates": "模板",
    "components": "组件",
    "hooks": "钩子系统",
    "events": "事件系统",
    "queue": "消息队列",
    "cache": "缓存系统",
    "storage": "存储系统",
    "file": "文件管理",
    "files": "文件管理",
    "upload": "上传服务",
    "download": "下载服务",
    "notification": "通知系统",
    "notifications": "通知系统",
    "email": "邮件服务",
    "log": "日志系统",
    "logging": "日志系统",
    "monitor": "监控系统",
    "metrics": "指标系统",
    "telemetry": "遥测系统",
    "search": "搜索系统",
    "payment": "支付系统",
    "billing": "计费系统",
    "report": "报表系统",
    "export": "导出功能",
    "import": "导入功能",
    "sync": "同步服务",
    "bridge": "桥接层",
    "proxy": "代理层",
    "gateway": "网关",
    "compat": "兼容层",
    "parsers": "解析器",
    "parser": "解析器",
    "state": "状态管理",
    "store": "数据存储",
    "memory": "内存管理",
    "bootstrap": "启动引导",
    "init": "初始化",
    "setup": "安装配置",
    "voice": "语音功能",
    "assistant": "助手功能",
    "coordinator": "协调器",
    "screens": "页面",
    "remote": "远程服务",
    "native": "原生模块",
    "crates": "核心代码库",
    "scripts": "脚本工具",
}

# 函数名前缀 → 动作描述
_FUNC_PREFIX_MAP: dict[str, str] = {
    "get": "获取",
    "set": "设置",
    "create": "创建",
    "add": "添加",
    "update": "更新",
    "delete": "删除",
    "remove": "移除",
    "check": "检查",
    "verify": "验证",
    "validate": "校验",
    "parse": "解析",
    "build": "构建",
    "render": "渲染",
    "send": "发送",
    "receive": "接收",
    "load": "加载",
    "save": "保存",
    "init": "初始化",
    "start": "启动",
    "stop": "停止",
    "run": "执行",
    "process": "处理",
    "handle": "处理",
    "convert": "转换",
    "format": "格式化",
    "filter": "过滤",
    "sort": "排序",
    "search": "搜索",
    "find": "查找",
    "connect": "连接",
    "disconnect": "断开",
    "register": "注册",
    "unregister": "注销",
    "login": "登录",
    "logout": "登出",
    "auth": "认证",
    "encrypt": "加密",
    "decrypt": "解密",
    "hash": "哈希",
    "compress": "压缩",
    "decompress": "解压",
    "upload": "上传",
    "download": "下载",
    "read": "读取",
    "write": "写入",
    "open": "打开",
    "close": "关闭",
    "emit": "发出",
    "listen": "监听",
    "subscribe": "订阅",
    "publish": "发布",
    "notify": "通知",
    "log": "记录",
    "track": "追踪",
    "measure": "度量",
    "test": "测试",
    "mock": "模拟",
    "assert": "断言",
}


def infer_business_name(module_path: str) -> str:
    """从模块路径推断业务名称。

    Args:
        module_path: 模块目录路径（如 'src/auth', 'rust/crates/plugins'）。

    Returns:
        中文业务名称。
    """
    # 取路径最后一级
    leaf = module_path.rstrip("/").split("/")[-1].lower()
    leaf = leaf.replace("-", "_").replace(".", "_")

    # 精确匹配
    if leaf in _KEYWORD_MAP:
        return _KEYWORD_MAP[leaf]

    # 部分匹配（关键词出现在名称中）
    for keyword, name in _KEYWORD_MAP.items():
        if keyword in leaf:
            return name

    # 下划线拆分尝试匹配
    parts = leaf.split("_")
    for part in parts:
        if part in _KEYWORD_MAP:
            return _KEYWORD_MAP[part]

    # 无法推断，返回原名（首字母大写）
    return leaf.replace("_", " ").title()


def infer_business_description(
    module_name: str,
    function_names: list[str],
    class_names: list[str],
    file_count: int,
    line_count: int,
) -> str:
    """从模块元数据推断业务描述。

    Args:
        module_name: 模块路径名。
        function_names: 模块内公开函数名列表。
        class_names: 模块内类名列表。
        file_count: 文件数。
        line_count: 代码行数。

    Returns:
        一句话业务描述。
    """
    biz_name = infer_business_name(module_name)

    # 从函数名推断核心动作
    actions = []
    for fn in function_names[:10]:
        fn_lower = fn.lower()
        for prefix, action in _FUNC_PREFIX_MAP.items():
            if fn_lower.startswith(prefix):
                if action not in actions:
                    actions.append(action)
                break

    if actions:
        action_str = "、".join(actions[:4])
        return f"负责{action_str}等操作，包含 {file_count} 个文件"
    elif class_names:
        class_str = "、".join(class_names[:3])
        return f"定义了 {class_str} 等核心类，包含 {file_count} 个文件"
    else:
        return f"包含 {file_count} 个文件、{line_count} 行代码"


def infer_function_explanation(
    func_name: str,
    params: list[str],
    return_type: str | None,
    docstring: str | None,
) -> str:
    """从函数签名推断实现逻辑解释。

    Args:
        func_name: 函数名。
        params: 参数名列表。
        return_type: 返回类型。
        docstring: 文档字符串。

    Returns:
        业务语言的实现逻辑解释。
    """
    # 优先使用 docstring
    if docstring and len(docstring.strip()) > 5:
        # 取第一句
        first_line = docstring.strip().split("\n")[0].strip().rstrip(".")
        return first_line

    # 从函数名推断
    fn_lower = func_name.lower()
    action = ""
    for prefix, act in _FUNC_PREFIX_MAP.items():
        if fn_lower.startswith(prefix):
            action = act
            remainder = fn_lower[len(prefix):].strip("_")
            break
    else:
        action = "处理"
        remainder = fn_lower

    # 参数信息
    param_hint = ""
    if params:
        filtered = [p for p in params if p not in ("self", "cls", "ctx", "context")]
        if filtered:
            param_hint = f"，接收 {', '.join(filtered[:3])} 作为输入"

    # 返回值信息
    return_hint = ""
    if return_type and return_type not in ("None", "void", "()"):
        return_hint = f"，返回 {return_type}"

    # 组装
    subject = remainder.replace("_", " ") if remainder else func_name
    return f"{action} {subject}{param_hint}{return_hint}"


def infer_connection_verb(
    from_module: str,
    to_module: str,
    call_count: int,
) -> str:
    """推断模块间连线的动词标注。

    Args:
        from_module: 调用方模块。
        to_module: 被调方模块。
        call_count: 调用次数。

    Returns:
        动词标注（如「调用」「读取」「发送」）。
    """
    to_leaf = to_module.rstrip("/").split("/")[-1].lower()

    if "db" in to_leaf or "database" in to_leaf or "store" in to_leaf:
        return "读写数据"
    if "auth" in to_leaf or "permission" in to_leaf:
        return "验证权限"
    if "cache" in to_leaf:
        return "读取缓存"
    if "queue" in to_leaf or "event" in to_leaf:
        return "发送消息"
    if "log" in to_leaf or "telemetry" in to_leaf or "monitor" in to_leaf:
        return "上报数据"
    if "config" in to_leaf or "settings" in to_leaf:
        return "读取配置"
    if "api" in to_leaf or "server" in to_leaf:
        return "请求服务"

    if call_count >= 10:
        return "频繁调用"
    return "调用"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/jacky/Codebook/mcp-server && python3 -m pytest tests/test_business_namer.py -v`
Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/jacky/Codebook
git add mcp-server/src/summarizer/business_namer.py mcp-server/tests/test_business_namer.py
git commit -m "feat: add rule-based business namer for blueprint v2 fallback"
```

---

### Task 2: 蓝图摘要数据模型 + LLM 上下文组装

**Files:**
- Create: `src/summarizer/blueprint_summary.py`
- Test: `tests/test_blueprint_summary.py`

- [ ] **Step 1: 写失败测试 — 数据模型和上下文组装**

```python
# tests/test_blueprint_summary.py
"""blueprint_summary 数据模型和上下文组装测试。"""

import pytest
from src.summarizer.blueprint_summary import (
    BlueprintSummary,
    ModuleSummary,
    FunctionSummary,
    ConnectionSummary,
    build_summary_context,
    build_fallback_summary,
    parse_llm_response,
)
from src.parsers.ast_parser import ParseResult, FunctionInfo, ClassInfo, ImportInfo, CallInfo
from src.parsers.repo_cloner import FileInfo, CloneResult
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import ModuleGroup
from src.summarizer.engine import SummaryContext


def _make_test_context() -> SummaryContext:
    """构造测试用 SummaryContext。"""
    parse_results = [
        ParseResult(
            file_path="src/auth/login.py",
            language="python",
            functions=[
                FunctionInfo(
                    name="check_permission",
                    params=["user_id", "action"],
                    return_type="bool",
                    line_start=10,
                    line_end=25,
                    is_method=False,
                    parent_class=None,
                    docstring="Check if user has permission to perform action.",
                ),
                FunctionInfo(
                    name="create_session",
                    params=["user"],
                    return_type="Session",
                    line_start=30,
                    line_end=50,
                    is_method=False,
                    parent_class=None,
                ),
            ],
            classes=[ClassInfo(name="AuthManager", line_start=1, line_end=80)],
            imports=[ImportInfo(module="src.db", names=["query"])],
            calls=[CallInfo(callee_name="query", caller_func="check_permission")],
            line_count=80,
        ),
        ParseResult(
            file_path="src/db/store.py",
            language="python",
            functions=[
                FunctionInfo(name="query", params=["sql"], return_type="list", line_start=5, line_end=20, is_method=False, parent_class=None),
            ],
            classes=[],
            imports=[],
            calls=[],
            line_count=20,
        ),
    ]

    clone_result = CloneResult(
        repo_path="/repo",
        files=[
            FileInfo(path="src/auth/login.py", abs_path="/repo/src/auth/login.py", language="python", size_bytes=2000, line_count=80),
            FileInfo(path="src/db/store.py", abs_path="/repo/src/db/store.py", language="python", size_bytes=500, line_count=20),
        ],
        languages={"python": 2},
        total_lines=100,
    )

    modules = [
        ModuleGroup(name="src/auth", dir_path="src/auth", files=["src/auth/login.py"], is_special=False, total_lines=80),
        ModuleGroup(name="src/db", dir_path="src/db", files=["src/db/store.py"], is_special=False, total_lines=20),
    ]

    dep_graph = DependencyGraph()
    dep_graph.build(parse_results)
    module_map = {}
    for node_id, data in dep_graph.graph.nodes(data=True):
        f = data.get("file", "")
        if "auth" in f:
            module_map[node_id] = "src/auth"
        elif "db" in f:
            module_map[node_id] = "src/db"
    dep_graph.set_module_groups(module_map)

    return SummaryContext(
        clone_result=clone_result,
        parse_results=parse_results,
        modules=modules,
        dep_graph=dep_graph,
        role="pm",
        repo_url="https://github.com/test/repo",
    )


class TestBlueprintSummaryDataModel:
    def test_function_summary_fields(self):
        fs = FunctionSummary(
            code_name="check_permission",
            business_name="验证用户权限",
            explanation="检查用户是否有执行该操作的权限",
            file_path="src/auth/login.py",
            line_start=10,
            params=["user_id", "action"],
            return_type="bool",
        )
        assert fs.code_name == "check_permission"
        assert fs.business_name == "验证用户权限"

    def test_module_summary_fields(self):
        ms = ModuleSummary(
            code_path="src/auth",
            business_name="认证系统",
            description="管理用户登录、权限验证和会话管理",
            health="green",
            functions=[],
            depends_on=[],
            used_by=[],
        )
        assert ms.business_name == "认证系统"

    def test_blueprint_summary_fields(self):
        bs = BlueprintSummary(
            project_name="测试项目",
            project_description="一个用于测试的 Python 项目",
            modules=[],
            connections=[],
        )
        assert bs.project_name == "测试项目"


class TestBuildFallbackSummary:
    def test_produces_valid_summary(self):
        ctx = _make_test_context()
        summary = build_fallback_summary(ctx)

        assert isinstance(summary, BlueprintSummary)
        assert len(summary.modules) == 2
        assert summary.modules[0].business_name == "认证系统"
        assert summary.modules[1].business_name == "数据库"

    def test_functions_have_explanations(self):
        ctx = _make_test_context()
        summary = build_fallback_summary(ctx)

        auth_module = next(m for m in summary.modules if m.code_path == "src/auth")
        assert len(auth_module.functions) > 0
        for fn in auth_module.functions:
            assert fn.explanation != ""
            assert fn.business_name != ""

    def test_connections_have_verbs(self):
        ctx = _make_test_context()
        summary = build_fallback_summary(ctx)

        if summary.connections:
            for conn in summary.connections:
                assert conn.verb != ""


class TestBuildSummaryContext:
    def test_returns_context_dict(self):
        ctx = _make_test_context()
        result = build_summary_context(ctx)

        assert "modules" in result
        assert "prompt" in result
        assert isinstance(result["prompt"], str)
        assert len(result["prompt"]) > 100

    def test_context_contains_module_data(self):
        ctx = _make_test_context()
        result = build_summary_context(ctx)

        assert len(result["modules"]) == 2
        for mod in result["modules"]:
            assert "name" in mod
            assert "functions" in mod
            assert "classes" in mod


class TestParseLlmResponse:
    def test_valid_json_response(self):
        response = {
            "project_name": "认证服务",
            "project_description": "提供用户认证和权限管理",
            "modules": [
                {
                    "code_path": "src/auth",
                    "business_name": "认证系统",
                    "description": "管理用户登录和权限验证",
                    "functions": [
                        {
                            "code_name": "check_permission",
                            "business_name": "验证权限",
                            "explanation": "检查用户是否有权限执行操作",
                        }
                    ],
                }
            ],
            "connections": [
                {
                    "from": "src/auth",
                    "to": "src/db",
                    "verb": "查询数据",
                }
            ],
        }
        ctx = _make_test_context()
        summary = parse_llm_response(response, ctx)

        assert isinstance(summary, BlueprintSummary)
        assert summary.project_name == "认证服务"
        assert len(summary.modules) >= 1

    def test_invalid_response_returns_fallback(self):
        ctx = _make_test_context()
        summary = parse_llm_response({"invalid": "data"}, ctx)

        # 应返回降级结果而非崩溃
        assert isinstance(summary, BlueprintSummary)
        assert len(summary.modules) > 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/jacky/Codebook/mcp-server && python3 -m pytest tests/test_blueprint_summary.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 实现蓝图摘要数据模型 + 上下文组装**

```python
# src/summarizer/blueprint_summary.py
"""blueprint_summary — 蓝图摘要数据模型和 LLM 上下文组装。

定义 Blueprint v2 的核心数据结构，
提供 LLM 上下文组装和降级方案。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

import structlog

from src.summarizer.business_namer import (
    infer_business_name,
    infer_business_description,
    infer_function_explanation,
    infer_connection_verb,
)

logger = structlog.get_logger()


@dataclass
class FunctionSummary:
    """函数级摘要。"""
    code_name: str
    business_name: str
    explanation: str
    file_path: str = ""
    line_start: int = 0
    params: list[str] = field(default_factory=list)
    return_type: str | None = None


@dataclass
class ConnectionSummary:
    """模块间连接。"""
    from_module: str
    to_module: str
    verb: str
    call_count: int = 1


@dataclass
class ModuleSummary:
    """模块级摘要。"""
    code_path: str
    business_name: str
    description: str
    health: str = "green"
    functions: list[FunctionSummary] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    used_by: list[str] = field(default_factory=list)


@dataclass
class BlueprintSummary:
    """完整蓝图摘要。"""
    project_name: str
    project_description: str
    modules: list[ModuleSummary] = field(default_factory=list)
    connections: list[ConnectionSummary] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_fallback_summary(ctx: "SummaryContext") -> BlueprintSummary:
    """基于规则生成降级摘要（不调用 LLM）。

    Args:
        ctx: SummaryContext（来自 scan_repo）。

    Returns:
        BlueprintSummary，使用规则推断的业务名称。
    """
    from src.parsers.dependency_graph import DependencyGraph

    mg = ctx.dep_graph.get_module_graph()

    # 项目名
    repo_url = ctx.repo_url or ""
    if "/" in repo_url:
        project_name = repo_url.rstrip("/").split("/")[-1]
    else:
        project_name = "项目"

    # 语言信息
    langs = ctx.clone_result.languages
    primary_lang = max(langs, key=langs.get) if langs else "未知"
    project_desc = (
        f"基于 {primary_lang} 的项目，"
        f"包含 {len(ctx.clone_result.files)} 个文件、"
        f"{ctx.clone_result.total_lines} 行代码"
    )

    # 模块摘要
    modules: list[ModuleSummary] = []
    for m in ctx.modules:
        if m.is_special:
            continue

        # 收集模块内的函数信息
        module_files = set(m.files)
        func_names: list[str] = []
        class_names: list[str] = []
        func_summaries: list[FunctionSummary] = []

        for pr in ctx.parse_results:
            if pr.file_path not in module_files:
                continue
            for fn in pr.functions:
                if fn.name.startswith("_") or fn.name == "<module>":
                    continue
                func_names.append(fn.name)
                func_summaries.append(FunctionSummary(
                    code_name=fn.name,
                    business_name=infer_function_explanation(
                        fn.name, fn.params, fn.return_type, fn.docstring,
                    ).split("，")[0],  # 取第一部分做名称
                    explanation=infer_function_explanation(
                        fn.name, fn.params, fn.return_type, fn.docstring,
                    ),
                    file_path=pr.file_path,
                    line_start=fn.line_start,
                    params=fn.params,
                    return_type=fn.return_type,
                ))
            for cls in pr.classes:
                class_names.append(cls.name)

        # 健康度
        if m.total_lines > 3000:
            health = "red"
        elif m.total_lines > 1000:
            health = "yellow"
        else:
            health = "green"

        depends_on = list(mg.predecessors(m.name)) if m.name in mg else []
        used_by = list(mg.successors(m.name)) if m.name in mg else []

        modules.append(ModuleSummary(
            code_path=m.name,
            business_name=infer_business_name(m.name),
            description=infer_business_description(
                m.name, func_names, class_names, len(m.files), m.total_lines,
            ),
            health=health,
            functions=func_summaries,
            depends_on=depends_on,
            used_by=used_by,
        ))

    # 连接
    connections: list[ConnectionSummary] = []
    for u, v, data in mg.edges(data=True):
        connections.append(ConnectionSummary(
            from_module=u,
            to_module=v,
            verb=infer_connection_verb(u, v, data.get("call_count", 1)),
            call_count=data.get("call_count", 1),
        ))

    return BlueprintSummary(
        project_name=project_name,
        project_description=project_desc,
        modules=modules,
        connections=connections,
    )


def build_summary_context(ctx: "SummaryContext") -> dict[str, Any]:
    """组装 LLM 摘要上下文，供 MCP 宿主推理。

    Args:
        ctx: SummaryContext。

    Returns:
        {"modules": [...], "connections": [...], "prompt": str}
        宿主 LLM 根据 prompt 和数据生成 BlueprintSummary JSON。
    """
    mg = ctx.dep_graph.get_module_graph()

    modules_data = []
    for m in ctx.modules:
        if m.is_special:
            continue

        module_files = set(m.files)
        functions = []
        classes = []

        for pr in ctx.parse_results:
            if pr.file_path not in module_files:
                continue
            for fn in pr.functions:
                if fn.name.startswith("_") or fn.name == "<module>":
                    continue
                functions.append({
                    "name": fn.name,
                    "params": fn.params,
                    "return_type": fn.return_type,
                    "docstring": fn.docstring or "",
                    "file": pr.file_path,
                    "line": fn.line_start,
                })
            for cls in pr.classes:
                classes.append({
                    "name": cls.name,
                    "methods": cls.methods,
                })

        depends_on = list(mg.predecessors(m.name)) if m.name in mg else []
        used_by = list(mg.successors(m.name)) if m.name in mg else []

        modules_data.append({
            "name": m.name,
            "files": m.files,
            "file_count": len(m.files),
            "line_count": m.total_lines,
            "functions": functions,
            "classes": classes,
            "depends_on": depends_on,
            "used_by": used_by,
        })

    connections_data = []
    for u, v, data in mg.edges(data=True):
        connections_data.append({
            "from": u,
            "to": v,
            "call_count": data.get("call_count", 1),
        })

    prompt = (
        "你是一个代码分析专家。请用简洁的中文为以下项目的每个模块和函数生成业务语言描述。\n"
        "目标读者是不会写代码的产品经理。\n\n"
        "请返回以下 JSON 格式：\n"
        "{\n"
        '  "project_name": "项目的中文业务名称",\n'
        '  "project_description": "一句话项目描述",\n'
        '  "modules": [\n'
        "    {\n"
        '      "code_path": "模块路径（保持原样）",\n'
        '      "business_name": "中文业务名称",\n'
        '      "description": "一句话功能描述",\n'
        '      "functions": [\n'
        "        {\n"
        '          "code_name": "函数名（保持原样）",\n'
        '          "business_name": "中文名称（做什么）",\n'
        '          "explanation": "实现逻辑解释（怎么做，2-3句话）"\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ],\n"
        '  "connections": [\n'
        "    {\n"
        '      "from": "调用方模块路径",\n'
        '      "to": "被调方模块路径",\n'
        '      "verb": "动词（如：调用、读取数据、验证权限）"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "以下是项目的代码结构数据：\n"
    )

    return {
        "modules": modules_data,
        "connections": connections_data,
        "prompt": prompt,
    }


def parse_llm_response(
    response: dict[str, Any],
    ctx: "SummaryContext",
) -> BlueprintSummary:
    """解析 LLM 返回的摘要 JSON，失败时返回降级结果。

    Args:
        response: LLM 返回的 JSON dict。
        ctx: SummaryContext（用于降级）。

    Returns:
        BlueprintSummary。
    """
    try:
        project_name = response.get("project_name", "")
        project_desc = response.get("project_description", "")

        if not project_name or "modules" not in response:
            raise ValueError("LLM 响应缺少必要字段")

        modules = []
        for mod_data in response.get("modules", []):
            functions = []
            for fn_data in mod_data.get("functions", []):
                functions.append(FunctionSummary(
                    code_name=fn_data.get("code_name", ""),
                    business_name=fn_data.get("business_name", ""),
                    explanation=fn_data.get("explanation", ""),
                ))

            modules.append(ModuleSummary(
                code_path=mod_data.get("code_path", ""),
                business_name=mod_data.get("business_name", ""),
                description=mod_data.get("description", ""),
                functions=functions,
            ))

        connections = []
        for conn_data in response.get("connections", []):
            connections.append(ConnectionSummary(
                from_module=conn_data.get("from", ""),
                to_module=conn_data.get("to", ""),
                verb=conn_data.get("verb", "调用"),
            ))

        return BlueprintSummary(
            project_name=project_name,
            project_description=project_desc,
            modules=modules,
            connections=connections,
        )

    except Exception as e:
        logger.warning("blueprint_summary.parse_failed", error=str(e))
        return build_fallback_summary(ctx)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/jacky/Codebook/mcp-server && python3 -m pytest tests/test_blueprint_summary.py -v`
Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/jacky/Codebook
git add mcp-server/src/summarizer/blueprint_summary.py mcp-server/tests/test_blueprint_summary.py
git commit -m "feat: blueprint summary data model with LLM context assembly and fallback"
```

---

### Task 3: MCP 工具注册 — summarize_for_blueprint + save_blueprint_summary

**Files:**
- Create: `src/tools/summarize_for_blueprint.py`
- Create: `src/tools/save_blueprint_summary.py`
- Modify: `src/server.py`
- Modify: `src/tools/_repo_cache.py`
- Test: `tests/test_summarize_tools.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_summarize_tools.py
"""summarize_for_blueprint 和 save_blueprint_summary 工具测试。"""

import pytest
from unittest.mock import patch, MagicMock


class TestMCPToolRegistration:
    def test_summarize_tool_registered(self):
        from src.server import mcp
        tools = mcp._tool_manager._tools
        assert "summarize_for_blueprint" in tools

    def test_save_summary_tool_registered(self):
        from src.server import mcp
        tools = mcp._tool_manager._tools
        assert "save_blueprint_summary" in tools


class TestSummarizeForBlueprint:
    @pytest.mark.asyncio
    async def test_returns_context_when_cached(self):
        from src.tools.summarize_for_blueprint import summarize_for_blueprint

        # 模拟 repo_cache 有数据
        mock_ctx = MagicMock()
        mock_ctx.modules = []
        mock_ctx.parse_results = []
        mock_ctx.clone_result.languages = {"python": 1}
        mock_ctx.clone_result.files = []
        mock_ctx.clone_result.total_lines = 100
        mock_ctx.dep_graph.get_module_graph.return_value = MagicMock(
            edges=MagicMock(return_value=[]),
        )
        mock_ctx.repo_url = "https://test.com/repo"

        with patch("src.tools.summarize_for_blueprint.repo_cache") as mock_cache:
            mock_cache.get.return_value = mock_ctx
            result = await summarize_for_blueprint("https://test.com/repo")

        assert result["status"] == "context_ready"
        assert "prompt" in result
        assert "modules" in result

    @pytest.mark.asyncio
    async def test_returns_error_when_not_scanned(self):
        from src.tools.summarize_for_blueprint import summarize_for_blueprint

        with patch("src.tools.summarize_for_blueprint.repo_cache") as mock_cache:
            mock_cache.get.return_value = None
            result = await summarize_for_blueprint("https://test.com/nonexist")

        assert result["status"] == "error"


class TestSaveBlueprintSummary:
    @pytest.mark.asyncio
    async def test_saves_valid_summary(self):
        from src.tools.save_blueprint_summary import save_blueprint_summary

        summary_json = {
            "project_name": "测试",
            "project_description": "测试项目",
            "modules": [],
            "connections": [],
        }

        with patch("src.tools.save_blueprint_summary.repo_cache") as mock_cache, \
             patch("src.tools.save_blueprint_summary._save_to_memory") as mock_save:
            mock_cache.get.return_value = MagicMock()
            result = await save_blueprint_summary("https://test.com/repo", summary_json)

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_falls_back_on_invalid_json(self):
        from src.tools.save_blueprint_summary import save_blueprint_summary

        with patch("src.tools.save_blueprint_summary.repo_cache") as mock_cache:
            mock_ctx = MagicMock()
            mock_ctx.modules = []
            mock_ctx.parse_results = []
            mock_ctx.clone_result.languages = {"python": 1}
            mock_ctx.clone_result.files = []
            mock_ctx.clone_result.total_lines = 0
            mock_ctx.dep_graph.get_module_graph.return_value = MagicMock(
                edges=MagicMock(return_value=[]),
            )
            mock_ctx.repo_url = "https://test.com/repo"
            mock_cache.get.return_value = mock_ctx

            with patch("src.tools.save_blueprint_summary._save_to_memory"):
                result = await save_blueprint_summary("https://test.com/repo", {"bad": "data"})

        # 降级成功，不崩溃
        assert result["status"] == "ok"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/jacky/Codebook/mcp-server && python3 -m pytest tests/test_summarize_tools.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 summarize_for_blueprint 工具**

```python
# src/tools/summarize_for_blueprint.py
"""summarize_for_blueprint — 返回模块结构上下文供宿主 LLM 生成业务摘要。

MCP 工具。扫描完成后调用，返回结构化数据 + 提示词。
宿主 LLM 推理后应调用 save_blueprint_summary 回写结果。
"""

from __future__ import annotations

from typing import Any

import structlog

from src.tools._repo_cache import repo_cache
from src.summarizer.blueprint_summary import build_summary_context, build_fallback_summary

logger = structlog.get_logger()


async def summarize_for_blueprint(repo_url: str) -> dict[str, Any]:
    """组装蓝图摘要上下文，供宿主 LLM 推理。

    Args:
        repo_url: 已扫描的仓库地址。

    Returns:
        {status, prompt, modules, connections, fallback_summary}
    """
    ctx = repo_cache.get(repo_url)
    if ctx is None:
        return {
            "status": "error",
            "message": "请先使用 scan_repo 或 codebook 扫描该仓库",
        }

    # 组装 LLM 上下文
    summary_context = build_summary_context(ctx)

    # 同时提供降级结果（宿主可选择直接使用或让 LLM 优化）
    fallback = build_fallback_summary(ctx)

    logger.info(
        "summarize_for_blueprint.context_ready",
        repo_url=repo_url,
        modules=len(summary_context["modules"]),
    )

    return {
        "status": "context_ready",
        "prompt": summary_context["prompt"],
        "modules": summary_context["modules"],
        "connections": summary_context["connections"],
        "fallback_summary": fallback.to_dict(),
        "guidance": (
            "请根据上述代码结构数据，为每个模块和函数生成中文业务描述。"
            "生成完成后，请调用 save_blueprint_summary 工具保存结果。"
            "如果你无法生成，可以直接使用 fallback_summary 中的降级结果。"
        ),
    }
```

- [ ] **Step 4: 实现 save_blueprint_summary 工具**

```python
# src/tools/save_blueprint_summary.py
"""save_blueprint_summary — 接收宿主 LLM 生成的蓝图摘要并缓存。

MCP 工具。宿主 LLM 完成推理后调用此工具回写结果。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from src.tools._repo_cache import repo_cache
from src.summarizer.blueprint_summary import (
    BlueprintSummary,
    parse_llm_response,
    build_fallback_summary,
)

logger = structlog.get_logger()


def _save_to_memory(repo_url: str, summary: BlueprintSummary) -> None:
    """将摘要保存到 ProjectMemory 目录。"""
    import hashlib
    repo_hash = hashlib.sha256(repo_url.encode()).hexdigest()[:16]
    memory_dir = Path.home() / ".codebook" / "memory" / repo_hash
    memory_dir.mkdir(parents=True, exist_ok=True)

    path = memory_dir / "blueprint_summary.json"
    path.write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("blueprint_summary.saved", path=str(path))


async def save_blueprint_summary(
    repo_url: str,
    summary_json: dict[str, Any],
) -> dict[str, Any]:
    """保存宿主 LLM 生成的蓝图摘要。

    Args:
        repo_url: 仓库地址。
        summary_json: LLM 生成的摘要 JSON（BlueprintSummary 格式）。

    Returns:
        {status, message}
    """
    ctx = repo_cache.get(repo_url)
    if ctx is None:
        return {"status": "error", "message": "缓存中未找到该仓库的扫描数据"}

    # 解析 LLM 返回（失败时自动降级）
    summary = parse_llm_response(summary_json, ctx)

    # 持久化
    _save_to_memory(repo_url, summary)

    logger.info(
        "save_blueprint_summary.done",
        repo_url=repo_url,
        modules=len(summary.modules),
        source="llm" if summary_json.get("project_name") else "fallback",
    )

    return {
        "status": "ok",
        "message": f"已保存 {len(summary.modules)} 个模块的业务摘要",
        "summary": summary.to_dict(),
    }
```

- [ ] **Step 5: 注册到 server.py**

在 `src/server.py` 中添加：

```python
# 在 import 区域添加
from src.tools.summarize_for_blueprint import summarize_for_blueprint as _summarize_for_blueprint
from src.tools.save_blueprint_summary import save_blueprint_summary as _save_blueprint_summary

# 在 watch_status 工具之后添加

@mcp.tool()
async def summarize_for_blueprint(repo_url: str) -> dict:
    """为蓝图生成业务语言摘要（第一步）。

    扫描完成后调用此工具。返回代码结构数据和提示词，
    请根据提示词为每个模块和函数生成中文业务描述，
    然后调用 save_blueprint_summary 保存结果。

    Args:
        repo_url: 已扫描的仓库地址。
    """
    logger.info("tool.summarize_for_blueprint", repo_url=repo_url)
    return await _summarize_for_blueprint(repo_url=repo_url)


@mcp.tool()
async def save_blueprint_summary(repo_url: str, summary_json: dict) -> dict:
    """保存蓝图业务摘要（第二步）。

    将 summarize_for_blueprint 返回的数据经 LLM 推理后的结果保存。
    如果无法生成，可直接传入 fallback_summary 中的内容。

    Args:
        repo_url: 仓库地址。
        summary_json: 生成的摘要 JSON。
    """
    logger.info("tool.save_blueprint_summary", repo_url=repo_url)
    return await _save_blueprint_summary(repo_url=repo_url, summary_json=summary_json)
```

- [ ] **Step 6: 更新工具数量测试**

修改 `tests/test_server.py` 和 `tests/test_e2e.py` 中的工具数量：从 11 改为 13，expected set 增加 `"summarize_for_blueprint"` 和 `"save_blueprint_summary"`。

- [ ] **Step 7: 运行测试确认通过**

Run: `cd /Users/jacky/Codebook/mcp-server && python3 -m pytest tests/test_summarize_tools.py tests/test_server.py tests/test_e2e.py -v -k "tool" `
Expected: ALL PASS

- [ ] **Step 8: 提交**

```bash
cd /Users/jacky/Codebook
git add mcp-server/src/tools/summarize_for_blueprint.py mcp-server/src/tools/save_blueprint_summary.py mcp-server/src/server.py mcp-server/tests/test_summarize_tools.py mcp-server/tests/test_server.py mcp-server/tests/test_e2e.py
git commit -m "feat: add summarize_for_blueprint and save_blueprint_summary MCP tools"
```

---

### Task 4: 集成到 codebook_explore 流水线

**Files:**
- Modify: `src/tools/codebook_explore.py`
- Modify: `src/tools/_repo_cache.py`

- [ ] **Step 1: 在 _repo_cache 中增加 blueprint_summary 加载**

在 `src/tools/_repo_cache.py` 中添加方法：

```python
def get_blueprint_summary(self, repo_url: str) -> dict | None:
    """加载已缓存的蓝图摘要。"""
    import hashlib
    import json
    from pathlib import Path

    repo_hash = hashlib.sha256(repo_url.encode()).hexdigest()[:16]
    path = Path.home() / ".codebook" / "memory" / repo_hash / "blueprint_summary.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
```

- [ ] **Step 2: 在 codebook_explore 的 _build_report_data 中嵌入 blueprint_summary**

在 `src/tools/codebook_explore.py` 的 `_build_report_data` 函数中，在返回的 dict 里添加 `blueprint_summary` 字段：

```python
# 在 _build_report_data 函数末尾的 return 之前添加
blueprint_summary = None
if repo_url:
    blueprint_summary = repo_cache.get_blueprint_summary(repo_url)
    if blueprint_summary is None:
        # 自动生成降级摘要
        ctx = repo_cache.get(repo_url)
        if ctx:
            from src.summarizer.blueprint_summary import build_fallback_summary
            fallback = build_fallback_summary(ctx)
            blueprint_summary = fallback.to_dict()

# 在 return dict 中添加
return {
    "overview": overview,
    "module_cards": module_cards,
    "health_overview": health_overview,
    "focus_diagrams": scan.get("focus_diagrams", {}),
    "selection_strategy": selection_strategy,
    "query": query,
    "role": role,
    "blueprint_summary": blueprint_summary,  # 新增
}
```

- [ ] **Step 3: 运行全量测试**

Run: `cd /Users/jacky/Codebook/mcp-server && python3 -m pytest tests/ -q`
Expected: ALL PASS, 0 failed

- [ ] **Step 4: 提交**

```bash
cd /Users/jacky/Codebook
git add mcp-server/src/tools/_repo_cache.py mcp-server/src/tools/codebook_explore.py
git commit -m "feat: integrate blueprint_summary into codebook_explore pipeline"
```

---

### Task 5: 全量回归 + 端到端验证

**Files:** 无新文件

- [ ] **Step 1: 运行全量测试**

Run: `cd /Users/jacky/Codebook/mcp-server && python3 -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: 端到端验证 — 降级摘要生成**

```bash
cd /Users/jacky/Codebook/mcp-server
python3 -c "
import asyncio
from src.tools.codebook_explore import codebook_explore

result = asyncio.run(codebook_explore(
    repo_url='https://github.com/ultraworkers/claw-code',
    role='pm',
))

summary = result.get('report_data', {}).get('blueprint_summary')
if summary:
    print('=== Blueprint Summary ===')
    print(f'项目: {summary.get(\"project_name\")}')
    print(f'描述: {summary.get(\"project_description\")}')
    print(f'模块数: {len(summary.get(\"modules\", []))}')
    for m in summary.get('modules', [])[:5]:
        print(f'  [{m.get(\"health\",\"?\")}] {m.get(\"business_name\")} ({m.get(\"code_path\")})')
        print(f'       {m.get(\"description\")}')
        for fn in m.get('functions', [])[:3]:
            print(f'       - {fn.get(\"business_name\")}: {fn.get(\"explanation\")}')
    print(f'连接数: {len(summary.get(\"connections\", []))}')
    for c in summary.get('connections', [])[:5]:
        print(f'  {c.get(\"from_module\")} --{c.get(\"verb\")}--> {c.get(\"to_module\")}')
else:
    print('ERROR: blueprint_summary not found in report_data')
"
```

Expected: 输出包含中文业务名称（如「认证系统」「插件系统」），每个模块有业务描述，函数有逻辑解释。

- [ ] **Step 3: 提交 tag**

```bash
cd /Users/jacky/Codebook
git tag -a blueprint-v2-phase1 -m "Blueprint v2 Phase 1: LLM summary pipeline + business naming"
```
