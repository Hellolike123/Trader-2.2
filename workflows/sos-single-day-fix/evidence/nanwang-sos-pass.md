# 南网科技 SOS 验收（用户本机 2026-08 行情）

## pytest
- 修复 vol 边界测例后应全绿（此前 137 passed / 1 failed vol_boundary）

## diag
```
sos True thrust 45.5 … 量比1.9 … 近端1根前
post_sc_sos_hits 1 → 2026-08-03
main_detect_sos sos_signal True
08-03 base=4487096 ratio=1.88 thr=True
```

## final_wyckoff 面板
- 日线 ● SOS（强势信号）45.50
- 新亮 JAC、SOS
- 链：SC→AR→ST→SOS，待 LPS
- 周线 SOS 仍 ○（周 K 形态未达 thrust；可接受）
- 入池：建议入池（日线 LPS/SOS…）

## 根因摘要
整段 `tr_baseline_volume` 含突破日 → 量比 1.47；改为溪内（close≤creek）tip 前中位数 → 1.88。
