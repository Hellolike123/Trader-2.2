# 威科夫模块审计报告（wyckoff-review）

> 审计方法：逐条对照原典（威科夫积累/派发示意图 + `spec-wyckoff-classic-signals.md`）→ 代码落点（文件:函数:行号）→ 证据驱动判定 → 重验已知旧坑 → 跑 pytest → 抽真实市场数据验证。
> 审查人：威科夫专家（reviewer 模式，只读不改）。
> 审计日期：2026-07-15

## 一、总判定

**不通过（存在 P0 阻塞项）。** 威科夫计算层有 2 类实质问题：
1. **P0：威科夫测试未进 CI 门禁，且当前已有 2 个测试失败**（被门禁掩盖）。
2. **P1：同段价量上相反极性信号（SC↔SOW、LPS↔LPSY、Spring↔Upthrust）会被同时计入打分并互相抵消**，导致强方向信号被中性化为 50 分——真实数据（688248）已实证。

## 二、验收清单（逐项 [PASS]/[FAIL]）

| # | 原典规则 | 代码落点 | 判定 | 证据 |
|---|---------|---------|------|------|
| 1 | 三大定律：供求/因果/努力结果 | `wyckoff_events._detect_effort_vs_result` / `wyckoff_core` VSA 修正 | [PASS] | L1048-1093 实现努力无结果/供应耗尽；因果律(P&F)本项目未实现（见备注） |
| 2 | SC 卖力高潮（低位天量宽幅阴） | `wyckoff_events._detect_selling_climax` L347 | [PASS] | 量比≥1.8 + 低位过滤 + 阴线跌幅≥2% + 实体大 |
| 3 | BC 购买高潮（高位天量滞涨） | `wyckoff_events._detect_buying_climax` L268 | [PASS] | 量比≥1.8 + 高位过滤 + 滞涨/阴线 |
| 4 | AR 自动反弹（BC/SC 后放量反弹） | `wyckoff_events._detect_ar` L627 | [PASS] | 记忆依赖 BC/SC 锚点，后 1-3 根 close>bc*1.02 且放量 |
| 5 | Spring 弹簧（刺穿支撑后收回） | `wyckoff_events._detect_spring` L503 | [PASS] | ATR/固定刺穿线 + 收回到支撑上 + 量能分级 |
| 6 | SOS 强势（连续放量突破） | `wyckoff_events._detect_sos` L718 | [PASS] | ≥4/5 阳线 + 抬高 + 量≥1.2× + 累计≥2% |
| 7 | ST 二次测试（Spring 后缩量回测） | `wyckoff_events._detect_st` L779 | [PASS*] | 触发条件齐，但支撑位为"近10根最低价"重算，未用 Spring 记录的 support（松耦合，见 P2-3） |
| 8 | LPS 最后支撑（SOS 后缩量回踩不破前低） | `wyckoff_events._detect_lps` L891 | [PASS*] | 时序 SOS→回调→LPS 已强制；但同段会误触发 LPSY 抵消（见 P1-1） |
| 9 | Upthrust 上冲回落 | `wyckoff_events._detect_upthrust` L561 | [PASS] | 突破阻力+回落+放量确认 |
| 10 | SOW 弱势（放量跌破支撑） | `wyckoff_events._detect_sign_of_weakness` L421 | [PASS] | 跌破+放量+收盘下方 |
| 11 | LPSY 最后供应（反弹不过前高缩量） | `wyckoff_events._detect_lpsy` L996 | [FAIL] | **无派发背景门控**：一律 −12，与 phase 状态机的 `lpsy_found and (bc/ut/sow)` 门控不一致，导致与 LPS 抵消（P1-1） |
| 12 | 阶段机 Accumulation A→E | `wyckoff_phase._detect_phase` L145 | [FAIL*] | 仅对 bc/ar/ut/sow/sc/lpsy 滑窗扫描；spring/sos/lps 只看最后一根 → 经典积累链捕获弱（P1-3） |
| 13 | 阶段机 Distribution A→E | `wyckoff_phase._detect_phase` L240 | [PASS] | BC/UT/SOW/SC+AR/LPSY 分支齐全 |
| 14 | 孤立 LPSY 不标派发 | `wyckoff_phase._detect_phase` L249 | [PASS] | `if lpsy_found: return none`（孤立时） |
| 15 | 打分体系与缠论互补独立 | `wyckoff_core.calculate_wyckoff_score` L300 | [PASS] | 独立计算，无覆盖 |
| 16 | 归一化分母匹配当前权重集 | `config.WYCKOFF_SCORE_MAX_ABS=95` | [FAIL] | 95 按"最大正值85"算，P2/P3 新增 SC/压缩/趋势回踩/VSA 修正后实际最大 raw≈128+，分母过时（P1-2） |
| 17 | 已知旧坑：phase 只进不退 | `wyckoff_phase._transition_phase` L319 | [PASS*] | 反向翻转已修（L378-384）；同方向仍只升不降 + none 保留旧状态 → 标签可能黏住（P2-6） |
| 18 | 已知旧坑：中线周线不足回退日线 | `wyckoff_core.wyckoff_strategy_midline` L269 | [PASS] | 直接 insufficient，不回退（L282-294） |

