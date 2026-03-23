#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# CodeBook Sprint 2 — Checkpoint Validator
# 用法: ./checkpoint.sh <WAVE>    例如: ./checkpoint.sh W1
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MCP="$REPO_ROOT/mcp-server"
LOG_DIR="$SCRIPT_DIR/logs"
REPORT_DIR="$SCRIPT_DIR/reports"
mkdir -p "$REPORT_DIR"

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; }
info() { echo -e "  ${YELLOW}?${NC} $*"; }
hdr()  { echo -e "\n${BOLD}${CYAN}$*${NC}"; }

# ── 检查文件是否存在 ──
check_file() {
    if [[ -e "$1" ]]; then
        pass "$2: $1"
        return 0
    else
        fail "$2: $1 不存在"
        return 1
    fi
}

# ── 检查目录非空 ──
check_dir_nonempty() {
    if [[ -d "$1" ]] && [[ -n "$(ls -A "$1" 2>/dev/null)" ]]; then
        pass "$2: $1/"
        return 0
    else
        fail "$2: $1/ 不存在或为空"
        return 1
    fi
}

# ── 运行 pytest ──
run_pytest() {
    hdr "回归测试: pytest"
    cd "$MCP"
    if python -m pytest tests/ -x -q 2>&1 | tail -5; then
        pass "pytest 通过"
        return 0
    else
        fail "pytest 失败"
        return 1
    fi
}

