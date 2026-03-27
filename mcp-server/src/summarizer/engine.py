"""summarizer.engine — 模块卡片生成引擎。

读取 prompts/summary/ 下的 Prompt 模板，填充变量后调用 LLM 生成
项目概览（L1）、模块地图（L2）、模块卡片（L3）和代码细节（L4）。
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from src.config import settings
from src.parsers.ast_parser import ParseResult
from src.parsers.dependency_graph import DEFAULT_MAX_OVERVIEW_NODES, DependencyGraph
from src.parsers.module_grouper import ModuleGroup
from src.parsers.repo_cloner import CloneResult
from src.glossary.term_resolver import TermResolver

logger = structlog.get_logger()

# ── Prompt 模板路径 ──────────────────────────────────────


def _find_project_root() -> Path:
    """定位 Codebook 项目根目录（包含 prompts/summary/ 目录的那层）。

    搜索策略：
    1. 从 __file__ 向上逐级查找含有 prompts/summary/ 子目录的目录
    2. 从 CWD 向上查找
    3. 从 CWD 的父目录查找（pytest 通常从 mcp-server/ 运行，项目根在其上一层）
    4. 回退到固定层级计算（兼容旧行为）

    注意：mcp-server/src/prompts/ 是一个空的 Python 包目录（仅含 __init__.py），
    不是真正的 prompt 模板目录。真正的模板在项目根的 prompts/summary/ 下。
    """
    def _is_valid_prompts_root(d: Path) -> bool:
        """检查目录是否包含有效的 prompts 结构。

        要求 prompts/ 目录中至少有 summary/ 子目录或 codebook_config 文件。
        排除 mcp-server/src/prompts/（仅含 __init__.py 的空包目录）。
        """
        prompts = d / "prompts"
        if not prompts.is_dir():
            return False
        # 检查是否有实际的 prompt 资源（排除空的 Python 包目录）
        has_summary = (prompts / "summary").is_dir()
        has_v03_config = (prompts / "codebook_config_v0.3.json").is_file()
        has_v02_config = (prompts / "codebook_config_v0.2.json").is_file()
        return has_summary or has_v03_config or has_v02_config

    # Strategy 1: search upward from __file__
    current = Path(__file__).resolve().parent
    for _ in range(8):
        if _is_valid_prompts_root(current):
            return current
        parent = current.parent
        if parent == current:  # reached filesystem root
            break
        current = parent

    # Strategy 2: search upward from CWD (covers pytest invocation scenarios)
    current = Path.cwd()
    for _ in range(5):
        if _is_valid_prompts_root(current):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Strategy 3: CWD 可能是 mcp-server/，项目根在其父目录
    cwd_parent = Path.cwd().parent
    if _is_valid_prompts_root(cwd_parent):
        return cwd_parent

    # Strategy 4: original fixed-depth calculation
    return Path(__file__).resolve().parent.parent.parent.parent


_PROJECT_ROOT = _find_project_root()
PROMPTS_DIR = _PROJECT_ROOT / "prompts" / "summary"
CONFIG_PATH = _PROJECT_ROOT / "prompts" / "codebook_config_v0.2.json"

# ── 内置回退配置（当 JSON 文件均无法加载时使用）──────────

_BUILTIN_CONFIG_FALLBACK: dict = {
    "role_system_v0_3": {
        "views": [
            {
                "name": "dev",
                "display_name": "开发者视角",
                "banned_terms": [],
            },
            {
                "name": "pm",
                "display_name": "产品经理视角",
                "banned_terms": [
                    "幂等 / idempotent", "slug", "冷启动 / cold start",
                    "连接池 / connection pool", "openapi / swagger",
                    "env_file / .env", "middleware / 中间件",
                    "布尔值 / boolean", "回调 / callback", "异步 / async",
                    "序列化 / serialize", "AST", "NetworkX", "Tree-sitter",
                ],
            },
            {
                "name": "domain_expert",
                "display_name": "行业专家视角",
                "requires_project_domain": True,
                "supported_domains": ["fintech", "healthcare", "ecommerce", "saas", "general"],
            },
        ],
    },
    "backward_compatibility": {
        "mappings": {
            "ceo": "pm",
            "pm": "pm",
            "investor": "pm",
            "qa": "dev",
            "dev": "dev",
            "domain_expert": "domain_expert",
        },
    },
    "project_domain_inference": {
        "priority_layers": [
            {"layer": 1, "name": "显式参数", "description": "scan_repo(project_domain='fintech') 中明确指定的值"},
            {
                "layer": 2, "name": "自动推断",
                "description": "从 README.md 关键词和依赖包名推断",
                "inference_rules": {
                    "fintech": {
                        "readme_keywords": ["金融", "支付", "交易", "钱包", "银行", "转账"],
                        "dependency_markers": ["stripe", "braintree", "square", "wise", "alipay", "paypal"],
                    },
                    "healthcare": {
                        "readme_keywords": ["医疗", "诊断", "患者", "处方", "病历"],
                        "dependency_markers": ["fhir", "hl7", "dicom", "hl7apy"],
                    },
                    "ecommerce": {
                        "readme_keywords": ["电商", "购物车", "订单", "物流", "商品"],
                        "dependency_markers": ["shopify", "woocommerce", "bigcommerce", "prestashop"],
                    },
                },
            },
            {"layer": 3, "name": "术语库记忆", "description": "从 ~/.codebook/memory/{repo_hash}/meta.json 读取"},
        ],
    },
    "guidance_templates": {
        "dev": "你是 CodeBook 的 AI 助手，正在帮助开发者理解代码。\n\n提供精确的代码定位、调用栈分析和实现细节。\n\n关键信息：函数签名、参数类型、返回值、异常处理、循环依赖、性能瓶颈、内存安全。\n\n可以使用所有技术术语（AST、序列化、中间件、幂等性、连接池等）。\n\n优先包含源代码而非文档。支持追问函数签名、异常处理、边界条件等技术细节。",
        "pm": "你是 CodeBook 的 AI 助手，正在帮助产品经理理解代码变更的业务影响。\n\n使用纯业务语言描述问题，避免使用技术术语。\n\n关键信息：功能完整性、用户体验影响、工作量估算、依赖关系、风险识别。\n\n禁止使用以下术语：幂等、slug、冷启动、连接池、中间件、序列化、回调、异步、AST、NetworkX、Tree-sitter。必须将这些概念转化为业务语言。\n\n优先包含模块概览而非源代码。支持追问完成度、工作量估算等管理类问题。",
        "domain_expert": "你是 CodeBook 的 AI 助手，正在帮助行业专家审查代码。\n\n你的任务是用该领域的专业术语翻译代码逻辑，让行业专家能够验证实现是否符合行业标准和最佳实践。\n\n关键信息：业务规则验证、合规检查、风险识别、审计记录。\n\n重点识别涉及数据安全、合规要求、业务规则的代码部分。",
        "domain_expert_fintech": "你是 CodeBook 的 AI 助手，正在帮助金融合规官审查代码。\n\n项目领域：金融科技。应当使用以下术语及其业务含义：\n- KYC = 客户身份验证\n- AML = 反洗钱检查\n- settlement = 资金结算\n- transaction = 交易\n\n关键检查项：交易金额限制、审计日志、加密存储、访问控制、异常交易检测。",
        "domain_expert_healthcare": "你是 CodeBook 的 AI 助手，正在帮助医疗数据官审查代码。\n\n项目领域：医疗健康。应当使用以下术语及其业务含义：\n- FHIR = 快速医疗互操作性资源\n- HL7 = 医疗信息交换标准\n- PHI = 受保护的健康信息\n- 患者隐私 = 医疗数据的绝对保密性需求\n- 诊断 = 医学判断\n\n关键检查项：患者数据加密、访问日志、诊断链的可审计性。",
        "domain_expert_ecommerce": "你是 CodeBook 的 AI 助手，正在帮助电商风控专家审查代码。\n\n项目领域：电子商务。应当使用以下术语及其业务含义：\n- 订单 = 用户购买行为的记录\n- 支付 = 交易金额的验证和转移\n- 物流 = 商品配送的跟踪管理\n- 库存 = 可售商品的数量管理\n- 退款 = 交易取消和金额返还\n\n关键检查项：订单的一致性、支付的原子性、库存扣减时机、退款流程的完整性。",
    },
    "banned_terms_in_pm_fields": {
        "terms": {
            "幂等 / idempotent": "描述重复操作的具体后果",
            "slug": "URL 中的文章标识",
            "冷启动 / cold start": "描述具体缺失场景（如「新用户首页为空」）",
            "连接池 / connection pool": "同时处理请求的上限",
            "openapi / swagger": "API 调试页面",
            "env_file / .env": "配置文件",
            "middleware / 中间件": "请求处理的中间环节",
            "布尔值 / boolean": "是/否",
            "回调 / callback": "完成后自动触发的操作",
            "异步 / async": "不阻塞其他操作地执行",
            "序列化 / serialize": "把数据转换成可传输的格式",
            "AST / 抽象语法树": "代码的结构化表示",
            "NetworkX": "图论库",
            "Tree-sitter": "代码解析库",
        },
    },
    "http_status_code_annotations": {
        "codes": {
            "200": "成功",
            "201": "创建成功",
            "204": "操作成功，无返回内容",
            "400": "请求有误",
            "401": "未登录",
            "403": "没有权限",
            "404": "找不到",
            "409": "数据冲突",
            "422": "数据格式不对",
            "500": "系统内部错误",
        },
    },
}


# ── 数据类 ──────────────────────────────────────────────

@dataclass
class SummaryContext:
    """生成摘要所需的完整上下文。"""
    clone_result: CloneResult
    parse_results: list[ParseResult]
    modules: list[ModuleGroup]
    dep_graph: DependencyGraph
    role: str = "pm"
    repo_url: Optional[str] = None


@dataclass
class ProjectOverview:
    """L1 项目概览。"""
    project_summary: str = ""


@dataclass
class ModuleMapItem:
    """L2 模块地图中的一个模块。"""
    name: str = ""
    paths: list[str] = field(default_factory=list)
    responsibility: str = ""
    entry_points: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    used_by: list[str] = field(default_factory=list)
    pm_note: str = ""


@dataclass
class ModuleMap:
    """L2 模块总览地图。"""
    modules: list[ModuleMapItem] = field(default_factory=list)
    mermaid_diagram: str = ""


@dataclass
class ModuleCard:
    """L3 模块卡片。"""
    name: str = ""
    path: str = ""
    what: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    branches: list[dict] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    blast_radius: list[str] = field(default_factory=list)
    key_code_refs: list[str] = field(default_factory=list)
    pm_note: str = ""


@dataclass
class ModuleChapter:
    """read_chapter 的输出：一个模块的所有卡片 + 依赖图。"""
    module_name: str = ""
    cards: list[ModuleCard] = field(default_factory=list)
    dependency_graph: str = ""


# ── Prompt 加载 ──────────────────────────────────────────

def _load_prompt_template(level: str) -> dict:
    """加载指定级别的 Prompt 模板 JSON。"""
    filenames = {
        "L1": "L1_project_overview.json",
        "L2": "L2_module_map.json",
        "L3": "L3_module_card.json",
        "L4": "L4_code_detail.json",
    }
    filepath = PROMPTS_DIR / filenames[level]
    if not filepath.exists():
        # 尝试重新定位项目根（模块初始化时可能 CWD 不同）
        alt_root = _find_project_root()
        alt_path = alt_root / "prompts" / "summary" / filenames[level]
        if alt_path.exists():
            filepath = alt_path
        else:
            raise FileNotFoundError(f"Prompt template not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_codebook_config() -> dict:
    """加载 codebook_config_v0.3.json，回退到 v0.2，最终回退到内置默认值。"""
    # Try v0.3 first
    v0_3_path = _PROJECT_ROOT / "prompts" / "codebook_config_v0.3.json"
    if v0_3_path.exists():
        try:
            with open(v0_3_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("config.v0_3_load_error", path=str(v0_3_path), error=str(e))

    # Fallback to v0.2
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("config.v0_2_load_error", path=str(CONFIG_PATH), error=str(e))

    # 最终回退：内置默认配置（确保核心功能始终可用）
    logger.warning("config.using_builtin_fallback",
                    project_root=str(_PROJECT_ROOT),
                    v0_3_path=str(v0_3_path),
                    config_path=str(CONFIG_PATH))
    return _BUILTIN_CONFIG_FALLBACK


def _normalize_role(role: str) -> str:
    """将旧角色名映射到新视图系统。

    Args:
        role: 原始角色名

    Returns:
        规范化的角色名（dev/pm/domain_expert）
    """
    config = _load_codebook_config()
    mappings = config.get("backward_compatibility", {}).get("mappings", {})

    normalized = mappings.get(role, role)

    # 校验规范化后的角色是否有效
    valid_roles = {"dev", "pm", "domain_expert"}
    if normalized not in valid_roles:
        logger.warning("invalid_role", original=role, normalized=normalized)
        return "pm"  # Default fallback

    if normalized != role:
        logger.debug("role_mapped", original=role, mapped_to=normalized)

    return normalized


def _get_banned_terms(repo_url: Optional[str] = None, role: str = "pm") -> str:
    """获取禁用术语表的文本形式。

    首先尝试通过 TermResolver 获取（如果提供了 repo_url），
    失败或无 repo_url 时，回退到 JSON 配置文件读取。
    dev 视角不应用禁用术语；只在 pm 视角应用。

    Args:
        repo_url: 仓库 URL，用于通过 TermResolver 加载术语
        role: 角色名（dev/pm/domain_expert）

    Returns:
        格式化的术语表文本，用于注入 prompt
    """
    # dev 视角无禁用术语
    if role == "dev":
        logger.debug("banned_terms.skipped_for_dev_role")
        return ""

    # 尝试通过 TermResolver 获取（优先级更高）
    if repo_url:
        try:
            resolver = TermResolver(repo_url)
            resolved = resolver.resolve()
            if resolved:
                logger.debug("banned_terms.from_resolver", repo_url=repo_url, role=role)
                return resolved
        except Exception as e:
            logger.debug(
                "banned_terms.resolver_failed",
                repo_url=repo_url,
                error=str(e),
            )
            # 继续回退到 JSON 读取

    # 回退到 JSON 配置文件
    config = _load_codebook_config()
    banned = config.get("banned_terms_in_pm_fields", {}).get("terms", {})
    if not banned:
        logger.debug("banned_terms.not_configured", role=role)
        return "（未配置禁用术语表）"

    lines = []
    for term, replacement in banned.items():
        lines.append(f"- 「{term}」→ {replacement}")

    logger.debug("banned_terms.from_config", term_count=len(banned), role=role)
    return "\n".join(lines)


def _get_role_guidance(role: str, project_domain: Optional[str] = None) -> str:
    """获取特定角色和领域的 guidance 文本。

    Args:
        role: 规范化的角色名（dev/pm/domain_expert）
        project_domain: 项目领域（用于 domain_expert 视角，如 fintech）

    Returns:
        guidance 文本
    """
    config = _load_codebook_config()
    guidance_templates = config.get("guidance_templates", {})

    if role == "domain_expert" and project_domain:
        # 查找特定领域的 guidance
        domain_key = f"domain_expert_{project_domain}"
        if domain_key in guidance_templates:
            logger.debug("guidance.loaded", role=role, domain=project_domain)
            return guidance_templates[domain_key]

    # 回退到通用 guidance
    guidance = guidance_templates.get(role, "")
    if not guidance:
        logger.warning("guidance.not_found", role=role, project_domain=project_domain)
        return ""

    logger.debug("guidance.loaded", role=role)
    return guidance


def _get_http_annotations() -> str:
    """获取 HTTP 状态码注释表。"""
    config = _load_codebook_config()
    codes = config.get("http_status_code_annotations", {}).get("codes", {})
    if not codes:
        return "（未配置状态码注释表）"
    lines = []
    for code, meaning in codes.items():
        lines.append(f"- {code}（{meaning}）")
    return "\n".join(lines)


# ── 上下文提取辅助 ───────────────────────────────────────

def _build_file_tree(clone_result: CloneResult, max_depth: int = 2) -> str:
    """从 CloneResult 构建目录树文本。"""
    dirs: set[str] = set()
    for f in clone_result.files:
        parts = Path(f.path).parts
        for i in range(1, min(len(parts), max_depth + 1)):
            dirs.add("/".join(parts[:i]))
    sorted_dirs = sorted(dirs)
    return "\n".join(sorted_dirs) if sorted_dirs else "(empty)"


def _get_entry_file_content(clone_result: CloneResult, max_lines: int = 100) -> str:
    """找到入口文件并返回其内容。"""
    entry_patterns = ["main.py", "app.py", "index.ts", "index.js", "server.py", "app/__init__.py"]
    for pattern in entry_patterns:
        for f in clone_result.files:
            if f.path.endswith(pattern):
                try:
                    with open(f.abs_path, "r", encoding="utf-8", errors="replace") as fh:
                        lines = fh.readlines()
                    return "".join(lines[:max_lines])
                except OSError:
                    continue
    return "(入口文件未找到)"


def _module_groups_to_text(modules: list[ModuleGroup]) -> str:
    """将模块分组转为文本摘要。"""
    lines = []
    for m in modules:
        special = " [特殊模块]" if m.is_special else ""
        lines.append(f"- {m.name}{special}: {len(m.files)} 文件, {m.total_lines} 行")
        if m.entry_functions:
            lines.append(f"  入口函数: {', '.join(m.entry_functions[:5])}")
        if m.public_interfaces:
            lines.append(f"  公开接口: {', '.join(m.public_interfaces[:5])}")
    return "\n".join(lines)


def _dependency_edges_to_text(dep_graph: DependencyGraph) -> str:
    """将模块级依赖边转为文本。"""
    mg = dep_graph.get_module_graph()
    lines = []
    for u, v, data in mg.edges(data=True):
        count = data.get("call_count", 1)
        strength = "强" if count >= 5 else "弱"
        lines.append(f"- {u} → {v} (调用 {count} 次, {strength}依赖)")
    return "\n".join(lines) if lines else "(无模块间依赖)"


def _module_functions_to_text(
    modules: list[ModuleGroup],
    parse_results: list[ParseResult],
) -> str:
    """列出每个模块的关键函数和类。"""
    # file -> module 映射
    file_to_module: dict[str, str] = {}
    for m in modules:
        for f in m.files:
            file_to_module[f] = m.name

    # 按模块收集
    module_symbols: dict[str, list[str]] = {}
    for pr in parse_results:
        mod = file_to_module.get(pr.file_path, "未分组")
        symbols = module_symbols.setdefault(mod, [])
        for cls in pr.classes:
            symbols.append(f"class {cls.name} ({pr.file_path}:L{cls.line_start})")
        for func in pr.functions:
            if not func.name.startswith("_") and not func.is_method:
                symbols.append(f"func {func.name}({', '.join(func.params[:3])}) ({pr.file_path}:L{func.line_start})")

    lines = []
    for mod_name, syms in sorted(module_symbols.items()):
        lines.append(f"\n### {mod_name}")
        for s in syms[:10]:
            lines.append(f"  - {s}")
        if len(syms) > 10:
            lines.append(f"  - ... (还有 {len(syms)-10} 个)")
    return "\n".join(lines)


def _get_module_source(module: ModuleGroup, max_lines_per_file: int = 200) -> str:
    """读取模块所有文件的源代码。"""
    parts = []
    for fpath in module.files[:15]:  # 限制文件数量
        # 需要从 abs_path 读取，但 ModuleGroup 只存相对路径
        # engine 调用时需要传入 repo_path
        parts.append(f"\n--- {fpath} ---\n(源代码需要在运行时从仓库读取)")
    return "\n".join(parts)


def _get_module_source_from_repo(
    module: ModuleGroup,
    repo_path: str,
    max_lines_per_file: int = 200,
) -> str:
    """从仓库目录读取模块所有文件的源代码。"""
    parts = []
    for fpath in module.files[:15]:
        abs_path = os.path.join(repo_path, fpath)
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            content = "".join(lines[:max_lines_per_file])
            if len(lines) > max_lines_per_file:
                content += f"\n... (省略 {len(lines) - max_lines_per_file} 行)"
            parts.append(f"\n--- {fpath} ---\n{content}")
        except OSError:
            parts.append(f"\n--- {fpath} ---\n(无法读取)")
    return "\n".join(parts)


def _parse_result_summary(
    module: ModuleGroup,
    parse_results: list[ParseResult],
) -> str:
    """生成模块的 ParseResult 摘要。"""
    module_files = set(module.files)
    relevant = [pr for pr in parse_results if pr.file_path in module_files]

    lines = []
    for pr in relevant:
        lines.append(f"\n文件: {pr.file_path}")
        if pr.classes:
            lines.append(f"  类: {', '.join(c.name for c in pr.classes)}")
        if pr.functions:
            func_names = [f"{f.name}({', '.join(f.params[:3])})" for f in pr.functions[:10]]
            lines.append(f"  函数: {', '.join(func_names)}")
        if pr.calls:
            call_summary = set(f"{c.caller_func}→{c.callee_name}" for c in pr.calls[:20])
            lines.append(f"  调用: {', '.join(list(call_summary)[:10])}")
    return "\n".join(lines)


def _get_upstream_downstream(
    module: ModuleGroup,
    dep_graph: DependencyGraph,
    modules: list[ModuleGroup],
) -> tuple[str, str]:
    """获取模块的上下游依赖文本。"""
    mg = dep_graph.get_module_graph()
    name = module.name

    upstream = []
    if name in mg:
        for pred in mg.predecessors(name):
            upstream.append(pred)

    downstream = []
    if name in mg:
        for succ in mg.successors(name):
            downstream.append(succ)

    up_text = ", ".join(upstream) if upstream else "(无上游依赖)"
    down_text = ", ".join(downstream) if downstream else "(无下游依赖)"
    return up_text, down_text


# ── Prompt 构建 ──────────────────────────────────────────

def _safe_format(template_str: str, **kwargs) -> str:
    """安全的模板替换，只替换已知变量，不碰其他花括号。"""
    result = template_str
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def build_l1_prompt(ctx: SummaryContext) -> tuple[str, str]:
    """构建 L1 项目概览的 system + user prompt。"""
    template = _load_prompt_template("L1")

    system = template["system_prompt"]
    user = _safe_format(
        template["user_prompt"],
        file_tree=_build_file_tree(ctx.clone_result),
        language_stats=json.dumps(ctx.clone_result.languages, ensure_ascii=False),
        entry_file_content=_get_entry_file_content(ctx.clone_result),
    )
    return system, user


def build_l2_prompt(ctx: SummaryContext, project_summary: str = "") -> tuple[str, str]:
    """构建 L2 模块总览的 system + user prompt。"""
    template = _load_prompt_template("L2")

    # 规范化角色并获取 guidance
    normalized_role = _normalize_role(ctx.role)
    banned_terms = _get_banned_terms(ctx.repo_url, role=normalized_role)

    system = _safe_format(template["system_prompt"], banned_terms=banned_terms)
    user = _safe_format(
        template["user_prompt"],
        project_summary=project_summary or "(待生成)",
        module_groups=_module_groups_to_text(ctx.modules),
        dependency_edges=_dependency_edges_to_text(ctx.dep_graph),
        module_functions=_module_functions_to_text(ctx.modules, ctx.parse_results),
    )
    return system, user


def build_l3_prompt(
    ctx: SummaryContext,
    module: ModuleGroup,
    repo_path: str,
) -> tuple[str, str]:
    """构建 L3 模块卡片的 system + user prompt。"""
    template = _load_prompt_template("L3")

    # 规范化角色并获取 guidance
    normalized_role = _normalize_role(ctx.role)
    banned_terms = _get_banned_terms(ctx.repo_url, role=normalized_role)

    system = _safe_format(
        template["system_prompt"],
        http_status_annotations=_get_http_annotations(),
        banned_terms=banned_terms,
    )

    upstream, downstream = _get_upstream_downstream(module, ctx.dep_graph, ctx.modules)

    user = _safe_format(
        template["user_prompt"],
        module_name=module.name,
        module_info=json.dumps({
            "name": module.name,
            "dir_path": module.dir_path,
            "files": module.files,
            "entry_functions": module.entry_functions,
            "public_interfaces": module.public_interfaces,
            "total_lines": module.total_lines,
        }, ensure_ascii=False, indent=2),
        source_code=_get_module_source_from_repo(module, repo_path),
        parse_result=_parse_result_summary(module, ctx.parse_results),
        upstream=upstream,
        downstream=downstream,
    )
    return system, user


def build_l4_prompt(
    file_path: str,
    line_start: int,
    line_end: int,
    symbol_name: str,
    language: str,
    code_content: str,
    module_name: str,
    callers: list[str],
    callees: list[str],
) -> tuple[str, str]:
    """构建 L4 代码细节的 system + user prompt。"""
    template = _load_prompt_template("L4")

    system = template["system_prompt"]
    user = _safe_format(
        template["user_prompt"],
        file_path=file_path,
        line_start=str(line_start),
        line_end=str(line_end),
        symbol_name=symbol_name,
        language=language,
        code_content=code_content,
        module_name=module_name,
        callers=", ".join(callers) if callers else "(无调用方)",
        callees=", ".join(callees) if callees else "(无被调用函数)",
    )
    return system, user


# ── 主入口：基于代码解析结果生成本地摘要（不调用 LLM） ──

def generate_local_blueprint(ctx: SummaryContext) -> dict:
    """不调用 LLM，直接从解析结果生成蓝图数据。

    用于 placeholder 阶段或 LLM 不可用时，确保基本功能可用。

    Returns:
        与 scan_repo 工具返回格式一致的字典。
    """
    start_time = time.time()

    # 项目概览
    langs = ctx.clone_result.languages
    primary_lang = max(langs, key=langs.get) if langs else "unknown"
    project_summary = (
        f"该项目使用 {primary_lang} 语言，"
        f"包含 {len(ctx.clone_result.files)} 个文件、"
        f"{ctx.clone_result.total_lines} 行代码，"
        f"分为 {len([m for m in ctx.modules if not m.is_special])} 个业务模块。"
    )

    # 模块列表
    mg = ctx.dep_graph.get_module_graph()
    module_items = []
    for m in ctx.modules:
        if m.is_special:
            continue

        depends_on = list(mg.predecessors(m.name)) if m.name in mg else []
        used_by = list(mg.successors(m.name)) if m.name in mg else []

        module_items.append({
            "name": m.name,
            "paths": [m.dir_path],
            "responsibility": f"包含 {len(m.files)} 个文件、{m.total_lines} 行代码",
            "entry_points": m.entry_functions[:5],
            "depends_on": depends_on,
            "used_by": used_by,
            "pm_note": f"公开接口: {', '.join(m.public_interfaces[:3])}" if m.public_interfaces else "",
        })

    # Mermaid 图 — 大项目自动使用聚合概览
    if len(mg.nodes) > DEFAULT_MAX_OVERVIEW_NODES:
        mermaid = ctx.dep_graph.to_mermaid(level="overview")
    else:
        mermaid = ctx.dep_graph.to_mermaid(level="module")

    # 连接
    connections = []
    for u, v, data in mg.edges(data=True):
        connections.append({
            "from": u,
            "to": v,
            "label": "",
            "strength": "strong" if data.get("call_count", 1) >= 5 else "weak",
        })

    elapsed = time.time() - start_time

    return {
        "status": "ok",
        "project_overview": project_summary,
        "modules": module_items,
        "connections": connections,
        "mermaid_diagram": mermaid,
        "stats": {
            "files": len(ctx.clone_result.files),
            "modules": len(module_items),
            "functions": sum(len(pr.functions) for pr in ctx.parse_results),
            "scan_time_seconds": round(elapsed, 2),
        },
    }


def generate_local_chapter(
    ctx: SummaryContext,
    module_name: str,
) -> dict:
    """不调用 LLM，直接从解析结果生成模块卡片数据。

    Returns:
        与 read_chapter 工具返回格式一致的字典。
    """
    # 找到对应模块
    target = None
    for m in ctx.modules:
        if m.name == module_name:
            target = m
            break

    if target is None:
        return {
            "status": "error",
            "error": f"模块 '{module_name}' 不存在",
            "available_modules": [m.name for m in ctx.modules],
        }

    module_files = set(target.files)
    relevant_prs = [pr for pr in ctx.parse_results if pr.file_path in module_files]

    # 为每个文件生成简化卡片
    cards = []
    for pr in relevant_prs:
        if not pr.functions and not pr.classes:
            continue

        # 收集分支信息
        branches = []
        for func in pr.functions:
            branches.append({
                "condition": f"调用 {func.name}",
                "result": f"执行 {func.name} 逻辑",
                "code_ref": f"{pr.file_path}:L{func.line_start}",
            })

        cards.append({
            "name": pr.file_path.split("/")[-1].replace(".py", "").replace(".ts", ""),
            "path": pr.file_path,
            "what": f"包含 {len(pr.functions)} 个函数, {len(pr.classes)} 个类",
            "inputs": [f"来自 {imp.module}" for imp in pr.imports[:5] if imp.module],
            "outputs": [f.name for f in pr.functions if not f.name.startswith("_")][:5],
            "branches": branches[:5],
            "side_effects": [],
            "blast_radius": [],
            "key_code_refs": [
                f"{pr.file_path}:L{f.line_start}-L{f.line_end}"
                for f in pr.functions[:5]
            ],
            "pm_note": "",
        })

    # 局部依赖图
    dep_mermaid = ctx.dep_graph.to_mermaid(level="function")

    return {
        "status": "ok",
        "module_name": module_name,
        "module_cards": cards,
        "dependency_graph": dep_mermaid,
    }