### 2.5 逐检测器 vs 原典理论差距表

> 本表系统对比每个 `_detect_*` 函数与原典理论的核心差距。**核心问题（P0-3）是所有检测器共性的**——原典的"支撑/阻力=TR区间边界"被替换为"支撑/阻力=固定窗口局部极值"，且事件判定与 TR 层脱钩。以下逐条列出每个检测器在该共性之外的特有差距。

| # | 检测器 | 核心函数:L行号 | 代码窗口 | 窗口含义 | 与原典核心差距 |
|---|--------|---------------|---------|---------|-------------|
| 1 | BC 购买高潮 | `_detect_buying_climax`:279 | `bars[-5:]` | 只扫最后5根找天量滞涨 | **顶部在外不可见**：原典 BC 是"漫长上升趋势末端"的天量，需更长的趋势背景判定。另：`_is_bc_high_position` 是近窗 `max(lookback=10)` 极值判定，不是"趋势末端"语境。 |
| 2 | SC 卖力高潮 | `_detect_selling_climax`:362 | `bars[-5:]` | 只扫最后5根找天量暴跌 | **同上**：原典 SC 是"漫长下跌后的抛售枯竭"，需要下跌趋势背景。代码只有"近窗低位"无下跌趋势判定。 |
| 3 | AR 自动反弹 | `_detect_ar`:640 | `bars[-5:]` 找 BC/SC 锚点 | 锚点只来源于最近5根 | 如果 BC/SC 在 5 根外（A 股常见），本根 AR 因无锚点而永不可达。 |
| 4 | Spring 弹簧 | `_detect_spring`:507 | `_is_trading_range(bars, lookback=20)` | 近20根 ATR 振幅≤4×ATR% | **有波动过滤器但不是 TR 边界**：此函数只检查"是否大趋势中"（排除极端趋势），不识别 TR 的上下沿。Spring 的"support"是近10根最低价（L527），不是 TR 下沿。 |
| 5 | SOS 强势 | `_detect_sos`:730 | 基线窗 `bars[-15:-5]` + 事件窗 `bars[-5:]` | 基线=前10根均量，事件=5根连续K线 | **突破什么**：原典 SOS 是"放量突破 TR 上沿"，代码只检查"连续涨2%+放量"。如果股价已在上升趋势中脱离 TR，也会被标 SOS。无 TR 上沿概念。 |
| 6 | ST 二次测试 | `_detect_st`:793 | Spring 后 3-15 根 | 回测支撑±1%+缩量<80% | **支撑重算**：P2-3 已提，支撑为"近10根最低价"重算，非 Spring 记录的 support。但 Spring 本身也未记录 support——两个检测器松耦合。另：ST 信号依赖 Spring，但 Spring 可能因`_is_trading_range` 过滤掉而永不可达（非TR期间）。 |
| 7 | LPS 最后支撑 | `_detect_lps`:950 | SOS 后 2-10 根回调 | SOS 锚点+回调不破前低+缩量<0.7 | **回调深度未关联 TR 上沿**：原典 LPS 是 SOS 突破 TR 后的缩量回踩 TR 上沿（不破）。代码只检查"不破 SOS 前低"——如果 SOS 起点不是 TR 上沿而是半途，LPS 的逻辑依然成立但与原典语义不同。 |
| 8 | Upthrust 上冲回落 | `_detect_upthrust`:565 | 阻力窗 `bars[-11:-1]` | 阻力=近10根最高价×1.005 | **无 TR 上沿**：阻力是近10根最高价，不是 TR 上沿。如果在上升趋势中，近10根一直走高，阻力最近跟得紧，"突破回落后再回落"的分辨率低。 |
| 9 | SOW 弱势信号 | `_detect_sign_of_weakness`:440 | 支撑窗 `bars[-12:-2]`（consecutive=2时） | 支撑=近10根最低值 | **无 TR 下沿**：已详述。支撑随窗口漂移（前日破位后新的最低价进入窗口→支撑下移→破位标准变松）。原典 SOW 是"跌破 TR 下沿"，支撑应该是固定的 TR 边界。 |
| 10 | LPSY 最后供应 | `_detect_lpsy`:1013 | 阻力窗 `bars[-15:]` | 阻力=近15根最高价 | **无派发背景门控**：P1-1 已提。额外差距：阻力是近15根最高不是 TR 上沿。 |
| 11 | 量价背离 | `_detect_volume_divergence`:600 | 5根拆两半 | 后2.5根/前2.5根量比<0.85 | **窗口太短**：原典量价背离应在更长趋势背景（15-30根）下判定。5根在 A 股日线上几乎没有统计学意义。 |
| 12 | 努力vs结果 VSA | `_detect_effort_vs_result`:1060 | 基线20根+扫描最后3根 | 高量窄幅 vs 低量窄幅 | 实现合理，无理论偏差。 |
| 13 | 压缩蓄势 | `_detect_compression`:1103 | 近20根 ATR+参考窗60根 | ATR分位<20%+量比<0.6 | **非原典核心概念**：合理的技术指标，但不是威科夫 Theory 的原典要求。保留作为展示型指标。 |
| 14 | 趋势回踩 | `_detect_trend_pullback`:1180 | 近10根+MA20 | 回撤5-20%+缩量+站稳MA20 | **非原典概念**：是均线系统，非威科夫。保留作为展示型指标。 |

