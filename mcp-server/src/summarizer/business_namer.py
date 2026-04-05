"""Rule-based business namer for blueprint v2 fallback.

Translates code directory names and function signatures into
human-readable Chinese business names and descriptions, so that
non-technical users can understand software blueprints.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Keyword → Chinese business name mapping (directory segments)
# ---------------------------------------------------------------------------

_KEYWORD_MAP: dict[str, str] = {
    # Authentication & authorization
    "auth": "认证系统",
    "authentication": "认证系统",
    "authorization": "授权系统",
    "oauth": "OAuth 认证",
    "sso": "单点登录",
    "rbac": "权限管理",
    "permissions": "权限管理",
    "acl": "访问控制",
    # API & networking
    "api": "API 接口",
    "rest": "REST 接口",
    "graphql": "GraphQL 接口",
    "grpc": "gRPC 接口",
    "gateway": "网关",
    "proxy": "代理服务",
    "websocket": "WebSocket 服务",
    "ws": "WebSocket 服务",
    "http": "HTTP 服务",
    "rpc": "远程调用",
    # Data
    "db": "数据库",
    "database": "数据库",
    "models": "数据模型",
    "schema": "数据结构",
    "schemas": "数据结构",
    "migration": "数据迁移",
    "migrations": "数据迁移",
    "orm": "对象关系映射",
    "sql": "SQL 查询",
    "redis": "Redis 缓存",
    "cache": "缓存系统",
    "caching": "缓存系统",
    "storage": "存储服务",
    "store": "数据存储",
    # CLI & tools
    "cli": "命令行工具",
    "cmd": "命令行工具",
    "commands": "命令集",
    "terminal": "终端工具",
    "shell": "Shell 工具",
    "repl": "交互式终端",
    # Core & runtime
    "core": "核心模块",
    "kernel": "内核",
    "runtime": "运行时引擎",
    "engine": "引擎",
    "executor": "执行器",
    "scheduler": "调度器",
    "worker": "工作进程",
    "queue": "消息队列",
    "mq": "消息队列",
    "broker": "消息代理",
    # Plugins & extensions
    "plugins": "插件系统",
    "plugin": "插件系统",
    "extensions": "扩展模块",
    "addons": "附加组件",
    "modules": "功能模块",
    # Configuration
    "config": "配置管理",
    "configuration": "配置管理",
    "settings": "设置",
    "env": "环境配置",
    # Logging & monitoring
    "logging": "日志系统",
    "logger": "日志系统",
    "logs": "日志",
    "monitor": "监控系统",
    "monitoring": "监控系统",
    "metrics": "指标采集",
    "telemetry": "遥测系统",
    "tracing": "链路追踪",
    # Testing
    "tests": "测试套件",
    "test": "测试",
    "fixtures": "测试固件",
    "mocks": "模拟数据",
    # UI & frontend
    "ui": "用户界面",
    "views": "视图层",
    "templates": "模板",
    "components": "组件库",
    "pages": "页面",
    "layouts": "布局",
    "styles": "样式",
    "assets": "静态资源",
    "static": "静态文件",
    "public": "公共资源",
    # Services & business logic
    "services": "业务服务",
    "service": "业务服务",
    "handlers": "处理器",
    "controllers": "控制器",
    "routes": "路由",
    "router": "路由器",
    "middleware": "中间件",
    "interceptors": "拦截器",
    # Utilities
    "utils": "工具集",
    "utilities": "工具集",
    "helpers": "辅助函数",
    "common": "公共模块",
    "shared": "共享模块",
    "lib": "基础库",
    "libs": "基础库",
    "pkg": "软件包",
    "packages": "软件包",
    "vendor": "第三方依赖",
    "internal": "内部模块",
    # Deployment & CI/CD
    "deploy": "部署",
    "deployment": "部署系统",
    "ci": "持续集成",
    "cd": "持续交付",
    "docker": "容器化",
    "k8s": "Kubernetes 编排",
    "kubernetes": "Kubernetes 编排",
    "infra": "基础设施",
    "terraform": "基础设施即代码",
    # Documentation
    "docs": "文档",
    "documentation": "项目文档",
    # Security
    "security": "安全模块",
    "crypto": "加密模块",
    "encryption": "加密服务",
    # Notifications
    "notifications": "通知系统",
    "email": "邮件服务",
    "sms": "短信服务",
    "push": "推送服务",
    # Media & files
    "media": "媒体处理",
    "upload": "文件上传",
    "downloads": "文件下载",
    "images": "图像处理",
    # Search & analytics
    "search": "搜索引擎",
    "analytics": "数据分析",
    "reports": "报表系统",
    # i18n
    "i18n": "国际化",
    "l10n": "本地化",
    "locales": "语言包",
    # Async & events
    "events": "事件系统",
    "signals": "信号处理",
    "hooks": "钩子系统",
    "tasks": "任务调度",
    "jobs": "后台任务",
    "cron": "定时任务",
    # Domain-specific
    "payment": "支付系统",
    "payments": "支付系统",
    "billing": "计费系统",
    "cart": "购物车",
    "orders": "订单系统",
    "inventory": "库存管理",
    "users": "用户管理",
    "user": "用户模块",
    "profile": "用户资料",
    "admin": "管理后台",
    "dashboard": "仪表盘",
    "chat": "聊天系统",
    "messaging": "消息系统",
}

# ---------------------------------------------------------------------------
# Function-name prefix → Chinese action description
# ---------------------------------------------------------------------------

_FUNC_PREFIX_MAP: dict[str, str] = {
    "get": "获取",
    "set": "设置",
    "create": "创建",
    "make": "生成",
    "build": "构建",
    "delete": "删除",
    "remove": "移除",
    "update": "更新",
    "modify": "修改",
    "patch": "局部更新",
    "save": "保存",
    "load": "加载",
    "read": "读取",
    "write": "写入",
    "send": "发送",
    "receive": "接收",
    "fetch": "拉取",
    "pull": "拉取",
    "push": "推送",
    "parse": "解析",
    "format": "格式化",
    "convert": "转换",
    "transform": "变换",
    "validate": "验证",
    "verify": "验证",
    "check": "检查",
    "test": "测试",
    "assert": "断言",
    "init": "初始化",
    "initialize": "初始化",
    "setup": "设置",
    "configure": "配置",
    "start": "启动",
    "stop": "停止",
    "run": "运行",
    "execute": "执行",
    "process": "处理",
    "handle": "处理",
    "dispatch": "分发",
    "emit": "触发",
    "trigger": "触发",
    "listen": "监听",
    "subscribe": "订阅",
    "publish": "发布",
    "register": "注册",
    "unregister": "注销",
    "login": "登录",
    "logout": "登出",
    "authenticate": "认证",
    "authorize": "授权",
    "encrypt": "加密",
    "decrypt": "解密",
    "hash": "哈希计算",
    "sign": "签名",
    "log": "记录",
    "print": "打印",
    "render": "渲染",
    "display": "显示",
    "show": "展示",
    "hide": "隐藏",
    "open": "打开",
    "close": "关闭",
    "connect": "连接",
    "disconnect": "断开连接",
    "bind": "绑定",
    "unbind": "解绑",
    "attach": "附加",
    "detach": "分离",
    "add": "添加",
    "insert": "插入",
    "append": "追加",
    "merge": "合并",
    "split": "拆分",
    "sort": "排序",
    "filter": "过滤",
    "search": "搜索",
    "find": "查找",
    "query": "查询",
    "list": "列出",
    "count": "计数",
    "aggregate": "聚合",
    "calculate": "计算",
    "compute": "计算",
    "compare": "比较",
    "diff": "差异对比",
    "sync": "同步",
    "async": "异步处理",
    "cache": "缓存",
    "flush": "刷新",
    "clear": "清除",
    "reset": "重置",
    "retry": "重试",
    "recover": "恢复",
    "rollback": "回滚",
    "migrate": "迁移",
    "export": "导出",
    "import": "导入",
    "upload": "上传",
    "download": "下载",
    "notify": "通知",
    "alert": "告警",
    "schedule": "调度",
    "cancel": "取消",
    "approve": "审批",
    "reject": "拒绝",
    "submit": "提交",
    "confirm": "确认",
    "scan": "扫描",
    "detect": "检测",
    "monitor": "监控",
    "track": "跟踪",
    "resolve": "解析",
    "serialize": "序列化",
    "deserialize": "反序列化",
    "encode": "编码",
    "decode": "解码",
    "compile": "编译",
    "evaluate": "评估",
    "map": "映射",
    "reduce": "归约",
    "collect": "收集",
    "generate": "生成",
    "extract": "提取",
    "apply": "应用",
    "wrap": "包装",
    "unwrap": "解包",
    "mount": "挂载",
    "unmount": "卸载",
    "clone": "克隆",
    "copy": "复制",
    "move": "移动",
    "rename": "重命名",
    "drop": "丢弃",
    "truncate": "截断",
    "sanitize": "清理",
    "normalize": "规范化",
    "refresh": "刷新",
    "reload": "重新加载",
    "revert": "还原",
    "revoke": "撤销",
    "grant": "授权",
    "deny": "拒绝",
    "lock": "加锁",
    "unlock": "解锁",
    "enable": "启用",
    "disable": "禁用",
    "activate": "激活",
    "deactivate": "停用",
    "unsubscribe": "退订",
    "benchmark": "基准测试",
    "profile": "性能分析",
    "debug": "调试",
    "inspect": "检查",
    "audit": "审计",
    "archive": "归档",
    "restore": "恢复",
    "backup": "备份",
    "destroy": "销毁",
    "bootstrap": "引导启动",
    "shutdown": "关闭",
    "provision": "配置资源",
    "allocate": "分配",
    "deallocate": "释放",
    "acquire": "获取",
    "release": "释放",
    "await": "等待",
    "wait": "等待",
    "poll": "轮询",
    "ping": "探测",
    "probe": "探测",
    "warm": "预热",
    "cooldown": "冷却",
    "throttle": "限流",
    "limit": "限制",
    "batch": "批量处理",
    "stream": "流式处理",
    "pipe": "管道传输",
    "route": "路由",
    "forward": "转发",
    "redirect": "重定向",
    "proxy": "代理",
    "relay": "中继",
    "broadcast": "广播",
    "multicast": "组播",
    "enqueue": "入队",
    "dequeue": "出队",
    "peek": "查看队首",
    "pop": "弹出",
}

# ---------------------------------------------------------------------------
# Connection target → Chinese verb mapping
# ---------------------------------------------------------------------------

_CONNECTION_VERB_MAP: dict[str, str] = {
    "db": "读写数据",
    "database": "读写数据",
    "sql": "查询数据",
    "redis": "读写缓存",
    "cache": "读写缓存",
    "auth": "验证权限",
    "authentication": "验证权限",
    "authorization": "验证权限",
    "logging": "写入日志",
    "logger": "写入日志",
    "log": "写入日志",
    "config": "读取配置",
    "settings": "读取配置",
    "queue": "发送消息",
    "mq": "发送消息",
    "email": "发送邮件",
    "sms": "发送短信",
    "notification": "发送通知",
    "storage": "读写存储",
    "search": "检索数据",
    "api": "请求接口",
    "gateway": "网关转发",
    "monitor": "上报监控",
    "metrics": "上报指标",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def infer_business_name(module_path: str) -> str:
    """Infer a Chinese business name from a module path.

    Matching priority:
      1. Exact match on the last path segment
      2. Partial match (segment contained in a keyword or vice-versa)
      3. Underscore-split match on individual tokens
      4. Return the original segment as-is
    """
    segment = module_path.rstrip("/").rsplit("/", maxsplit=1)[-1].lower()

    # 1. Exact match
    if segment in _KEYWORD_MAP:
        return _KEYWORD_MAP[segment]

    # 2. Partial match – keyword is substring of segment or vice-versa
    for keyword, name in _KEYWORD_MAP.items():
        if keyword in segment or segment in keyword:
            return name

    # 3. Underscore-split match
    tokens = segment.split("_")
    for token in tokens:
        if token in _KEYWORD_MAP:
            return _KEYWORD_MAP[token]

    # 4. Fallback – return segment (guaranteed non-empty)
    return segment


def infer_business_description(
    module_name: str,
    function_names: list[str],
    class_names: list[str],
    file_count: int,
    line_count: int,
) -> str:
    """Infer a one-line Chinese description from module metadata."""
    parts: list[str] = []

    # Derive module label
    module_label = _KEYWORD_MAP.get(module_name.lower(), module_name)

    # Infer actions from function names
    actions: list[str] = []
    for fn in function_names[:5]:  # limit to avoid overly long description
        prefix = fn.split("_")[0].lower()
        if prefix in _FUNC_PREFIX_MAP:
            actions.append(_FUNC_PREFIX_MAP[prefix])

    if actions:
        unique_actions = list(dict.fromkeys(actions))  # deduplicate, keep order
        parts.append(f"提供{'/'.join(unique_actions[:3])}等功能")

    # Mention classes if present
    if class_names:
        parts.append(f"包含 {len(class_names)} 个类")

    # Scale information
    if file_count > 0 and line_count > 0:
        parts.append(f"共 {file_count} 个文件、{line_count} 行代码")

    _LABEL_SUFFIXES = ("系统", "模块", "引擎", "工具", "服务", "接口", "组件", "平台")
    suffix = "" if any(module_label.endswith(s) for s in _LABEL_SUFFIXES) else "模块"

    if parts:
        return f"{module_label}{suffix}，{'，'.join(parts)}。"

    # Empty module fallback
    return f"{module_label}{suffix}（空模块，暂无实现）。"


def infer_function_explanation(
    func_name: str,
    params: list[str],
    return_type: str | None,
    docstring: str | None,
) -> str:
    """Infer a Chinese explanation of a function's implementation logic.

    Priority: docstring > function-name prefix inference.
    """
    # 1. Prefer docstring if available
    if docstring and docstring.strip():
        return docstring.strip()

    # 2. Infer from function name prefix
    prefix = func_name.split("_")[0].lower()
    action = _FUNC_PREFIX_MAP.get(prefix, "处理")

    # Build subject from remaining tokens
    tokens = func_name.split("_")[1:]
    subject = "_".join(tokens) if tokens else "数据"

    # Translate subject via keyword map if possible
    subject_cn = _KEYWORD_MAP.get(subject.lower(), subject)

    # Build parameter description
    param_desc = ""
    if params:
        param_desc = f"，参数为 {', '.join(params)}"

    # Build return type description
    return_desc = ""
    if return_type:
        return_desc = f"，返回 {return_type}"

    return f"{action} {subject_cn}{param_desc}{return_desc}"


def infer_connection_verb(
    from_module: str,
    to_module: str,
    call_count: int,
) -> str:
    """Infer a Chinese verb for the connection between two modules."""
    to_lower = to_module.lower()

    # Exact match
    if to_lower in _CONNECTION_VERB_MAP:
        return _CONNECTION_VERB_MAP[to_lower]

    # Partial match
    for keyword, verb in _CONNECTION_VERB_MAP.items():
        if keyword in to_lower or to_lower in keyword:
            return verb

    return "调用"
