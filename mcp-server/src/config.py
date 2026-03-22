"""CodeBook MCP Server 配置管理。"""

import os
import tempfile

from pydantic_settings import BaseSettings


def _default_cache_dir() -> str:
    """返回一个可写的缓存目录，优先用用户目录下的 .codebook_cache。"""
    home_cache = os.path.join(os.path.expanduser("~"), ".codebook_cache")
    try:
        os.makedirs(home_cache, exist_ok=True)
        return home_cache
    except OSError:
        return os.path.join(tempfile.gettempdir(), "codebook_cache")


class Settings(BaseSettings):
    """应用配置，支持环境变量和 .env 文件。"""

    app_name: str = "CodeBook"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # AI provider
    ai_model: str = "claude-sonnet-4-20250514"
    ai_max_tokens: int = 8192

    # 仓库扫描
    max_repo_size_mb: int = 100
    clone_timeout_seconds: int = 120
    supported_languages: list[str] = [
        "python", "typescript", "javascript", "java", "go", "rust", "cpp", "c", "csharp", "ruby",
    ]

    # 缓存
    cache_dir: str = _default_cache_dir()

    model_config = {"env_prefix": "CODEBOOK_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
