# CI 门禁（pre-push gate）

> 把"本地安全网"变成"强制安全网"——每次 `git push` 前自动跑离线核心回归集，红则拦截。

## 为什么是 pre-push hook 而不是服务端 CI

- 远程是 **Gitee**（`gitee.com/hellolike123/Trader-2.2.git`），GitHub Actions 不触发；Gitee Go 需网页配置 + runner，不能纯文件启用。
- 本地 `pre-push` hook **零外部依赖、立即生效、每次 push 前拦截**，恰好覆盖"别人/未来推送绕过测试"的场景。
- 门禁范围与命令与 CI 完全一致（`scripts/run-gate-tests.sh`），将来迁 GitHub Actions / 启用 Gitee Go 可直接复用，无需重写。

## 启用方式

```bash
git config core.hooksPath scripts/git-hooks
```

hook 已随仓库版本化提交，clone 后需各机执行一次上面这行（git 不自动应用 hooksPath）。

## 门禁范围（锁定）

跑 `scripts/run-gate-tests.sh` 里 `TESTS` 数组列出的文件（**离线、无凭证、确定性**）。条数以脚本实际跑出的 pytest 计数为准（约 **300+** / 数秒级；随用例增减会变）。

### 主路径 / 等价性

| 文件 | 守护内容 |
|---|---|
| `test_imports_smoke.py` | 核心子模块 + 公开 API 导入冒烟 |
| `test_build_report_golden.py` | `build_report` 行为回归 |
| `test_build_report_adr002_equivalence.py` | ADR-002 路由后逐字段等价 |
| `test_report_render_equivalence.py` | 渲染与 `fixtures/report_render_baseline.txt` 逐字节一致 |
| `test_golden_diff_gate.py` | golden-diff（渲染 + 字段双比对） |
| `test_arch_refactoring.py` | 架构重构 / PluginRegistry |
| `test_indicator_math.py` | 指标数学 |
| `test_fusion_regime_weights.py` / `test_p0_signal_structurization.py` / `test_p1_global_state.py` / `test_plugin_autodiscovery.py` | 融合与信号契约 |
| `test_box_detect.py` / `test_combo_strategy.py` | 箱体 / 组合策略 |
| `test_wyckoff_*` / `test_chan_split_*` / `test_stage_split_*` | 拆分等价；含 `test_wyckoff_tr_maturity` / state_view / cause_effect / pnf（L0–L3 量度闸，离线） |
| `trader_shared/test_chan_nesting*.py` / `test_cache_stale_revalidation.py` | 区间套 / 缓存 |
| `01-功能包-packages/trader/tests/test_report_renderer.py` | 旧 renderer 包 |

### Arch C/D（分析卡 / 策略闸 / 包边界）

| 文件 | 守护内容 |
|---|---|
| `test_fusion_cards_parity_bugs.py` | 动量卡生产形态、**默认 cards**、类二买、nesting、cost_price、止损不松于结构 |
| `test_fusion_path_compare.py` | classic vs cards 对账纯逻辑（无网） |
| `test_fusion_from_cards.py` | cards / classic / compare 输入路径 |
| `test_strategy_match.py` | 六闸匹配契约 |
| `test_analysis_opinion_cards_p0.py` | 意见卡 shape / 数值有限 |
| `test_arch_boundaries.py` | analysis ↔ strategy 包边界红线 |

**故意不跑全量测试**：其中大量依赖网络/凭证（`test_tushare_integration`、`test_tdx3_provider` 等），在 CI 与离线环境会红或超时。强行全量会让门禁永远红、失去报警意义。

## Golden-diff 闸门（P3）

`scripts/golden_diff_gate.py` 是统一闸门（seam：`trader_shared/testing/mock_seam.py`）：

- `capture`：重抓 `tests/golden/` 下 `<symbol>.render.md` + `<symbol>.fields.json`。**仅在确认行为变更是有意的后才跑**。
- `check`：比对 golden；被 `test_golden_diff_gate.py` 在门禁里强制跑。
- 若同时改了短中线报告版面：还须刷新 `tests/fixtures/report_render_baseline.txt`（与 `test_report_render_equivalence` 对齐）。

有意改输出时推荐顺序：

```bash
python scripts/golden_diff_gate.py capture
# 若 render 等价测仍红：用 mock_seam 重写 report_render_baseline.txt
bash scripts/run-gate-tests.sh
```

## 扩展门禁

新增一个**离线、无凭证、确定性**的测试后，显式加入 `scripts/run-gate-tests.sh` 的 `TESTS` 数组即可。不要为"凑覆盖"把网络测试塞进门禁——那会摧毁门禁的可信度。

## 已知边界 / 风险

1. **门禁守"行为不变"，不守"行为正确"**：等价性闸门以当前输出为基线，若基线本就带 bug，门禁会把它锁成绿。门禁防回归，不防"一直错的旧逻辑"。
2. **全量 `pytest 02-共享模块-shared/tests/` 里的历史红项，禁止为「凑绿」强行塞进门禁**  
   - 门禁只收录**当前离线稳定、已修契约相关**的用例。  
   - 全量套件可能含网络/凭证/陈旧契约失败；把它们写进 `TESTS` 会让 pre-push 永久红、失去报警意义。  
   - 修债路径：先把该测修绿且确认无网，再**显式**加入 `run-gate-tests.sh`。
3. **`test_contract.py` 等契约债不在门禁内**：勿盲目纳入导致永久红。
4. **耗时**：当前门禁为数秒级（视机器而定）；若变重，再考虑「仅跑改动相关」分层，不急着拆。
5. **PYTHONPATH 顺序敏感**：`02-共享模块-shared` 必须在前。
6. **Fusion 默认**：生产与测缺省 **cards**（`FUSION_FROM_CARDS` 未设）；`classic` 为强制回退。见 `analysis-strategy-boundaries.md` §5、`test_default_fusion_mode_is_cards`。

## 跳过门禁（谨慎）

```bash
git push --no-verify
```

仅用于你明确知道测试红是预期内的紧急推送。**事后必须补绿**。

## 迁移到服务端 CI（未来）

- **GitHub Actions** / **Gitee Go**：复用同一 `scripts/run-gate-tests.sh`。
- 核心原则：**门禁命令唯一来源是 `scripts/run-gate-tests.sh`**，本地 hook 与服务端 CI 永不 diverge。
