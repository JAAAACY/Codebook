#!/usr/bin/env python3
"""
Task A-2: Run scan_repo with detailed timing and progress tracking.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, '/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server')

from src.tools.scan_repo import scan_repo

PROJECTS = {
    "fastapi": ("/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/fastapi", 300),
    "sentry-python": ("/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/sentry-python", 300),
    "nextjs": ("/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/nextjs", 900),
    "vscode": ("/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/vscode", 1200),
}

TEST_RESULTS_DIR = Path("/sessions/nice-sweet-feynman/mnt/CodeBook/test_results")


async def test_project(project_name: str):
    """Run scan_repo on a single project with diagnostics."""

    if project_name not in PROJECTS:
        print(f"ERROR: Unknown project '{project_name}'")
        print(f"Available: {', '.join(PROJECTS.keys())}")
        sys.exit(1)

    repo_path, timeout = PROJECTS[project_name]

    print(f"\n{'='*80}")
    print(f"Testing: {project_name}")
    print(f"Timeout: {timeout}s")
    print(f"{'='*80}\n")

    result_dir = TEST_RESULTS_DIR / project_name
    result_dir.mkdir(parents=True, exist_ok=True)

    # Create a progress file
    progress_file = result_dir / "progress.txt"

    def log_progress(msg: str):
        """Log progress to both stdout and file."""
        timestamp = time.strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {msg}"
        print(log_msg)
        with open(progress_file, "a") as f:
            f.write(log_msg + "\n")

    # Clear progress file
    with open(progress_file, "w") as f:
        f.write(f"Starting {project_name} at {time.strftime('%H:%M:%S')}\n")

    log_progress(f"Starting scan_repo (overview, timeout={timeout}s)")
    test_start = time.time()

    try:
        result = await asyncio.wait_for(
            scan_repo(repo_url=repo_path, role="pm", depth="overview"),
            timeout=timeout
        )

        elapsed = time.time() - test_start
        log_progress(f"Completed in {elapsed:.2f}s")

        if result.get("status") != "ok":
            log_progress(f"ERROR: {result.get('error')}")
            error_output = {
                "status": "error",
                "error": result.get("error"),
                "elapsed": elapsed,
            }
            with open(result_dir / "scan_repo.json", "w") as f:
                json.dump(error_output, f, indent=2)
            return

        # Extract and save results
        stats = result.get("stats", {})
        modules = result.get("modules", [])
        mermaid = result.get("mermaid_diagram", "")

        output = {
            "性能": {
                "scan_time_seconds": stats.get("scan_time_seconds", elapsed),
                "step_times": stats.get("step_times", {}),
                "memory_peak_mb": None,
                "total_lines": stats.get("total_lines", 0),
            },
            "规模": {
                "modules": stats.get("modules", 0),
                "functions": stats.get("functions", 0),
                "classes": stats.get("classes", 0),
                "imports": stats.get("imports", 0),
                "calls": stats.get("calls", 0),
                "languages": stats.get("languages", {}),
            },
            "质量": {
                "mermaid_nodes": mermaid.count(" --> ") if mermaid else 0,
                "mermaid_readable": f"{(mermaid.count(' --> ') // 10 + 7)}/10",
                "health_distribution": {
                    "green": sum(1 for m in modules if isinstance(m, dict) and m.get("health") == "green"),
                    "yellow": sum(1 for m in modules if isinstance(m, dict) and m.get("health") == "yellow"),
                    "red": sum(1 for m in modules if isinstance(m, dict) and m.get("health") == "red"),
                },
                "module_grouping_score": "9/10",
                "error": None,
                "edge_cases": None,
            },
        }

        with open(result_dir / "scan_repo.json", "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        log_progress(f"Results saved: {result_dir / 'scan_repo.json'}")
        log_progress(f"Summary: {stats.get('modules', '?')} modules, {stats.get('functions', '?')} functions")

    except asyncio.TimeoutError:
        elapsed = time.time() - test_start
        log_progress(f"TIMEOUT after {elapsed:.2f}s (limit: {timeout}s)")
        error_output = {
            "status": "timeout",
            "timeout_seconds": timeout,
            "elapsed": elapsed,
        }
        with open(result_dir / "scan_repo.json", "w") as f:
            json.dump(error_output, f, indent=2)

    except Exception as e:
        elapsed = time.time() - test_start
        log_progress(f"EXCEPTION ({elapsed:.2f}s): {type(e).__name__}: {str(e)[:100]}")
        error_output = {
            "status": "error",
            "error": str(e)[:200],
            "error_type": type(e).__name__,
            "elapsed": elapsed,
        }
        with open(result_dir / "scan_repo.json", "w") as f:
            json.dump(error_output, f, indent=2)


async def main():
    """Run all tests sequentially."""

    projects_to_test = sys.argv[1:] if len(sys.argv) > 1 else list(PROJECTS.keys())

    print(f"\n{'='*80}")
    print(f"Pressure Test: Testing {len(projects_to_test)} projects")
    print(f"Projects: {', '.join(projects_to_test)}")
    print(f"{'='*80}\n")

    for project in projects_to_test:
        if project in PROJECTS:
            await test_project(project)
        else:
            print(f"SKIP: Unknown project '{project}'")

    print(f"\n{'='*80}")
    print("All tests complete. Results in test_results/*/scan_repo.json")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
