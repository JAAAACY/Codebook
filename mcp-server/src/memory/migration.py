"""Migration: Auto-migrate old ~/.codebook_cache/ to new ~/.codebook/memory/

This module detects the old cache directory and migrates its contents to the new
ProjectMemory storage layer. Migration is idempotent and fails gracefully.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


def _get_repo_hash(repo_url: str) -> str:
    """Generate stable hash for repository URL."""
    return hashlib.sha256(repo_url.encode()).hexdigest()[:16]


# These are now accessed via functions to support dynamic Path.home() mocking
OLD_CACHE_ROOT = None  # Will be computed dynamically


def _get_old_cache_root() -> Path:
    """Get old cache root directory (supports mocking)."""
    return Path.home() / ".codebook_cache"


def _get_old_cache_contexts() -> Path:
    """Get old cache contexts directory."""
    return _get_old_cache_root() / "contexts"


def _get_new_memory_root() -> Path:
    """Get new memory root directory."""
    return Path.home() / ".codebook" / "memory"


def _get_migration_marker() -> Path:
    """Get migration marker file."""
    return _get_old_cache_root() / ".migrated"


def _migrate_context_file(
    old_file: Path, repo_url: str, repo_hash: str
) -> bool:
    """Migrate a single cache file from old to new location.

    Args:
        old_file: Path to old cache file
        repo_url: Repository URL from cache metadata
        repo_hash: Hashed repo URL for new directory

    Returns:
        True if migration succeeded, False otherwise
    """
    try:
        # Create new memory directory
        new_memory_root = _get_new_memory_root()
        new_dir = new_memory_root / repo_hash
        new_dir.mkdir(parents=True, exist_ok=True)

        # Read old cache file
        with open(old_file, "r", encoding="utf-8") as f:
            old_data = json.load(f)

        # Transform: old format has everything at top level,
        # new format wraps it in a "context" key
        new_data = {
            "version": 1,
            "repo_url": repo_url,
            "timestamp": old_data.get("timestamp", ""),
            "context": old_data,  # Wrap old data as "context"
        }

        # Write to new location
        new_file = new_dir / "context.json"
        with open(new_file, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)

        logger.info(
            "migration.context_migrated",
            old_file=str(old_file),
            new_file=str(new_file),
            repo_url=repo_url,
            repo_hash=repo_hash,
        )
        return True

    except Exception as e:
        logger.warning(
            "migration.context_migration_failed",
            old_file=str(old_file),
            error=str(e),
        )
        return False


def should_migrate() -> bool:
    """Check if migration is needed.

    Returns:
        True if old cache exists and migration hasn't been performed
    """
    old_cache_root = _get_old_cache_root()
    migration_marker = _get_migration_marker()
    old_cache_contexts = _get_old_cache_contexts()

    if not old_cache_root.exists():
        return False
    if migration_marker.exists():
        return False
    return old_cache_contexts.exists() and any(
        f.endswith(".json") for f in os.listdir(old_cache_contexts)
    )


def perform_migration() -> dict[str, Any]:
    """Perform migration from old to new cache system.

    Returns:
        Dictionary with migration results:
        {
            "migrated": bool - whether any files were migrated,
            "count": int - number of files migrated,
            "failed": int - number of files that failed,
            "error": str (optional) - error message if migration failed
        }
    """
    result: dict[str, Any] = {
        "migrated": False,
        "count": 0,
        "failed": 0,
    }

    # Check if migration is needed
    if not should_migrate():
        migration_marker = _get_migration_marker()
        logger.debug("migration.not_needed", marker_exists=migration_marker.exists())
        return result

    old_cache_contexts = _get_old_cache_contexts()
    new_memory_root = _get_new_memory_root()

    logger.info(
        "migration.starting",
        old_cache=str(old_cache_contexts),
        new_memory=str(new_memory_root),
    )

    try:
        # Ensure new directory exists
        new_memory_root.mkdir(parents=True, exist_ok=True)

        # List all JSON files in old cache
        cache_files = [
            f
            for f in os.listdir(old_cache_contexts)
            if f.endswith(".json")
        ]

        if not cache_files:
            logger.info("migration.no_files_found", cache_dir=str(old_cache_contexts))
            _mark_migration_done()
            return result

        # Migrate each file
        for filename in cache_files:
            old_file = old_cache_contexts / filename

            try:
                # Read old file to extract repo_url
                with open(old_file, "r", encoding="utf-8") as f:
                    old_data = json.load(f)

                repo_url = old_data.get("repo_url", "unknown")
                repo_hash = _get_repo_hash(repo_url)

                if _migrate_context_file(old_file, repo_url, repo_hash):
                    result["count"] += 1
                else:
                    result["failed"] += 1

            except Exception as e:
                logger.warning(
                    "migration.file_processing_failed",
                    filename=filename,
                    error=str(e),
                )
                result["failed"] += 1

        # Mark migration as done
        _mark_migration_done()
        result["migrated"] = result["count"] > 0

        logger.info(
            "migration.completed",
            count=result["count"],
            failed=result["failed"],
        )
        return result

    except Exception as e:
        logger.exception(
            "migration.failed",
            error=str(e),
        )
        result["error"] = str(e)
        # Still mark as attempted to avoid repeated failures
        _mark_migration_done()
        return result


def _mark_migration_done() -> None:
    """Mark migration as completed to prevent re-running."""
    try:
        old_cache_root = _get_old_cache_root()
        migration_marker = _get_migration_marker()

        old_cache_root.mkdir(parents=True, exist_ok=True)
        migration_marker.touch()
        logger.debug("migration.marker_created", marker=str(migration_marker))
    except Exception as e:
        logger.warning(
            "migration.marker_creation_failed",
            error=str(e),
        )


def migrate_on_startup() -> None:
    """Entry point for migration during application startup.

    This function should be called once during server initialization.
    It gracefully handles migration failures without crashing the server.
    """
    try:
        logger.debug("migration.checking_for_migration_needed")
        result = perform_migration()

        if result.get("migrated"):
            logger.info(
                "migration.success",
                count=result["count"],
                failed=result.get("failed", 0),
            )
        elif "error" in result:
            logger.warning(
                "migration.degraded",
                error=result["error"],
                hint="Continuing with fresh memory system. Old cache will not be imported.",
            )
        else:
            logger.debug("migration.not_needed")

    except Exception as e:
        logger.exception(
            "migration.unexpected_error",
            error=str(e),
            hint="Continuing with fresh memory system.",
        )
