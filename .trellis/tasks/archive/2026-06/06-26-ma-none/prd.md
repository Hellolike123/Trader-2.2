# 完整报告-修复MA行缺失和评分字段为None的渲染问题

## Goal

修复 `render_markdown()` 中缺失的 6 个段落，使输出匹配 `output-template.md` 的完整模板。已有数据（筹码峰、EXPMA、共振、macd、量能日等）但 render 层没写进去。

## What I already know

- ATR=0 已修复（冗余 bar append 缺 ATR 字段，已补）
- `render_markdown` 计算的 `ma5_text`/`ma10_text` 等值从没写入输出
- report dict 有 99 个字段，含 chip/migration/expma/resonance/macd/missing_sources 等完整数据
- 模板要求输出 7 段：标题行情 → 阶段 + 融合 → 买卖点 → 持仓建议 → 筹码 → 打分 → 信号判断
- 当前仅输出标题行情 → 阶段 + 融合 → 买卖点 → 持仓 → 回测 → 亮点风险

## Requirements

1. 现价行后增加 MA 行（MA5/MA10/MA20/MA250）
2. 增加 💡 为什么这么操作（趋势/EXPMA/多窗判断）
3. 增加 🔍 主力筹码（筹码峰/中位数/日环比搬家）
4. 增加 💰 主力行为（有数据时展示，无数据时标注无数据）
5. 增加 📊 五层打分（结构/量价/筹码/动能）
6. 增加 🎯 信号判断（警惕/亮点/风险）
7. 所有数据从已有 report dict 字段直读，不新增数据计算

## Acceptance Criteria

- [ ] 输出包含 `MA5：X ｜ MA10：Y ｜ MA20：Z ｜ MA250：W` 行
- [ ] 💡 段落展示 stage + trend + EXPMA 评分 + 多窗
- [ ] 🔍 段落展示筹码峰、中位数、当前价以下占比、日环比变化
- [ ] 💰 段落展示主力行为评分(有数据时)或"无数据"
- [ ] 📊 段落展示结构/量价/筹码/动能分部评分
- [ ] 🎯 段落展示警惕/亮点/风险信号
- [ ] 南网科技运行输出完整，数据不受 main_force_env=unknown 影响

## Out of Scope

- 不新增数据计算逻辑（只渲染已有 report 字段）
- 不修复 main_force_env=unknown（独立问题，网络相关）

## Technical Notes

- 修改文件：`01-功能包-packages/trader/scripts/run_analysis.py` render_markdown 函数
- `ma_raw` dict 含 ma5/ma10/ma20/ma30/ma250 值
- `chip_peaks` list 含 4 个峰的 price/support_level 信息
- `chip_mid_price` 含中位数价格
- `chip_current_pct` 含当前价以下占比
- `chip_migration` dict 含峰对比数据
- `expma_status` 含 total_score/trend_label
- `resonance` 含 weekly/daily/timing label + total_score
- `macd_status` 含 MACD 信号
- `main_force_score` dict 含评分维度
- `verification_warnings/positives` 当前为 None（单独问题）
