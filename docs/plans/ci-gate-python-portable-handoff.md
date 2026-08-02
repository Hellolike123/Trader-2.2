# CI 门禁 Python 可移植默认值 handoff

> **状态**: active（2026-08-02）  
> **产品裁决**: 门禁脚本默认解释器不得绑死本机 Mac 绝对路径；云 / Linux / CI 无该路径时须能跑。  
> **范围**: 只改 `scripts/run-gate-tests.sh` 的 Python 解析 + `docs/architecture/ci-gate.md` 说明；**不改**测试集合、不改业务引擎。

---

## 1. 背景

`run-gate-tests.sh` 现行默认：

```bash
PYTHON="${TRADER_CI_PYTHON:-/Users/like/.workbuddy/binaries/python/envs/default/bin/python}"
```

云 Agent / Linux 上该路径不存在 → 门禁直接失败，被迫手设 `TRADER_CI_PYTHON=python3`。  
文档已写「CI runner 设此变量」；缺省值仍应可移植。

---

## 2. 必须（G-P1…G-P5）

| ID | 必须 |
|----|------|
| G-P1 | `TRADER_CI_PYTHON` 若已设且可执行 → **只用它**（不覆盖） |
| G-P2 | 未设时：若历史 Mac venv 路径存在且可执行 → 可用作默认（兼容原作者本机） |
| G-P3 | 否则回退 `command -v python3`；再否则 `command -v python`；都没有 → **非零退出 + 明确错误信息** |
| G-P4 | 选定的解释器须能跑 `"$PYTHON" -c "import sys; print(sys.executable)"` |
| G-P5 | `docs/architecture/ci-gate.md` 补一句：默认解析顺序（env → Mac venv if exists → python3 → python） |

---

## 3. 禁止

1. 不删/不扩 `TESTS` 数组（本 PR 不夹带加测）。  
2. 不改 `trader_shared` / skill 包业务逻辑。  
3. 不把网络测试塞进门禁。  
4. 不在脚本里 `pip install`。

---

## 4. 可改 / 勿改

| 可改 | 勿改 |
|------|------|
| `scripts/run-gate-tests.sh`（仅 PYTHON 解析段） | `TESTS` 列表内容 |
| `docs/architecture/ci-gate.md`（环境变量说明） | 任意引擎 / 面板 / fusion |
| 本 handoff | pre-push hook 语义（除非只是调用同一脚本） |

---

## 5. 验收

| ID | 项 | 如何验 |
|----|-----|--------|
| M-G1 | 未设 env、无 Mac 路径时，`bash scripts/run-gate-tests.sh` 用系统 `python3` 启动 | 云环境干跑；日志可见解释器路径 |
| M-G2 | `TRADER_CI_PYTHON=/usr/bin/python3` 时强制用该路径 | env 覆盖干跑 |
| M-G3 | 相关 pytest 集合仍绿（门禁 exit 0） | 跑完整门禁脚本 |
| M-G4 | diff 只含脚本 + ci-gate 文档 + 本 handoff | `git diff --stat` |

---

## 6. 双 Agent

- **写 Agent**：按 G-P* 改脚本与文档，跑门禁至绿，commit/push。  
- **查 Agent**：对照本 handoff 列 ✅/❌；禁扩 TESTS / 禁碰引擎。
