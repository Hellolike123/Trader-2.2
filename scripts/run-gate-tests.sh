#!/usr/bin/env bash
# Trader3.0 CI 门禁测试运行器
# 跑离线、无凭证、确定性的核心回归集。
# 被 scripts/git-hooks/pre-push 调用，也可被 CI 工作流直接调用。
#
# 设计取舍（详见 docs/architecture/ci-gate.md）：
#   - 不跑全量 80+ 测试：其中大量依赖网络/凭证（tushare / tdx / 腾讯），
#     在 CI 与离线环境会红或超时（历史上有沙箱 SIGKILL 137 记录）。
#   - 门禁守的是"行为不变"（等价性闸门），不是"行为正确"——
#     基线若本就带 bug，门禁会把它锁成绿。这是等价性测试的固有代价。
#
# 环境变量：
#   TRADER_CI_PYTHON  覆盖 Python 解释器。未设时解析顺序：
#     Mac 历史 venv（若存在）→ python3 → python；都不可用则非零退出。
#   详见 docs/architecture/ci-gate.md。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Python 解析（G-P1…G-P4）：env → Mac venv if exists → python3 → python → 明确失败
_MAC_VENV="/Users/like/.workbuddy/binaries/python/envs/default/bin/python"

_resolve_python() {
  local candidate=""
  if [[ -n "${TRADER_CI_PYTHON:-}" ]]; then
    candidate="$TRADER_CI_PYTHON"
  elif [[ -x "$_MAC_VENV" ]]; then
    candidate="$_MAC_VENV"
  elif command -v python3 >/dev/null 2>&1; then
    candidate="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    candidate="$(command -v python)"
  else
    echo "error: no usable Python found (set TRADER_CI_PYTHON, or install python3/python)" >&2
    return 1
  fi

  # 可执行性：绝对/相对路径用 -x；否则走 PATH（command -v）
  if [[ "$candidate" == */* ]]; then
    if [[ ! -x "$candidate" ]]; then
      echo "error: Python not executable: $candidate" >&2
      return 1
    fi
  elif ! command -v "$candidate" >/dev/null 2>&1; then
    echo "error: Python not found on PATH: $candidate" >&2
    return 1
  fi

  # G-P4：选定解释器须能跑 import sys
  if ! "$candidate" -c "import sys; print(sys.executable)" >/dev/null 2>&1; then
    echo "error: Python failed smoke check: $candidate" >&2
    return 1
  fi

  printf '%s\n' "$candidate"
}

PYTHON="$(_resolve_python)" || exit 1
echo "gate python: $PYTHON"

# PYTHONPATH 顺序敏感：shared 必须在前，否则 config 会解析到 trader_shared/config.py 导致收集失败
export PYTHONPATH="02-共享模块-shared:01-功能包-packages/trader/scripts"

# 区间套确认需 30m 数据（生产环境本机 eastmoney/tdx 取数），CI/离线不可达；
# 禁用以保证门禁确定性（report_builder 接入点会优雅跳过，等价性闸门成立）。
export TRADER_CHAN_NESTING=0

# 离线稳定核心回归集（锁定）。新增离线测试请显式加入此数组。
# 基线以实际 pytest 计数为准；扩展原则：只加离线/无凭证/确定性用例。
TESTS=(
  "02-共享模块-shared/tests/test_imports_smoke.py"
  "02-共享模块-shared/tests/test_build_report_golden.py"
  "02-共享模块-shared/tests/test_build_report_adr002_equivalence.py"
  "02-共享模块-shared/tests/test_report_render_equivalence.py"
  "02-共享模块-shared/tests/test_arch_refactoring.py"
  "02-共享模块-shared/tests/test_indicator_math.py"
  "02-共享模块-shared/tests/test_fusion_regime_weights.py"
  "02-共享模块-shared/tests/test_p0_signal_structurization.py"
  "02-共享模块-shared/tests/test_p1_global_state.py"
  "02-共享模块-shared/tests/test_plugin_autodiscovery.py"
  "02-共享模块-shared/tests/test_golden_diff_gate.py"
  "02-共享模块-shared/tests/test_box_detect.py"
  "02-共享模块-shared/tests/test_combo_strategy.py"
  "02-共享模块-shared/tests/test_wyckoff_core.py"
  "02-共享模块-shared/tests/test_wyckoff_tr.py"
  "02-共享模块-shared/tests/test_wyckoff_tr_maturity.py"
  "02-共享模块-shared/tests/test_wyckoff_state_view.py"
  "02-共享模块-shared/tests/test_cause_effect_display.py"
  "02-共享模块-shared/tests/test_wyckoff_pnf.py"
  "02-共享模块-shared/tests/test_wyckoff_split_equivalence.py"
  "02-共享模块-shared/tests/test_chan_split_equivalence.py"
  "02-共享模块-shared/tests/test_stage_split_equivalence.py"
  "02-共享模块-shared/trader_shared/test_chan_nesting.py"
  "02-共享模块-shared/trader_shared/test_chan_nesting_chain.py"
  "02-共享模块-shared/trader_shared/test_cache_stale_revalidation.py"
  "01-功能包-packages/trader/tests/test_report_renderer.py"
  # Arch C/D：cards / fusion-from-cards / 六闸策略（防动量席静音、cost_price 等契约）
  "02-共享模块-shared/tests/test_fusion_cards_parity_bugs.py"
  "02-共享模块-shared/tests/test_fusion_path_compare.py"
  "02-共享模块-shared/tests/test_buy_point_lifecycle.py"
  "02-共享模块-shared/tests/test_report_optimization.py"
  "02-共享模块-shared/tests/test_fusion_from_cards.py"
  "02-共享模块-shared/tests/test_strategy_match.py"
  "02-共享模块-shared/tests/test_analysis_opinion_cards_p0.py"
  "02-共享模块-shared/tests/test_arch_boundaries.py"
  "02-共享模块-shared/tests/test_output_template_contract.py"
  "02-共享模块-shared/tests/test_production_path_defaults.py"
  # 架构瘦身后缝：pipeline / attach / t0 引擎（纯离线）
  "02-共享模块-shared/tests/test_report_pipeline.py"
  "02-共享模块-shared/tests/test_attach_offline.py"
  "02-共享模块-shared/tests/test_t0_engine_offline.py"
  "02-共享模块-shared/tests/test_pool_resonance_rank.py"
  "02-共享模块-shared/tests/test_portfolio_resonance.py"
  "02-共享模块-shared/tests/test_daily_ruling_decision_view.py"
  "02-共享模块-shared/tests/test_decision_view.py"
  "02-共享模块-shared/tests/test_fusion_instrument_caps.py"
  "02-共享模块-shared/tests/test_stage_field_discipline.py"
  "02-共享模块-shared/tests/test_structure_core.py"
  "02-共享模块-shared/tests/test_daily_scale_glitch.py"
  # bugfix 回归：review symbol 次序 / signal 首写 mkdir
  "02-共享模块-shared/tests/test_review_core_offline.py"
  "02-共享模块-shared/tests/test_signal_store_changes.py"
  "02-共享模块-shared/tests/test_data_provider.py"
  "02-共享模块-shared/tests/test_context_stage_offline.py"
  "02-共享模块-shared/tests/test_position_add_store.py"
  # 批量路径加速回归（2026-08-06）：refresh 死锁修复 / enrich 预热 / 腾讯 quote 硬超时
  "02-共享模块-shared/tests/test_batch_path_accel.py"
)

exec "$PYTHON" -m pytest -q -p no:cacheprovider "${TESTS[@]}"
