"""module_grouper — 按目录结构和命名空间对文件分组为模块。"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from src.parsers.ast_parser import ParseResult

logger = structlog.get_logger()

# ── 数据类 ──────────────────────────────────────────────


@dataclass
class ModuleGroup:
    """一个逻辑模块的分组结果。"""
    name: str  # 模块名（业务语言）
    dir_path: str  # 对应的目录路径
    files: list[str] = field(default_factory=list)  # 文件路径列表
    entry_functions: list[str] = field(default_factory=list)  # 入口函数
    public_interfaces: list[str] = field(default_factory=list)  # 公开接口
    total_lines: int = 0
    is_special: bool = False  # 是否为特殊模块（配置/测试）


# ── 特殊目录识别 ─────────────────────────────────────────

TEST_PATTERNS = {"test", "tests", "spec", "specs", "__tests__", "test_", "_test"}
CONFIG_PATTERNS = {"config", "conf", "settings", "cfg"}

LARGE_FILE_THRESHOLD = 500  # 行数


def _is_test_path(path: str) -> bool:
    """判断路径是否属于测试。"""
    parts = Path(path).parts
    for part in parts:
        part_lower = part.lower()
        if part_lower in TEST_PATTERNS or part_lower.startswith("test"):
            return True
    # 文件名检查
    fname = Path(path).stem.lower()
    return fname.startswith("test_") or fname.endswith("_test") or fname.startswith("spec_")


def _is_config_file(path: str) -> bool:
    """判断文件是否为配置文件。"""
    fname = Path(path).name.lower()
    if fname in ("setup.py", "setup.cfg", "pyproject.toml", "package.json",
                  "tsconfig.json", "webpack.config.js", "vite.config.ts",
                  "Makefile", "Dockerfile", "docker-compose.yml",
                  ".env.example", "alembic.ini"):
        return True
    parts = Path(path).parts
    for part in parts:
        if part.lower() in CONFIG_PATTERNS:
            return True
    return False


def _get_top_dir(file_path: str) -> str:
    """获取文件的顶层目录。"""
    parts = Path(file_path).parts
    if len(parts) > 1:
        return parts[0]
    return "<root>"


def _get_sub_dir(file_path: str) -> str | None:
    """获取文件的第二层目录（如果有）。"""
    parts = Path(file_path).parts
    if len(parts) > 2:
        return parts[1]
    return None


# ── Swift Package 检测 ──────────────────────────────────

def _detect_swift_package_targets(repo_path: str) -> list[dict] | None:
    """解析 Package.swift 提取 target 定义作为模块边界。

    返回 [{"name": "MyLib", "path": "Sources/MyLib", "type": "regular|test"}]
    如果没有 Package.swift 则返回 None。
    """
    pkg_path = os.path.join(repo_path, "Package.swift")
    if not os.path.isfile(pkg_path):
        return None

    try:
        with open(pkg_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return None

    targets = []

    # 匹配 .target(name: "X", ...) 和 .testTarget(name: "X", ...)
    # 也匹配 .executableTarget(name: "X", ...)
    target_pattern = re.compile(
        r'\.(target|testTarget|executableTarget)\s*\(\s*name\s*:\s*"([^"]+)"'
        r'(?:.*?path\s*:\s*"([^"]+)")?',
        re.DOTALL,
    )

    for match in target_pattern.finditer(content):
        target_type = match.group(1)
        name = match.group(2)
        explicit_path = match.group(3)

        # 推断路径：如果没有显式指定，按 Swift 约定推断
        if explicit_path:
            path = explicit_path
        elif target_type == "testTarget":
            path = f"Tests/{name}"
        else:
            path = f"Sources/{name}"

        targets.append({
            "name": name,
            "path": path,
            "type": "test" if target_type == "testTarget" else "regular",
        })

    if targets:
        logger.info("swift_package.detected", targets=len(targets))
    return targets if targets else None


# ── 核心分组函数 ─────────────────────────────────────────


async def group_modules(
    parse_results: list[ParseResult],
    repo_path: str,
) -> list[ModuleGroup]:
    """按目录结构 + 命名空间将文件分组为模块。

    规则：
    0. 如果检测到 Package.swift，按 Swift Package target 划分模块
    1. 每个顶层目录 = 一个模块
    2. 如果顶层目录内有子目录，子目录 = 子模块
    3. 单个大文件（>500 LOC）可独立成模块
    4. 配置文件归入 "配置" 特殊模块
    5. 测试文件归入 "测试" 特殊模块

    Args:
        parse_results: ast_parser 的解析结果列表。
        repo_path: 仓库根目录路径。

    Returns:
        ModuleGroup 列表。
    """
    # ── 尝试 Swift Package 模块划分 ──
    swift_targets = _detect_swift_package_targets(repo_path)
    if swift_targets:
        return _group_by_swift_package(parse_results, swift_targets)

    # 按目录归类文件
    dir_files: dict[str, list[ParseResult]] = {}
    test_files: list[ParseResult] = []
    config_files: list[ParseResult] = []
    large_standalone: list[ParseResult] = []

    for pr in parse_results:
        # 测试文件
        if _is_test_path(pr.file_path):
            test_files.append(pr)
            continue

        # 配置文件
        if _is_config_file(pr.file_path):
            config_files.append(pr)
            continue

        top_dir = _get_top_dir(pr.file_path)
        sub_dir = _get_sub_dir(pr.file_path)

        # 大文件独立成模块
        if pr.line_count > LARGE_FILE_THRESHOLD and top_dir == "<root>":
            large_standalone.append(pr)
            continue

        # 有子目录时用 top/sub 作为模块路径
        if sub_dir and top_dir != "<root>":
            key = f"{top_dir}/{sub_dir}"
        else:
            key = top_dir

        dir_files.setdefault(key, []).append(pr)

    # 构建模块分组
    modules: list[ModuleGroup] = []

    for dir_path, results in sorted(dir_files.items()):
        module = _build_module(dir_path, results)
        modules.append(module)

    # 大文件独立模块
    for pr in large_standalone:
        module = _build_module(
            Path(pr.file_path).stem,
            [pr],
        )
        modules.append(module)

    # 测试模块
    if test_files:
        modules.append(ModuleGroup(
            name="测试",
            dir_path="tests/",
            files=[pr.file_path for pr in test_files],
            total_lines=sum(pr.line_count for pr in test_files),
            is_special=True,
        ))

    # 配置模块
    if config_files:
        modules.append(ModuleGroup(
            name="配置",
            dir_path="config/",
            files=[pr.file_path for pr in config_files],
            total_lines=sum(pr.line_count for pr in config_files),
            is_special=True,
        ))

    logger.info(
        "module_grouper.done",
        modules=len(modules),
        total_files=sum(len(m.files) for m in modules),
    )
    return modules


def _group_by_swift_package(
    parse_results: list[ParseResult],
    targets: list[dict],
) -> list[ModuleGroup]:
    """按 Swift Package target 定义进行模块分组。"""
    modules: list[ModuleGroup] = []
    assigned_files: set[str] = set()

    for target in targets:
        name = target["name"]
        target_path = target["path"]
        is_test = target["type"] == "test"

        # 匹配属于这个 target 的文件
        target_results = [
            pr for pr in parse_results
            if pr.file_path.startswith(target_path + "/") or pr.file_path.startswith(target_path + "\\")
        ]

        if target_results:
            module = _build_module(name, target_results)
            module.is_special = is_test
            modules.append(module)
            assigned_files.update(pr.file_path for pr in target_results)

    # 未匹配到任何 target 的文件归入 "其他" 模块
    unmatched = [pr for pr in parse_results if pr.file_path not in assigned_files]
    if unmatched:
        # 按目录结构归类未匹配文件
        dir_files: dict[str, list[ParseResult]] = {}
        for pr in unmatched:
            top_dir = _get_top_dir(pr.file_path)
            sub_dir = _get_sub_dir(pr.file_path)
            if sub_dir and top_dir != "<root>":
                key = f"{top_dir}/{sub_dir}"
            else:
                key = top_dir
            dir_files.setdefault(key, []).append(pr)

        for dir_path, results in sorted(dir_files.items()):
            modules.append(_build_module(dir_path, results))

    logger.info(
        "module_grouper.swift_package.done",
        targets=len(targets),
        modules=len(modules),
        total_files=sum(len(m.files) for m in modules),
    )
    return modules


def _build_module(dir_path: str, results: list[ParseResult]) -> ModuleGroup:
    """从一组解析结果构建 ModuleGroup。"""
    # 收集入口函数（无其他函数调用它的函数）
    all_callee_names = set()
    all_functions = []
    for pr in results:
        for call in pr.calls:
            all_callee_names.add(call.callee_name)
        for func in pr.functions:
            all_functions.append(func)

    entry_functions = [
        f.name for f in all_functions
        if not f.is_method and f.name not in all_callee_names and not f.name.startswith("_")
    ]

    # 公开接口（不以 _ 开头的函数/类）
    public_interfaces = []
    for pr in results:
        for func in pr.functions:
            if not func.name.startswith("_") and not func.is_method:
                public_interfaces.append(func.name)
        for cls in pr.classes:
            if not cls.name.startswith("_"):
                public_interfaces.append(cls.name)

    return ModuleGroup(
        name=dir_path,
        dir_path=dir_path,
        files=[pr.file_path for pr in results],
        entry_functions=entry_functions[:10],  # 限制数量
        public_interfaces=list(set(public_interfaces))[:20],
        total_lines=sum(pr.line_count for pr in results),
    )


def build_node_module_map(
    modules: list[ModuleGroup],
    parse_results: list[ParseResult],
) -> dict[str, str]:
    """构建 node_id -> module_name 的映射，用于 DependencyGraph.set_module_groups()。

    Args:
        modules: 模块分组结果。
        parse_results: 解析结果。

    Returns:
        {node_id: module_name}
    """
    # 文件 -> 模块映射
    file_to_module: dict[str, str] = {}
    for module in modules:
        for f in module.files:
            file_to_module[f] = module.name

    # 节点 -> 模块映射
    node_map: dict[str, str] = {}
    for pr in parse_results:
        module_name = file_to_module.get(pr.file_path, "")
        if not module_name:
            continue

        for func in pr.functions:
            if func.parent_class:
                node_id = f"{pr.file_path}::{func.parent_class}.{func.name}"
            else:
                node_id = f"{pr.file_path}::{func.name}"
            node_map[node_id] = module_name

        for cls in pr.classes:
            node_id = f"{pr.file_path}::{cls.name}"
            node_map[node_id] = module_name

        # <module> 节点
        node_map[f"{pr.file_path}::<module>"] = module_name

    return node_map
