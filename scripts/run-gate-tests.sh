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
#   TRADER_CI_PYTHON  覆盖 Python 解释器（默认用本机 venv；CI runner 设此变量指向其 python）
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${TRADER_CI_PYTHON:-/Users/like/.workbuddy/binaries/python/envs/default/bin/python}"
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
)

exec "$PYTHON" -m pytest -q -p no:cacheprovider "${TESTS[@]}"
