# 缠论 S-2 / S-3 后续 Handoff

> **状态**: open（2026-08-04）  
> **前置**: `chanlun-stroke-narrative-followup-handoff.md`（几何已 landed_on_main；§8/§10 无真洞）  
> **法源**: `formulas.md` §6；`chanlun-skill-slim-b-handoff.md` §2.3/§2.4；C-D4e  
> **本 handoff 授权范围**：合同测 +（可选）render 截断文案；**不改**笔几何 / detect 门槛 / fusion / 池分道

---

## 0. 一句话

S-2 要锁的是「观察档永不冒充正式灯」；S-3 若做，只允许 **render 近笔展示截断**，禁止动 `build_strokes` / `CHANLUN_MIN_BARS_PER_STROKE`。

---

## 1. S-2 快照合同（本轮可做）

### 必须

| ID | 行为 |
|----|------|
| S2-T1 | 引擎 type `类一买/卖`、`类二买/卖` 经 `_collect_points` **只进 observe**，formal keys 不得出现 |
| S2-T2 | 正式 `一类/二类/三类`×买卖 进 formal，**不得**被标 `（观察）`（已有 O-T5；保持绿） |
| S2-T3 | 用 §10 实盘出现过的 type 集合做最小快照：`类一买`、`类一卖@价`、`类二卖` 与空正式灯共存 |

### 禁止

- 为「好看」把类一升格一类  
- 改 `detect_buy_points` / `detect_sell_points` 阈值（无新假点证据前）  
- 依赖外网 live 行情才能绿的测

### 可改文件

- `02-共享模块-shared/tests/test_chanlun_s2_observe_snapshot.py`（新建）  
- 如需：`test_chanlun_skill_render.py` 仅增断言，不改语义

### 验收

```bash
python3 -m pytest 02-共享模块-shared/tests/test_chanlun_s2_observe_snapshot.py \
  02-共享模块-shared/tests/test_chanlun_skill_render.py -q
```

---

## 2. S-3 近笔截断（默认不做，需产品拍板）

| 项 | 说明 |
|----|------|
| 动机 | 长窗日线笔数可达 50+，人话近笔刷屏 |
| 允许 | `chanlun_render` 只展示近 N 笔方向 / 近笔价，全文注明「近N」 |
| 禁止 | 改 `build_strokes`、全局放宽/收紧 min_bars、用截断影响买卖点 |
| 前置 | 用户确认 N（建议 5 或 7）+ 是否周/日都截 |

**未拍板前：不写生产代码。**

---

## 3. 五票联网 smoke（可选运维）

外网可用时：

```bash
for t in 南网科技 华工科技 中际旭创 曙光数创 中航光电; do
  python3 01-功能包-packages/chanlun/scripts/final_chanlun.py --target "$t"
done
```

对照 §10 离线表：正式/观察分层、tip_leave、无「宜买」指令叙事。

---

## 4. 勿改

fusion / decision_view / 池分道 / `chan_geometry.build_strokes` 语义 / 与威科夫 PR 混提。
