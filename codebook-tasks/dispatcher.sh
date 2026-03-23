#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# CodeBook Sprint 2 — Task Dispatcher
# 用法: ./dispatcher.sh <WAVE>    例如: ./dispatcher.sh W1
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPTS="$SCRIPT_DIR/prompts"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOCK_DIR="$SCRIPT_DIR/.locks"
mkdir -p "$LOG_DIR" "$LOCK_DIR"

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }

# ── 检查 claude CLI ──
if ! command -v claude &>/dev/null; then
    err "claude CLI 未安装。请先安装 Claude Code: https://docs.claude.com/claude-code"
    exit 1
fi

# ── 执行单个任务 ──
run_task() {
    local task_id="$1"
    local prompt_file="$PROMPTS/${task_id}.md"
    local log_file="$LOG_DIR/${task_id}.log"
    local lock_file="$LOCK_DIR/${task_id}.done"

    # 已完成的跳过
    if [[ -f "$lock_file" ]]; then
        ok "$task_id 已完成，跳过"
        return 0
    fi

    if [[ ! -f "$prompt_file" ]]; then
        err "$task_id: 找不到 prompt 文件 $prompt_file"
        return 1
    fi

    log "启动 $task_id ..."
    local start_time=$(date +%s)

    # 用 claude CLI 执行，工作目录设为 repo root
    if claude -p "$(cat "$prompt_file")" \
        --allowedTools "Bash,Read,Write,Edit,Glob,Grep" \
        > "$log_file" 2>&1; then

        local end_time=$(date +%s)
        local duration=$(( end_time - start_time ))
        touch "$lock_file"
        ok "$task_id 完成 (${duration}s) → $log_file"
        return 0
    else
        local end_time=$(date +%s)
        local duration=$(( end_time - start_time ))
        err "$task_id 失败 (${duration}s) → 查看 $log_file"
        return 1
    fi
}

# ── 并行执行多个任务 ──
run_parallel() {
    local pids=()
    local tasks=("$@")
    local failed=0

    for task in "${tasks[@]}"; do
        run_task "$task" &
        pids+=($!)
        log "  ↳ $task (PID: ${pids[-1]})"
    done

    # 等待所有并行任务
    for i in "${!pids[@]}"; do
        if ! wait "${pids[$i]}"; then
            err "任务 ${tasks[$i]} 失败"
            failed=1
        fi
    done

    return $failed
}

# ── 串行执行（a 完成后执行 b）──
run_serial() {
    for task in "$@"; do
        if ! run_task "$task"; then
            err "串行链中 $task 失败，中止后续任务"
            return 1
        fi
    done
}

# ── 等待前置任务 ──
wait_for() {
    local dep="$1"
    local lock_file="$LOCK_DIR/${dep}.done"
    if [[ ! -f "$lock_file" ]]; then
        err "前置任务 $dep 未完成。请先运行对应 Wave。"
        exit 1
    fi
}