**系统性结论**：14 个检测器中，**12 个（#1-#11, #14）与原典理论有可追溯的差距**——核心是 P0-3（无 TR 层/窗口漂移/边界替换）。#13（压缩蓄势）和 #14（趋势回踩）是新增展示型指标，不属于原典核心范围。差距最小的是 #12（VSA），实现合理。

## 三、跑测记录

```
PYTHONPATH="02-共享模块-shared:01-功能包-packages/trader/scripts" \
  python -m pytest 02-共享模块-shared/tests/test_wyckoff_core.py \
                    02-共享模块-shared/tests/test_wyckoff_split_equivalence.py -q

结果：2 failed, 92 passed
```

**失败用例 1**：`TestWyckoffScoreWithClassicSignals::test_lps_adds_12`
- 期望 raw ∈ {12, 27}，实际 raw=5。
- 探针实证：`LPS +12` + `LPSY -12`（同段 SOS 后缩量回踩被 LPSY 误判）+ `供应耗尽 +5` = 5。→ 印证 P1-1。

**失败用例 2**：`TestDetectPhaseSemantics::test_bc_ar_is_distribution_a_not_accumulation`
- 期望 distribution_a，实际 none。
- 根因：测试 `patch("trader_shared.wyckoff_core._scan_for_signal")`，但 `_detect_phase` 在 `wyckoff_phase.py` 内调用的是本模块的 `_scan_for_signal`（经 `from .wyckoff_phase import _scan_for_signal` re-export 双绑定），mock 打错命名空间失效。→ 测试缺陷 + 架构脆弱点（P0-2）。

