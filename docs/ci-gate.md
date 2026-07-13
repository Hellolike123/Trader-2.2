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

跑以下 7 个离线、无凭证、确定性测试文件（基线：**68 passed / 1 warning / ~63s**）：

| 文件 | 守护内容 |
|---|---|
| `02-共享模块-shared/tests/test_imports_smoke.py` | 22 核心子模块 + 公开 API 导入冒烟（无网络） |
| `02-共享模块-shared/tests/test_build_report_golden.py` | `build_report` 行为回归（5 策略调用计数 + 中线 key + 形状） |
| `02-共享模块-shared/tests/test_build_report_adr002_equivalence.py` | ADR-002 路由后逐字段等价（堵日线 chan 静默漂移） |
| `02-共享模块-shared/tests/test_report_render_equivalence.py` | 拆分前后渲染 md5 等价 |
| `02-共享模块-shared/tests/test_arch_refactoring.py` | 架构重构回归（PluginRegistry / 收编） |
| `02-共享模块-shared/tests/test_indicator_math.py` | 指标计算数学正确性 |
| `01-功能包-packages/trader/tests/test_report_renderer.py` | 旧 `report_renderer/` 包渲染（命名冲突规避） |

**故意不跑全量 80+ 测试**：其中大量依赖网络/凭证（`test_tushare_integration`、`test_tdx3_provider`、`test_light_data_mootdx` 等），在 CI 与离线环境会红或超时（历史上有沙箱 SIGKILL 137 记录）。强行全量会让门禁永远红、失去报警意义。

## 扩展门禁

新增一个**离线、无凭证、确定性**的测试后，显式加入 `scripts/run-gate-tests.sh` 的 `TESTS` 数组即可。不要为"凑覆盖"把网络测试塞进门禁——那会摧毁门禁的可信度。

## 已知边界 / 风险

1. **门禁守"行为不变"，不守"行为正确"**：等价性闸门以当前输出为基线，若基线本就带 bug，门禁会把它锁成绿。门禁防回归，不防"一直错的旧逻辑"。
2. **`test_contract.py` 3 项失败不在门禁内**：那是契约/实现漂移债，需单独评估（更新契约 or 修实现），勿盲目改测试对齐。它若纳入门禁会让门禁永久红。
3. **耗时约 63s**：golden 重计算所致。每次 push 等一分钟，是门禁的代价；如觉重，可后续优化为"仅跑改动相关测试"。
4. **PYTHONPATH 顺序敏感**：`02-共享模块-shared` 必须在前，否则 `config` 解析到 `trader_shared/config.py` 导致收集失败。

## 跳过门禁（谨慎）

```bash
git push --no-verify
```

仅用于你明确知道测试红是预期内（如临时调参）的紧急推送。**事后必须补绿**，否则门禁失去意义。

## 迁移到服务端 CI（未来）

- **GitHub Actions**：加 `.github/workflows/ci.yml`，steps 里 `pip install -r requirements-dev.txt && TRADER_CI_PYTHON=python3 scripts/run-gate-tests.sh`。迁 GitHub 远程后自动生效。
- **Gitee Go**：仓库设置启用，工作流配置文件 `.workflows/ci.yml` 复用同一 `run-gate-tests.sh`（设 `TRADER_CI_PYTHON` 指向 runner 的 python）。
- 核心原则：**门禁命令唯一来源是 `scripts/run-gate-tests.sh`**，本地 hook 与服务端 CI 永不 diverge。
