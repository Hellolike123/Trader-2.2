# 打包skill zip

## Goal

将 A-Share Trader 的三大技能（trader、t0、review）打包为可分发的 zip 文件，供 Hermes/Opencode 等平台安装使用。

## What I already know

* 项目已有 `02-共享模块-shared/scripts/pack_all.py` 脚本，功能完整：
  - 读取 `01-功能包-packages/` 下的 trader、t0、review 三个技能目录
  - 复制共享模块（`trader_shared/` 包 + 关键脚本）到每个技能
  - 生成 `_meta.json` 和 `SKILL.md`
  - 计算共享模块摘要
  - 打包为 `{skill}.zip` 输出到 `03-安装包-dist/releases/<timestamp>/`
  - 自动安装到 `~/.hermes/skills/`
  - 自动清理旧版本（保留最新 5 个）
* 上次打包在 2026-06-07 09:18，产物在 `03-安装包-dist/releases/0607-0918/`：
  - trader.zip (286 KB)
  - t0.zip (260 KB)
  - review.zip (279 KB)

## Assumptions (temporary)

* 用户想要重新打包（可能代码有更新）
* 不需要修改打包脚本本身

## Open Questions

* 是否直接运行现有的 `pack_all.py` 生成新版本？
* 是否需要 `--no-install` 标志（仅生成 zip 不自动安装到 ~/.hermes/skills）？
* 是否有其他技能也需要打包（如 `.opencode/skills/` 下的 trellis 相关技能）？

## Requirements (evolving)

* [ ] 生成新的 release 目录（带时间戳）
* [ ] 包含最新代码的 trader.zip、t0.zip、review.zip
* [ ] 验证 zip 完整性（meta、scripts、HERMES.md、SKILL.md 都在）

## Acceptance Criteria (evolving)

* [ ] `03-安装包-dist/releases/<new_timestamp>/` 存在三个 zip
* [ ] 每个 zip 解压后包含 `_meta.json`、`SKILL.md`、`scripts/`、`HERMES.md`
* [ ] 共享模块摘要正确写入 `_meta.json`

## Definition of Done

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 修改 pack_all.py 脚本逻辑
* 打包 .opencode/skills/ 下的内部工具技能
* 发布到外部 registry（PyPI、npm 等）

## Technical Notes

* 打包脚本：`02-共享模块-shared/scripts/pack_all.py`
* 技能源码：`01-功能包-packages/{trader,t0,review}/`
* 共享模块：`02-共享模块-shared/trader_shared/` + `scripts/`
* 输出目录：`03-安装包-dist/releases/`
* 自动安装目标：`~/.hermes/skills/`