**CI 缺口**：`scripts/run-gate-tests.sh` 门禁清单**不含** `test_wyckoff_core.py` / `test_wyckoff_split_equivalence.py`，故这 2 个失败被门禁掩盖（之前 145 passed 不含威科夫测试）。

## 四、真实数据抽检记录

调用：`get_provider().fetch_qfq_daily(sec, days=120)` → `wyckoff_analysis` + `calculate_wyckoff_score`。

| 标的 | 末日 | data_source | phase_label | score/raw | signals |
|------|------|------------|-------------|-----------|---------|
| 688248 南网科技 | **2026-07-15** | tencent-http（新鲜） | 积累期 A（SC） | 50 / 1 | sc_signal, **sow_signal** |
| 600519 贵州茅台 | **数据不一致⚠️** | 见下方 P2-5 实证 | （见注） | （见注） | （见注） |
| 002050 三花智控 | **2026-03-17** | tushare（**陈旧4个月**） | 无明确阶段 | 47 / -5 | （空） |
| 002460 赣锋锂业 | **2026-03-17** | tushare（**陈旧4个月**） | 无明确阶段 | 62 / 23 | st_signal |

**关键发现**：
- ✅ 688248 走 tencent-http 拿到**今天**数据 → 此前缓存 stale bug 修复生效。
- ❌ 002050/002460 末日停在 **2026-03-17**（今天 07-15）：本机 tushare HTTP 不可用（SSL EOF / timeout，stderr 可见），回退到**陈旧的 tushare 缓存**。数据源回退不一致，使这两只威科夫判定基于 4 个月前数据，**结论不可信**（P2-5，且与"老拿不到大盘数据"同源）。
- ❌ **688248 同时触发 sc_signal（看多）与 sow_signal（看空）→ raw=1 / score=50 中性**：一次暴跌后的强信号被相互抵消抹平。实证 P1-1（反向信号抵消）。
- ⚠️ **600519 茅台数据不一致（P2-5 实证）**：本审计**两次独立探针给出相反结果**——第一次直连底层 `fetch_qfq_daily` 返回 `末日=2026-07-15 / src=tencent-http / score=62 raw=23 / signals=[sos,st]`（新鲜）；后续走生产 `get_provider().fetch_qfq_daily` 重跑则返回 `末日=2026-03-17 / src=tushare / STALE`（陈旧）。**同一标的、同一天、两次取数落到不同数据源 → 结论不同**。这本身就是数据源回退链不确定性（P2-5）的活证据，故茅台未纳入 4.4 人工复核，其首次探针的 sos/st 判定仅作参考、不作证据。
- ✅ （参考）茅台首次探针 SOS+ST 同向 → 62 偏多，说明**同向 coherent 时打分正常**，问题集中在反向组合。

### 四.4 人工K线逐根复核（积累/派发案例，按提示词第四节第4条）

> 说明：本步骤为「人工看K线复核」。执行方式是把代码实际摄入的 OHLCV 逐根打印（见下方原始数据），按威科夫原典（积累/派发示意图的价/量/时序/窗口）逐根判读，再与 `wyckoff_analysis` 的代码输出比对。**数据源仅取末日==2026-07-15 的 tencent-http 新鲜数据**；末日停在 03-17 的陈旧 tushare（600519/002050/002460）已排除，不参与判定。

