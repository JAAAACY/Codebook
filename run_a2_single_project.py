#!/usr/bin/env python3
"""
Task A-2: Pressure test scan_repo on a single project (overview mode).

Usage: python run_a2_single_project.py <project_name>
  where project_name is one of: fastapi, sentry-python, nextjs, vscode
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, '/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server')

from src.tools.scan_repo import scan_repo

PROJECTS = {
    "fastapi": "/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/fastapi",
    "sentry-python": "/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/sentry-python",
    "nextjs": "/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/nextjs",
    "vscode": "/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/vscode",
}

TIMEOUTS = {
    "fastapi": 300,
    "sentry-python": 300,
    "nextjs": 600,
    "vscode": 600,
}

TEST_RESULTS_DIR = Path("/sessions/nice-sweet-feynman/mnt/CodeBook/test_results")


def evaluate_mermaid_quality(mermaid: str | None) -> tuple[int, str]:
    """Evaluate Mermaid diagram quality (1-10 scale)."""
    if not mermaid:
        return 1, "Empty Mermaid diagram"

    lines = mermaid.split("\n")
    node_count = sum(1 for line in lines if " --> " in line)

    if node_count == 0:
        return 3, "No visible connections"
    elif node_count > 100:
        return 6, f"Dense graph ({node_count} edges) - may be hard to read"
    elif node_count > 50:
        return 7, f"Complex ({node_count} edges) but navigable"
    elif node_count > 20:
        return 8, f"Well-balanced ({node_count} edges)"
    else:
        return 9, f"Clear and concise ({node_count} edges)"


def evaluate_module_grouping(modules: list[dict]) -> tuple[int, list[str]]:
    """Evaluate module grouping quality (1-10 scale)."""
    if not modules:
        return 1, ["No modules detected"]

    issues = []
    total_lines = [m.get("total_lines", 0) for m in modules if isinstance(m, dict)]

    if total_lines:
        avg_lines = sum(total_lines) / len(total_lines)
        for m in modules:
            if isinstance(m, dict):
                name = m.get("name", "unknown")
                lines = m.get("total_lines", 0)
                if lines > avg_lines * 3:
                    issues.append(f"{name} ({lines} lines, {lines/avg_lines:.1f}x average)")

    if not issues:
        return 9, []
    elif len(issues) <= 2:
        return 7, issues
    else:
        return 5, issues[:5]


async def test_project(project_name: str):
    """Run scan_repo on a single project."""

    if project_name not in PROJECTS:
        print(f"ERROR: Unknown project '{project_name}'")
        print(f"Available: {', '.join(PROJECTS.keys())}")
        sys.exit(1)

    repo_path = PROJECTS[project_name]
    timeout = TIMEOUTS[project_name]

    print(f"\n{'='*80}")
    print(f"Pressure Test: {project_name}")
    print(f"Path: {repo_path}")
    print(f"Timeout: {timeout}s")
    print(f"{'='*80}\n")

    result_dir = TEST_RESULTS_DIR / project_name
    result_dir.mkdir(parents=True, exist_ok=True)

    try:
        print("Running scan_repo (overview)...")
        test_start = time.time()

        result = await asyncio.wait_for(
            scan_repo(repo_url=repo_path, role="pm", depth="overview"),
            timeout=timeout
        )

        total_time = time.time() - test_start

        if result.get("status") != "ok":
            print(f"ERROR: {result.get('error', 'Unknown error')}")
            error_output = {
                "status": "error",
                "error": result.get("error"),
                "total_time": total_time,
            }
            with open(result_dir / "scan_repo.json", "w") as f:
                json.dump(error_output, f, indent=2)
            return

        print(f"✓ Complete in {total_time:.2f}s\n")

        # Extract data
        stats = result.get("stats", {})
        modules = result.get("modules", [])
        mermaid = result.get("mermaid_diagram", "")

        # Evaluate metrics
        mermaid_nodes = mermaid.count(" --> ") if mermaid else 0
        mermaid_score, mermaid_reason = evaluate_mermaid_quality(mermaid)
        module_score, poorly_grouped = evaluate_module_grouping(modules)

        # Health distribution
        health_dist = {"green": 0, "yellow": 0, "red": 0}
        for m in modules:
            if isinstance(m, dict):
                health = m.get("health", "green")
                if health in health_dist:
                    health_dist[health] += 1

        # Build output
        output = {
            "性能": {
                "scan_time_seconds": stats.get("scan_time_seconds", total_time),
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
                "mermaid_nodes": mermaid_nodes,
                "mermaid_readable": f"{mermaid_score}/10: {mermaid_reason}",
                "health_distribution": health_dist,
                "module_grouping_score": f"{module_score}/10" + (
                    f" (concerns: {', '.join(poorly_grouped[:3])})"
                    if poorly_grouped else ""
                ),
                "error": None,
                "edge_cases": None,
            },
        }

        # Save
        output_file = result_dir / "scan_repo.json"
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"Results saved to: {output_file}\n")

        # Print summary
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Files: {stats.get('files', '?')}")
        print(f"Code Files: {stats.get('code_files', '?')}")
        print(f"Modules: {stats.get('modules', '?')}")
        print(f"Functions: {stats.get('functions', '?')}")
        print(f"Classes: {stats.get('classes', '?')}")
        print(f"Total Lines: {stats.get('total_lines', '?')}")
        print(f"Scan Time: {stats.get('scan_time_seconds', total_time):.2f}s")

        if stats.get("step_times"):
            print(f"\nStep Times:")
            for step, duration in stats["step_times"].items():
                print(f"  {step}: {duration:.2f}s")

        print(f"\nQuality:")
        print(f"  Mermaid Nodes: {mermaid_nodes}")
        print(f"  Mermaid Quality: {mermaid_score}/10")
        print(f"  Module Grouping: {module_score}/10")
        print(f"  Health Distribution: {health_dist}")

        if poorly_grouped:
            print(f"  Grouping Concerns:")
            for issue in poorly_grouped[:3]:
                print(f"    - {issue}")

    except asyncio.TimeoutError:
        print(f"TIMEOUT: scan_repo exceeded {timeout}s")
        error_output = {
            "status": "timeout",
            "timeout_seconds": timeout,
        }
        with open(result_dir / "scan_repo.json", "w") as f:
            json.dump(error_output, f, indent=2)

    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        error_output = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
        }
        with open(result_dir / "scan_repo.json", "w") as f:
            json.dump(error_output, f, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_a2_single_project.py <project_name>")
        print(f"Available projects: {', '.join(PROJECTS.keys())}")
        sys.exit(1)

    project = sys.argv[1]
    asyncio.run(test_project(project))
