# 威科夫 failed 文案精简（本波无新SC）— Handoff

> **状态**: impl_done  
> 法源续：`docs/plans/wyckoff-phase-fail-copy-handoff.md`（只改人话；不改 failed 判定/检测/pos_ref）  
> 实现锚点：`wyckoff_render.py`；光杆 `wyckoff_core.format_wyckoff_*_light`  
> 产品裁决：**精简** failed 无强势句，消除「历史上从没 SC / 必须补课」误读。

## 1. 做

| 槽位 | 旧 | 新 |
|------|----|----|
| 日线 failed 无 SOS/LPS 主句 | `Phase A 失效｜须重新寻底` | `Phase A 失效｜本波无新SC` |
| 旧锚尾 | `旧SC {价}（仅对照）` | `旧SC {价}（对照）` |
| 光杆 daily | `…｜须重新寻底｜仅对照` | `…｜本波无新SC｜对照` |
| 光杆 midline | `…｜须重新寻底｜不据此开仓` | `…｜本波无新SC｜不据此开仓` |
| 推演若变好 / 盯 / 下一盯 | 重新寻底／新 SC… | `出现本波新SC` / `盯本波新SC` / `○ 下一盯：本波新SC` |
| chain token failed | `Phase A 失效｜须重新寻底` | `Phase A 失效｜本波无新SC` |

failed+SOS / failed+LPS 主句**不改**（仍破后强势 / LPS 修复）；旧锚尾同步用 `（对照）`。

## 2. 不做

- 不改 `phase_a_failed`、SC 检测、`pos_ref`、窗口、fusion、出手、池分道
- 不恢复健康链「还差 / 链可推进」
- 不引入长说明段（本迭代主句已自解释）

## 3. 验收

- pytest：`test_wyckoff_skill_render` / `test_wyckoff_structure_anchor` 相关 failed 串
- 面板可见：主句含 `本波无新SC`；有价则 `旧SC`+`（对照）`；禁加长「历史可有过 SC…」段落