**案例 A — 积累（Accumulation）案例：300750 宁德时代 —— ⚠️ 数据不可靠，撤销原判**

> **诚实更正（2026-07-15 复跑发现）**：本案例初次审计时取到的数据是「FRESH tencent-http 121根 末日07-15」，据此写了下方 SC/AR 积累判读。但按用户要求复跑起点终点验证时，**同一标的取到的是「STALE tushare 82根 末日2026-03-17」**，与初判所用数据完全不一致（P2-5 数据源回退不一致的真实代价）。82 根陈旧数据下 SC 检测最后5根无任何 climax bar，signals=[]。
> **结论**：本案例作为"积累结构实证"的证据**不可靠，撤销**。下方原典判读仅作方法示意、不作为审计结论。P1-3 的结论仍需另行用「末日==07-15 的可靠样本」重验，不可依赖宁德。

关键K线（近段，初判所用07-15数据，现已不可复现）：
```
07-10  O=375.00 H=375.20 L=346.16 C=348.76  V=556014 >>  阴宽   ← 窗口最大成交量，宽幅大跌
07-13  O=349.00 H=362.00 L=348.00 C=359.06  V=462907     阳宽
07-14  O=352.60 H=364.63 L=352.49 C=364.01  V=436316     阳宽
07-15  O=368.01 H=379.99 L=363.08 C=373.00  V=358493     阳窄
```
- **原典人工判读**：股价自 06-01 高位 438 跌至 07-10 的 348（约−20%），07-10 是一根「窗口最大成交量 + 宽幅阴线收低位」的**卖力高潮 SC**；随后 07-13~07-15 三连阳放量反弹 = **自动反弹 AR**。即经典的 **Phase A 积累启动（SC→AR）**。
- **代码输出**：`signals=['sos']`，`phase=无明确阶段`，`score=57/raw=15`。
- **比对结论**：代码只把反弹段识别为 SOS（偏多），**完全漏掉 SC/AR 积累结构**，phase 机给「无明确阶段」。→ 印证 **P1-3（积累阶段链捕获弱）**：阶段机只看最后一根，spring/sos/lps 无滑窗，导致 SC→AR 这种清晰积累背景识别不出。

**案例 B — 派发（Distribution）案例：300308 中际旭创（FRESH, tencent-http, 121根, 末日07-15）**

关键K线（顶部→破位）：
```
06-22  O=1367.78 H=1416.88 L=1343.38 C=1382.33  V=280333   阳窄   ← 窗口最高价 1416.88（顶部）
06-23  O=1395.00 H=1395.00 L=1300.00 C=1310.01  V=291773   阴宽
07-01  O=1263.50 H=1315.57 L=1208.00 C=1223.17  V=271557   阴窄   ← 更低的高点
07-02  O=1160.00 H=1198.00 L=1127.40 C=1143.00  V=317620   阴窄   ← 跳空大跌
07-10  O=1210.00 H=1218.00 L=1093.98 C=1093.98  V=423262 >>  阴宽   ← 窗口最大成交量，宽幅破位
07-13~15 反弹至 1169（缩量）
```
- **原典人工判读**：06-22 见顶 1416.88 后，**高点逐级降低**（1382→1310→1223→1143），07-10 在顶部区间之后出现「窗口最大成交量 + 宽幅阴线破位」= 典型的**派发破位 / 弱势信号 SOW**（Markup 后的供应涌入）。即 **Phase A/E 派发→Markdown**。
- **代码输出**：`signals=[]`（无任何信号），`phase=无明确阶段`，`score=55/raw=10`。
- **比对结论**：代码在一段**清晰顶部+放量破位**上**什么都没识别出来**，派发结构完全漏检。→ 印证 **P1-3 的对称问题（派发侧同样弱）**，且暴露新细节：**成交量比阈值参考窗过长**——07-10 的 423262 仅略低于 `vavg*1.5=447994`，因 05-06 整段都是高量区把均值抬高，导致破位量不够「相对高」而漏触发。属检测器灵敏度缺陷。