# ── Wave 定义 ──
run_wave() {
    local wave="$1"

    case "$wave" in
        W0|w0)
            log "═══ Wave 0: 全员对齐 ═══"
            run_task "W0-1"
            echo ""
            ok "Wave 0 完成。请确认对齐记录无偏差后继续: ./dispatcher.sh W1"
            ;;

        W1|w1)
            log "═══ Wave 1: 环境准备 + 测试修复 + 存储层 ═══"
            wait_for "W0-1"

            # A-1, C-1, D-1a 并行
            log "并行启动: A-1 / C-1 / D-1a"
            run_parallel "A-1" "C-1" "D-1a"

            # D-1b 串行（依赖 D-1a）
            log "串行启动: D-1b（依赖 D-1a）"
            run_task "D-1b"

            echo ""
            ok "Wave 1 完成。"
            warn ">>> 验收节点 #1: ./checkpoint.sh W1"
            ;;

        W2|w2)
            log "═══ Wave 2: 压测 + 角色设计 + 术语飞轮 ═══"
            wait_for "A-1"; wait_for "C-1"; wait_for "D-1b"

            # A-2, B-1, D-2a 并行
            log "并行启动: A-2 / B-1 / D-2a"
            run_parallel "A-2" "B-1" "D-2a"

            # D-2b 串行（依赖 D-2a）
            log "串行启动: D-2b（依赖 D-2a）"
            run_task "D-2b"

            echo ""
            ok "Wave 2 完成。"
            warn ">>> 验收节点 #2: ./checkpoint.sh W2"
            warn ">>> 决策节点: D-001 (增量扫描) 和 D-002 (Mermaid密度) 需要你根据 A-2 数据做决策"
            ;;

        W3|w3)
            log "═══ Wave 3: 深度压测 + 角色实现 + 记忆持久化 ═══"
            wait_for "A-2"; wait_for "B-1"; wait_for "D-2b"

            # A-3, D-3 并行; B-2a 也并行
            log "并行启动: A-3 / B-2a / D-3"
            run_parallel "A-3" "B-2a" "D-3"

            # B-2b 串行（依赖 B-2a）
            log "串行启动: B-2b（依赖 B-2a）"
            run_task "B-2b"

            echo ""
            ok "Wave 3 完成。"
            warn ">>> 验收节点 #3: ./checkpoint.sh W3"
            ;;

        W4|w4)
            log "═══ Wave 4: 全链路压测 + CI + 智能记忆 ═══"
            wait_for "A-3"; wait_for "B-2b"; wait_for "D-3"

            # A-4, C-2, D-4 并行
            log "并行启动: A-4 / C-2 / D-4"
            run_parallel "A-4" "C-2" "D-4"

            echo ""
            ok "Wave 4 完成。"
            warn ">>> 验收节点 #4: ./checkpoint.sh W4"
            ;;

        W5|w5)
            log "═══ Wave 5: 瓶颈优化 ═══"
            wait_for "A-4"; wait_for "C-2"; wait_for "D-4"

            run_task "A-5"

            echo ""
            ok "Wave 5 完成。继续: ./dispatcher.sh W6"
            ;;

        W6|w6)
            log "═══ Wave 6: 跨线集成验证 ═══"
            wait_for "A-5"

            # W6-1a → W6-1b 串行
            log "串行启动: W6-1a → W6-1b"
            run_serial "W6-1a" "W6-1b"

            # W6-2 串行
            run_task "W6-2"

            echo ""
            ok "Wave 6 完成。Sprint 2 全部任务执行完毕！"
            warn ">>> 最终验收: ./checkpoint.sh W6"
            ;;

        all)
            log "═══ 全自动执行模式（W0 → W6）═══"
            warn "将按 Wave 顺序执行所有任务。每个验收节点会暂停等待确认。"
            echo ""
            for w in W0 W1 W2 W3 W4 W5 W6; do
                run_wave "$w"
                if [[ "$w" == "W1" || "$w" == "W2" || "$w" == "W3" || "$w" == "W4" || "$w" == "W6" ]]; then
                    echo ""
                    warn "到达验收节点。运行 ./checkpoint.sh $w 确认后，按回车继续..."
                    read -r
                fi
            done
            ok "Sprint 2 全部完成！"
            ;;

        status)
            log "═══ 任务完成状态 ═══"
            for f in "$PROMPTS"/*.md; do
                local tid=$(basename "$f" .md)
                if [[ -f "$LOCK_DIR/${tid}.done" ]]; then
                    ok "$tid"
                else
                    echo "  ⬜ $tid"
                fi
            done
            ;;

        reset)
            warn "清除所有完成标记（不删除日志）"
            rm -f "$LOCK_DIR"/*.done
            ok "已重置"
            ;;

        *)
            echo "用法: $0 <W0|W1|W2|W3|W4|W5|W6|all|status|reset>"
            echo ""
            echo "  W0-W6  : 执行指定 Wave"
            echo "  all    : 全自动执行（验收节点暂停）"
            echo "  status : 查看任务完成状态"
            echo "  reset  : 清除完成标记重新执行"
            exit 1
            ;;
    esac
}

# ── 入口 ──
cd "$REPO_ROOT"
run_wave "${1:-help}"
