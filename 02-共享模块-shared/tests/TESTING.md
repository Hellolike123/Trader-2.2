# Trader3.0 测试文档

## 测试结构

```
02-共享模块-shared/tests/
├── test_chan_core.py          # 缠论核心：分型/笔/线段/中枢/买卖点/背驰
├── test_chan_discipline.py    # 缠论纪律层：C1清单/仓位限制/闸控
├── test_chan_midline.py       # 中线分析：周线缠论/关键价
├── test_fusion_core.py        # 决策融合：三路信号/大势/资金流出
├── test_momentum_core.py      # 动量指标：MACD/RSI/ADX
├── test_indicator_math.py     # 指标数学：EXPMA/MACD统一实现
├── test_rule_engine.py        # 规则引擎：YAML规则/评分规则
├── test_account_risk.py       # 账户风控：余额/交易/回撤告警
├── test_main_force.py         # 主力行为：五阶段识别
├── test_wyckoff_core.py       # 威科夫：BC/Spring/AR/ST
└── accuracy/                  # 精度回归测试
    └── test_accuracy_momentum.py
```

## 运行测试

```bash
# 运行全部测试
python3 -m pytest 02-共享模块-shared/tests/ -v

# 运行单个模块
python3 -m pytest 02-共享模块-shared/tests/test_chan_core.py -v

# 运行单个测试类
python3 -m pytest 02-共享模块-shared/tests/test_chan_core.py::TestBuildStrokes -v

# 运行单个测试
python3 -m pytest 02-共享模块-shared/tests/test_chan_core.py::TestBuildStrokes::test_stroke_power_fields_always_present -v

# 只跑快速测试（排除慢测试）
python3 -m pytest 02-共享模块-shared/tests/ -v --ignore=02-共享模块-shared/tests/accuracy/
```

## 测试覆盖矩阵

| 模块 | 测试文件 | 用例数 | 覆盖内容 |
|------|----------|--------|----------|
| chan_core.py | test_chan_core.py | 97 | 分型(双侧)/笔(极端值搜索)/线段/中枢/买卖点/背驰/力度 |
| chan_discipline.py | test_chan_discipline.py | ~30 | C1清单/仓位限制/闸控/merge_discipline |
| chan_midline.py | test_chan_midline.py | ~15 | 周线缠论/关键价/Fibonacci |
| fusion_core.py | test_fusion_core.py | 45 | 融合决策/大势/资金流出/情景优先/置信度 |
| momentum_core.py | test_momentum_core.py | 18 | MACD金死叉/RSI/ADX/EMA |
| indicator_math.py | test_indicator_math.py | 22 | EXPMA/MACD序列(含None处理/常数/单调) |
| rule_engine.py | test_rule_engine.py | 18 | safe_eval沙箱/RuleEngine优先级/ScoreRuleEngine求和 |
| account_risk.py | test_account_risk.py | 13 | 账户初始化/余额/交易/盈亏/风控告警 |

## 关键测试用例说明

### chan_core.py

- `test_stroke_power_fields_always_present`: 验证 P4 笔力度字段（power_price/length）始终存在
- `test_stroke_power_volume_with_bars`: 验证传入 bars 时计算 power_volume
- `test_stroke_power_volume_without_bars`: 验证不传 bars 时没有 power_volume
- `test_buy_point_1_with_zone_and_stroke_divergence`: 验证一类买点（中枢+背驰）
- `test_segment_termination`: 验证线段特征序列三分型终结
- `test_chanlun_analysis_integration`: 验证完整管线输出所有字段

### indicator_math.py

- `test_ema12_starts_at_index_11`: 验证 EMA12 在第 11 根 K 线初始化
- `test_dif_equals_ema12_minus_ema26`: 验证 DIF = EMA12 - EMA26
- `test_histogram_equals_dif_minus_dea`: 验证 histogram = DIF - DEA
- `test_monotonic_up_dif_positive`: 验证单调上涨时 DIF 为正

### rule_engine.py

- `test_no_builtins_access`: 验证沙箱无法访问 `__import__`
- `test_first_matching_rule_wins`: 验证规则优先级匹配
- `test_sum_matching_rules`: 验证评分规则求和逻辑

## 新增/修改测试的规范

1. 每个新功能必须有对应测试
2. 测试命名格式：`test_<功能描述>`（snake_case）
3. 测试类命名格式：`Test<模块/功能名>`
4. 使用 `_make_bar()` 或 fixture 构造测试数据，不要硬编码真实行情
5. 测试之间不应有顺序依赖
6. 边界条件必须覆盖：空输入、None、极端值
