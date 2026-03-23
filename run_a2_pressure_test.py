#!/usr/bin/env python3
"""
Task A-2: Pressure test scan_repo on 4 projects (overview mode).

This script runs scan_repo with depth='overview' on:
1. FastAPI (medium, 2,952 files, 356k lines)
2. Sentry Python SDK (medium-large, 534 files, 150k lines)
3. Next.js (large, 28k files, 144k lines)
4. VS Code (super-large, 10k files, 600k lines)

Results are saved to test_results/{name}/scan_repo.json with structure:
{
  "性能": {"scan_time_seconds": N, "step_times": {...}, ...},
  "规模": {"modules": N, "functions": N, ...},
  "质量": {"mermaid_nodes": N, "mermaid_readable": "...", ...}
}
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

# Add mcp-server to path
import sys
sys.path.insert(0, '/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server')

from src.tools.scan_repo import scan_repo

# Projects to test, ordered by size (small to large)
PROJECTS = [
    ("fastapi", "/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/fastapi"),
    ("sentry-python", "/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/sentry-python"),
    ("nextjs", "/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/nextjs"),
    ("vscode", "/sessions/nice-sweet-feynman/mnt/CodeBook/mcp-server/repos/vscode"),
]

TEST_RESULTS_DIR = Path("/sessions/nice-sweet-feynman/mnt/CodeBook/test_results")

# Timeout per project (seconds)
TIMEOUTS = {
    "fastapi": 300,  # 5 min
    "sentry-python": 300,  # 5 min
    "nextjs": 600,  # 10 min
    "vscode": 600,  # 10 min (might be longer)
}


def format_step_times(step_times: dict[str, float]) -> str:
    """Format step times for display."""
    lines = []
    for step, duration in step_times.items():
        lines.append(f"  {step}: {duration:.2f}s")
    return "\n".join(lines)


def evaluate_mermaid_quality(mermaid: str | None) -> tuple[int, str]:
    """Evaluate Mermaid diagram quality (1-10 scale).

    Returns (score, reasoning).
    """
    if not mermaid:
        return 1, "Empty Mermaid diagram"

    lines = mermaid.split("\n")
    if len(lines) < 3:
        return 2, "Very few nodes/edges"

    # Count nodes and edges
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
    """Evaluate module grouping quality (1-10 scale).

    Returns (score, list of poorly grouped modules if any).
    """
    if not modules:
        return 1, ["No modules detected"]

    issues = []

    # Check for outliers (very large or very small modules)
    total_lines = [m.get("total_lines", 0) for m in modules if isinstance(m, dict)]
    if total_lines:
        avg_lines = sum(total_lines) / len(total_lines)
        for m in modules:
            if isinstance(m, dict):
                name = m.get("name", "unknown")
                lines = m.get("total_lines", 0)
                # Check if module is >3x average size
                if lines > avg_lines * 3:
                    issues.append(f"{name} ({lines} lines, {lines/avg_lines:.1f}x average)")

    if not issues:
        return 9, []
    elif len(issues) <= 2:
        return 7, issues
    else:
        return 5, issues[:5]  # Limit to 5 for brevity


async def run_pressure_test():
    """Run scan_repo on all 4 projects and record results."""

    print("\n" + "="*80)
    print("Task A-2: Pressure Test - scan_repo (overview mode)")
    print("="*80)

    all_results = {}

    for project_name, repo_path in PROJECTS:
        print(f"\n{'─'*80}")
        print(f"Project: {project_name}")
        print(f"Path: {repo_path}")
        print(f"Timeout: {TIMEOUTS[project_name]}s")
        print(f"{'─'*80}")

        result_dir = TEST_RESULTS_DIR / project_name
        result_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Run scan_repo with timeout
            print(f"Running scan_repo (overview)...")
            test_start = time.time()

            result = await asyncio.wait_for(
                scan_repo(repo_url=repo_path, role="pm", depth="overview"),
                timeout=TIMEOUTS[project_name]
            )

            total_time = time.time() - test_start

            if result.get("status") != "ok":
                print(f"ERROR: {result.get('error', 'Unknown error')}")
                all_results[project_name] = {
                    "status": "error",
                    "error": result.get("error"),
                    "total_time": total_time,
                }
                continue

            print(f"✓ Success in {total_time:.2f}s")

            # Extract stats
            stats = result.get("stats", {})
            modules = result.get("modules", [])
            mermaid = result.get("mermaid_diagram", "")

            # Evaluate quality metrics
            mermaid_nodes = mermaid.count(" --> ") if mermaid else 0
            mermaid_score, mermaid_reason = evaluate_mermaid_quality(mermaid)
            module_score, poorly_grouped = evaluate_module_grouping(modules)

            # Count health distribution
            health_dist = {"green": 0, "yellow": 0, "red": 0}
            for m in modules:
                if isinstance(m, dict):
                    health = m.get("health", "green")
                    if health in health_dist:
                        health_dist[health] += 1

            # Build output structure
            output = {
                "性能": {
                    "scan_time_seconds": stats.get("scan_time_seconds", total_time),
                    "step_times": stats.get("step_times", {}),
                    "memory_peak_mb": None,  # Not available in current impl
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

            # Save to JSON
            output_file = result_dir / "scan_repo.json"
            with open(output_file, "w") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

            print(f"✓ Results saved to {output_file}")

            # Print summary
            print(f"\nSummary:")
            print(f"  Files: {stats.get('files', '?')}")
            print(f"  Code Files: {stats.get('code_files', '?')}")
            print(f"  Modules: {stats.get('modules', '?')}")
            print(f"  Functions: {stats.get('functions', '?')}")
            print(f"  Classes: {stats.get('classes', '?')}")
            print(f"  Total Lines: {stats.get('total_lines', '?')}")
            print(f"  Scan Time: {stats.get('scan_time_seconds', total_time):.2f}s")
            if stats.get("step_times"):
                print(f"\nStep Times:")
                print(format_step_times(stats["step_times"]))
            print(f"\nQuality Metrics:")
            print(f"  Mermaid Nodes: {mermaid_nodes}")
            print(f"  Mermaid Quality: {mermaid_score}/10 - {mermaid_reason}")
            print(f"  Health Distribution: {health_dist}")
            print(f"  Module Grouping: {module_score}/10")
            if poorly_grouped:
                print(f"    Concerns: {', '.join(poorly_grouped[:3])}")

            all_results[project_name] = {
                "status": "ok",
                "scan_time": stats.get("scan_time_seconds", total_time),
                "modules": stats.get("modules", 0),
            }

        except asyncio.TimeoutError:
            print(f"TIMEOUT: scan_repo exceeded {TIMEOUTS[project_name]}s")
            all_results[project_name] = {
                "status": "timeout",
                "timeout_seconds": TIMEOUTS[project_name],
            }
        except Exception as e:
            print(f"EXCEPTION: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            all_results[project_name] = {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

    # Print summary table
    print("\n" + "="*80)
    print("Summary Table (all projects)")
    print("="*80)
    print(f"{'Project':<20} {'Status':<12} {'Time (s)':<12} {'Modules':<12}")
    print("-" * 56)
    for name, result in all_results.items():
        status = result.get("status", "unknown").upper()
        time_str = f"{result.get('scan_time', 0):.2f}" if result.get("status") == "ok" else "—"
        modules = str(result.get("modules", "—")) if result.get("status") == "ok" else "—"
        print(f"{name:<20} {status:<12} {time_str:<12} {modules:<12}")

    print("\n✓ Task A-2 complete!\n")


if __name__ == "__main__":
    asyncio.run(run_pressure_test())