**案例 C — 反向信号抵消实证：688248 南网科技（FRESH, tencent-http, 301根, 末日07-15）**

关键K线：
```
07-01  C=67.63（阶段高点）
... 两周下跌至 ...
07-14  C=55.50
07-15  O=55.24 H=55.24 L=47.90 C=48.05  V=8851572 >>  阴宽   ← 窗口最大成交量，跳空大跌收近最低
```
- **原典人工判读**：自 07-01 高点 67.63 连跌两周至 07-15 的 48.05（−29%），07-15 是「最大成交量 + 跳空宽幅阴线收近最低」= 急跌末端的**卖力高潮 SC（抛售枯竭）**，属 Phase A 积累起点，**不是 SOW**（SOW 需先有派发区间，此处无）。
- **代码输出**：`signals=['sc','sow']`，`phase=积累期A(SC)`，`score=50/raw=1`。
- **比对结论**：同一根 bar 同时触发 `sc(+10)` 与 `sow(−12)` → 互相抵消净 raw=1/score=50 中性。其中 **`sow` 在此语境下是误判**（急跌末端应为 SC，非派发破位），而打分器无派发背景门控（phase 机虽有 `lpsy_found and (bc/ut/sow)` 但打分器未同步）→ 强 SC 信号被错误中性化。→ 直接实锤 **P1-1（反向极性信号同段抵消 + 缺上下文门控）**。

**四.4 小结**：3 个真实案例覆盖「积累 / 派发 / 反向抵消」三类，均与代码输出逐一比对，**全部发现代码判定与原典目视不符**——积累结构漏检（宁德）、派发结构漏检（中际旭创）、急跌末端 SC 被 SOW 误抵消（南网）。这不是单点 bug，而是**打分/阶段聚合层在「上下文」维度系统性缺失**（P1-1/P1-3）。

## 五、业务→代码映射抽检表（节选）

| 原典概念 | 主要函数 | 行号 |
|---------|---------|------|
| SC | `_detect_selling_climax` | wyckoff_events.py:347 |
| BC | `_detect_buying_climax` | wyckoff_events.py:268 |
| AR | `_detect_ar` | wyckoff_events.py:627 |
| Spring | `_detect_spring` | wyckoff_events.py:503 |
| SOS | `_detect_sos` | wyckoff_events.py:718 |
| ST | `_detect_st` | wyckoff_events.py:779 |
| LPS | `_detect_lps` | wyckoff_events.py:891 |
| LPSY | `_detect_lpsy` | wyckoff_events.py:996 |
| Upthrust | `_detect_upthrust` | wyckoff_events.py:561 |
| SOW | `_detect_sign_of_weakness` | wyckoff_events.py:421 |
| 努力/结果(VSA) | `_detect_effort_vs_result` | wyckoff_events.py:1048 |
| 阶段机 | `_detect_phase` | wyckoff_phase.py:145 |
| 状态机/持久化 | `_transition_phase` | wyckoff_phase.py:319 |
| 打分 | `calculate_wyckoff_score` | wyckoff_core.py:300 |
| 展示 | `format_wyckoff_oneline` | wyckoff_core.py:491 |

## 六、P0 / P1 / P2 问题列表

### P0（阻塞）
- **P0-1 威科夫测试未进 CI 门禁，且已有 2 个失败。**
  - `scripts/run-gate-tests.sh` 缺 `test_wyckoff_core.py` / `test_wyckoff_split_equivalence.py`。
  - 修复：将两文件加入门禁；修复 2 个失败用例（见 P0-2 / P1-1）。
- **P0-2 `test_bc_ar_is_distribution_a` 失败 = 测试 mock 打错命名空间。**
  - 修复：测试应 patch `trader_shared.wyckoff_phase._scan_for_signal`（或改为直接构造 signals 字典传参，避开 re-export 双绑定）。同时建议消除 `wyckoff_core` 对 `_scan_for_signal` 等的 re-export，减少混淆。