# ── Wave 验收 ──
checkpoint() {
    local wave="$1"
    local report="$REPORT_DIR/checkpoint_${wave}.md"
    local errors=0

    echo -e "\n${BOLD}═══ Wave ${wave} 验收检查 ═══${NC}\n"

    case "$wave" in
        W1|w1)
            hdr "A-1: 环境准备"
            check_dir_nonempty "$MCP/repos" "测试仓库目录" || ((errors++))
            for proj in fastapi sentry-python next.js vscode; do
                if [[ -d "$MCP/repos/$proj" ]] || [[ -d "$MCP/repos/"*"$proj"* ]]; then
                    pass "  $proj 已 clone"
                else
                    info "  $proj 未找到（可能用了不同目录名）"
                fi
            done

            hdr "C-1: 测试修复"
            run_pytest

            hdr "D-1a: ProjectMemory 数据模型"
            check_file "$MCP/src/memory/__init__.py" "memory 包" || ((errors++))
            check_file "$MCP/src/memory/models.py" "数据模型" || ((errors++))
            check_file "$MCP/src/memory/project_memory.py" "ProjectMemory 核心" || ((errors++))

            hdr "D-1b: 迁移 + RepoCache 集成"
            check_file "$MCP/src/memory/migration.py" "迁移脚本" || ((errors++))

            hdr "日志检查"
            for t in A-1 C-1 D-1a D-1b; do
                check_file "$LOG_DIR/${t}.log" "$t 执行日志" || ((errors++))
            done
            ;;

        W2|w2)
            hdr "A-2: scan_repo 压测结果"
            check_dir_nonempty "$MCP/test_results" "测试结果目录" || ((errors++))
            check_file "$MCP/test_results/scan_repo_summary.md" "压测汇总报告" || ((errors++))

            hdr "B-1: 角色系统设计"
            check_file "$REPO_ROOT/docs/role_system_v3_design.md" "角色设计文档" || ((errors++))

            hdr "D-2a: 术语飞轮核心"
            check_file "$MCP/src/glossary/__init__.py" "glossary 包" || ((errors++))
            check_file "$MCP/src/glossary/term_store.py" "TermStore" || ((errors++))
            check_file "$MCP/src/glossary/term_resolver.py" "TermResolver" || ((errors++))
            check_dir_nonempty "$MCP/domain_packs" "行业术语包" || ((errors++))

            hdr "D-2b: engine 集成"
            check_file "$MCP/src/tools/term_correct.py" "term_correct tool" || ((errors++))

            hdr "回归测试"
            run_pytest

            hdr "日志检查"
            for t in A-2 B-1 D-2a D-2b; do
                check_file "$LOG_DIR/${t}.log" "$t 执行日志" || ((errors++))
            done

            echo ""
            echo -e "${YELLOW}═══ 决策提醒 ═══${NC}"
            echo "  查看 test_results/scan_repo_summary.md 后决策:"
            echo "  D-001: 增量扫描 vs lazy loading"
            echo "  D-002: Mermaid 图密度处理方式"
            ;;

        W3|w3)
            hdr "A-3: RC + diagnose 压测"
            # 检查是否有新的测试结果文件
            local rc_count=$(find "$MCP/test_results" -name "*read_chapter*" -o -name "*diagnose*" 2>/dev/null | wc -l)
            if [[ $rc_count -gt 0 ]]; then
                pass "RC/diagnose 测试结果: $rc_count 个文件"
            else
                fail "未找到 RC/diagnose 测试结果"
                ((errors++))
            fi

            hdr "B-2a/b: 角色系统实现"
            # 检查角色系统是否有变更
            if grep -q "domain_expert\|dev.*pm" "$MCP/src/tools/ask_about.py" 2>/dev/null; then
                pass "ask_about.py 包含新角色逻辑"
            else
                info "ask_about.py 角色逻辑待确认"
            fi

            hdr "D-3: 记忆持久化"
            check_file "$MCP/src/tools/memory_feedback.py" "memory_feedback tool" || ((errors++))

            hdr "回归测试"
            run_pytest

            hdr "日志检查"
            for t in A-3 B-2a B-2b D-3; do
                check_file "$LOG_DIR/${t}.log" "$t 执行日志" || ((errors++))
            done
            ;;

        W4|w4)
            hdr "A-4: ask_about + codegen 压测"
            local aa_count=$(find "$MCP/test_results" -name "*ask_about*" -o -name "*codegen*" 2>/dev/null | wc -l)
            if [[ $aa_count -gt 0 ]]; then
                pass "ask_about/codegen 测试结果: $aa_count 个文件"
            else
                fail "未找到 ask_about/codegen 测试结果"
                ((errors++))
            fi

            hdr "C-2: CI Pipeline"
            check_file "$REPO_ROOT/.github/workflows/test.yml" "CI 配置" || ((errors++))
            if [[ -s "$REPO_ROOT/README.md" ]]; then
                pass "README.md 非空"
            else
                fail "README.md 为空或不存在"
                ((errors++))
            fi

            hdr "D-4: 智能记忆"
            if grep -q "infer_from_qa_history\|detect_hotspots\|incremental" "$MCP/src/glossary/term_resolver.py" 2>/dev/null || \
               grep -q "infer_from_qa_history\|detect_hotspots" "$MCP/src/memory/"*.py 2>/dev/null; then
                pass "智能记忆功能代码存在"
            else
                info "智能记忆功能待确认（可能文件名不同）"
            fi

            hdr "回归测试"
            run_pytest

            hdr "日志检查"
            for t in A-4 C-2 D-4; do
                check_file "$LOG_DIR/${t}.log" "$t 执行日志" || ((errors++))
            done
            ;;

        W6|w6)
            hdr "W6: 最终集成验证"
            check_file "$MCP/test_results/integration_test_report.md" "集成测试报告" || ((errors++))

            hdr "文档完整性"
            for doc in CONTEXT.md INTERFACES.md; do
                check_file "$REPO_ROOT/files/$doc" "$doc" || ((errors++))
            done
            check_file "$REPO_ROOT/docs/sprint2_quality_report.md" "质量评估报告" || ((errors++))

            hdr "最终 pytest"
            run_pytest

            hdr "验收指标确认"
            echo "  请人工确认以下指标:"
            echo "  □ pytest 通过率 ≥ 99%, 0 skip"
            echo "  □ PM 翻译质量 ≥ 9.0/10"
            echo "  □ scan_repo 中型 < 60s"
            echo "  □ diagnose 命中率 ≥ 80%"
            echo "  □ codegen diff_valid ≥ 90%"
            echo "  □ domain_expert 可用且翻译合理"
            echo "  □ 术语纠正 → 生效端到端通过"
            echo "  □ 记忆跨会话保留"
            echo "  □ CI 绿色"

            hdr "日志检查"
            for t in A-5 W6-1a W6-1b W6-2; do
                check_file "$LOG_DIR/${t}.log" "$t 执行日志" || ((errors++))
            done
            ;;

        *)
            echo "用法: $0 <W1|W2|W3|W4|W6>"
            exit 1
            ;;
    esac

    # ── 汇总 ──
    echo ""
    if [[ $errors -eq 0 ]]; then
        echo -e "${GREEN}${BOLD}═══ Wave $wave 验收通过 (0 问题) ═══${NC}"
    else
        echo -e "${RED}${BOLD}═══ Wave $wave 发现 $errors 个问题 ═══${NC}"
    fi

    # 写报告
    echo "# Wave $wave 验收报告" > "$report"
    echo "日期: $(date '+%Y-%m-%d %H:%M')" >> "$report"
    echo "问题数: $errors" >> "$report"
    echo "" >> "$report"
    echo "详细输出见终端。" >> "$report"

    echo -e "\n报告已保存: $report"
    return $errors
}

checkpoint "${1:-help}"
