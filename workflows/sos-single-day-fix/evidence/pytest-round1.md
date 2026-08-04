# pytest round 1（用户本机粘贴）

- TestDetectSosThrust: **2 failed, 5 passed**
- full test_wyckoff_core: **2 failed, 130 passed**

失败：`test_thrust_sos_breakout_above_tr`、`test_backup_can_anchor_thrust_sos`  
根因：`84498/47000 ≈ 1.7978 < 1.8` 严格比较。

## fix

`_try_sos_thrust`：`round(vol_ratio, 2) >= threshold`  
请重跑同命令确认 7/7 + 全文件绿。