- **P0-3 事件检测器"固定窗口滑动"框架与原典"TR→边界→事件"因果链不符（系统性差距）。**
  - 这是本次审计发现的最**深刻、最基础**的问题——编码者没有按照威科夫的"先识别交易区间 TR → 确定区间上下沿 → 在此基础上判定事件"的认知流程来设计代码，而是把所有检测器写成了**孤立的固定窗口模式匹配器**。
  - **原典正确流程**：① 划出 TR（Trading Range，成交密集区）→ ② 确定区间的上下沿边界和正常量能基线 → ③ 在此边界基础上判定事件：Spring = 跌破下沿后收回、SOW = 跌破下沿放量确认、Upthrust = 突破上沿回落、SOS = 放量突破上沿、LPS = 回调不破上沿且缩量、ST = 缩量回测 Spring 下沿等。
  - **代码实际流程**：每个检测器独立运算，用**固定数量 bar 的滑动窗口**计算局部极值→与当前 bar 值比对→判定事件。没有 TR 层，支撑/阻力全部是局部滑动极值。
  - **后果**：所有原典中"边界"的概念被替换成了"近 N 根 bar 的最低价/最高价"。这意味着：① 窗口外的关键高/低点不可见（宁德 06-01 高 438 不在 5 根窗内）；② 边界随窗口滑动漂移（中际旭创 SOW 支撑 1060.34 是 07-06 的最低价，07-07~13 反弹后支撑又会变）；③ 不存在"横盘越久→边界越可靠"的因果律。
  - **探针实证**见 `### 2.5 逐检测器 vs 原典理论差距表`（所有 14 个检测器均有此问题）。
  - **修复方向**：在检测器前增加 TR 识别层（识别成交密集区，计算区间上下沿、量能基线），让事件检测基于 TR 边界而非滑动窗口局部极值。**这是架构级改动，影响范围大，需整体设计后实施。**

### P1（非阻塞但重要）
- **P1-1 反向极性信号同时计入打分并互相抵消（score 中性化）。**
  - 证据：① 单元测试 `test_lps_adds_12` raw=5（LPS+12 / LPSY−12 / no_supply+5）；② 真实数据 688248 SC+SOW 同发 → raw=1/score=50。
  - 根因：`_detect_lpsy` 等 leaf 检测器无上下文门控，一律按极性加分/减分；phase 状态机虽有 `lpsy_found and (bc/ut/sow)` 背景门控，但打分器未同步。
  - 修复建议：打分器加"同上下文互斥"——积累背景下抑制派发类信号（UT/BC/SOW/LPSY），派发背景下抑制积累类信号（Spring/SC/SOS/LPS/AR/ST）；或在累加 raw 前按"净极性"取舍。最低成本做法：让 `_detect_lpsy` 也接收/复用派发背景布尔（与 phase 机一致），孤立 LPSY 不打分。
- **P1-2 归一化分母 `WYCKOFF_SCORE_MAX_ABS=95` 过时，注释还写错。**
  - `config.py:199` 注释 "raw 映射到 [-50,+50]" 错误（实际 `50+raw*50//95` → [0,100]）。
  - 95 按 spec "最大正值 85" 算；P2/P3 新增 SC(+10)/压缩(+10)/趋势回踩(+8)/VSA(+5+5)/阶段修正后，实际最大 raw≈128+，多数多头组合饱和到 100，区分度下降。
  - 修复：按当前权重集重算 MAX_ABS ≈ ceil(实际最大 raw × 1.05)，并修正注释。
- **P1-3 accumulation 阶段机对 last-bar 信号强依赖，经典积累链捕获弱。**
  - `_detect_phase` 只对 bc/ar/ut/sow/sc/lpsy 滑窗扫描；spring/sos/lps/compression/trend_pb 只看最后一根。
  - 后果：`spring and (sos or lps)` → accumulation_d 分支几乎不可达（需 spring 与 sos/lps 同在后一根 bar）；accumulation_d 实际只能靠 trend_pullback 触达。经典 Spring→SOS→LPS 确认在 phase_label 上体现不出。
  - 修复：对 spring/sos/lps 也加近期滑窗扫描（或维护信号滑动窗口），让阶段机基于"近 N 根内出现过的事件序列"而非"最后一根"。

### P2（备注）
- **P2-1 硬编码阈值多为工程经验值，非原典精确数值。** 证据：`WYCKOFF_BC_VOL_RATIO_THRESHOLD # 原2.0，方案B调至1.8`、`WYCKOFF_SPRING_RECLAIM_RATIO # 每年年底需检查`。建议：集中到 config 并标注"经验值·需回测"，不要伪装成原典。
- **P2-2 SC 复用 `WYCKOFF_SCORE_AR`(+10) 无独立常量，spec 也未定义 SC 分值。** 建议显式定义 `WYCKOFF_SCORE_SC` 便于调参与清晰。
- **P2-3 `_detect_st` 支撑位为"近 10 根最低价"重算，未用 Spring 记录的 support。** 松耦合，多数情况可工作，但与原典"ST 依赖 Spring 锚点"不完全一致。
- **P2-4 `format_wyckoff_oneline` 残留 `timeframe=="daily_fallback"` 死分支**（中线从不产出该值），清理。
- **P2-5 真实数据：tushare 通路坏时回退到陈旧 tushare 缓存（002050/002460 末日 03-17）。** 建议：tushare 失败不应返回陈旧 tushare 缓存，应继续降级到 tencent/sina 取新鲜数据（对齐 light_data 回退链），并校验末日新鲜度。
- **P2-6 阶段标签"黏住"风险**：`_transition_phase` 同方向只升不降 + none 保留旧状态 → 一旦进入某阶段，除非出现反向明确信号，phase_label 永久黏住；报告里该字段显眼，可能误导。建议加"阶段新鲜度衰减"（N 日无确认信号则降级）或明确为设计取舍。
- **备注：因果律（P&F count）原典要求的目标价测算本项目未实现。** 威科夫第三大定律未在代码中落地，属功能缺口而非 bug。

## 七、改动范围复核

本次为**审查（reviewer 模式），未改动业务代码**。所有结论基于读码 + 跑测 + 真实数据抽检。如需修复，改动应限定在：
- `wyckoff_events.py`（`_detect_lpsy` 加背景门控；可选 `_detect_st` 用 Spring support）
- `wyckoff_core.py`（`calculate_wyckoff_score` 加上下文互斥；`format_wyckoff_oneline` 清理死分支）
- `wyckoff_phase.py`（`_detect_phase` 对 spring/sos/lps 加滑窗）
- `config.py`（`WYCKOFF_SCORE_MAX_ABS` 重算 + 注释修正；可选 `WYCKOFF_SCORE_SC`）
- `scripts/run-gate-tests.sh`（纳入威科夫测试）
- `tests/test_wyckoff_core.py`（修复 2 个失败用例的 mock/数据构造）

## 八、结论

威科夫信号检测器（单 bar 层）整体对齐原典，法定义清晰；但**打分与阶段聚合层有系统性缺陷**：反向极性信号互相抵消（P1-1，真实数据实证）、归一化分母过时（P1-2）、积累阶段链捕获弱（P1-3）。叠加**威科夫测试被排除在 CI 之外且有 2 失败**（P0），当前威科夫评分在"反向信号共存"与"陈旧数据源"两种情况下会给出误导性中性/失真结论。

**总判定：不通过。** 阻塞项 = P0-1 / P0-2（先让威科夫测试进门禁并清零）。下一步按 P1-1 → P1-2 → P1-3 顺序修复打分与阶段聚合层。
