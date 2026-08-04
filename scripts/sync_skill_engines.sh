#!/usr/bin/env bash
# sync_skill_engines.sh — 仓库 trader_shared 引擎 → skill 安装位副本同步
#
# 目的：根治「仓库引擎 → skill 安装位副本漂移」。仓库规范为唯一事实源。
#
# 源：   02-共享模块-shared/trader_shared/*.py（仓库规范）
# 目标： {~/.workbuddy/skills, ~/.hermes/skills}/{trader,t0,wyckoff,review}/scripts/trader_shared/
#
# 同步规则：
#   - 仅同步「目标已存在」的 .py（不新增文件，避免污染 skill 特有结构）
#   - 逐文件 diff，不一致才复制；复制后复 diff 校验
# 模式：
#   - 默认 sync：把仓库文件复制到不一致的目标
#   - --check：只 diff 报告不改写；exit 1 = 有漂移
# 输出：每文件 ✓/✗ 明细 + 汇总（8 安装位 × 全部 engine .py 全一致 → exit 0）
# 幂等：重复执行无副作用
# 禁止：不用 rm 清理目标目录；不碰 skill 包内非 trader_shared 文件；不写临时文件到仓库
#
# 用法：
#   bash scripts/sync_skill_engines.sh [--check]
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO/02-共享模块-shared/trader_shared"

ROOTS=(
  "$HOME/.workbuddy/skills"
  "$HOME/.hermes/skills"
)
SKILLS=(trader t0 wyckoff review)

MODE="sync"
for arg in "$@"; do
  case "$arg" in
    --check) MODE="check" ;;
    *) echo "未知参数: $arg (仅支持 --check)" >&2; exit 2 ;;
  esac
done

if [ ! -d "$SRC_DIR" ]; then
  echo "✗ 源目录不存在: $SRC_DIR" >&2
  exit 2
fi

# 收集 8 个目标 trader_shared 目录（缺目录即失败，不做静默跳过）
TARGETS=()
for root in "${ROOTS[@]}"; do
  for skill in "${SKILLS[@]}"; do
    TARGETS+=("$root/$skill/scripts/trader_shared")
  done
done

missing_targets=0
for t in "${TARGETS[@]}"; do
  if [ ! -d "$t" ]; then
    echo "✗ 目标目录不存在: $t" >&2
    missing_targets=1
  fi
done
if [ "$missing_targets" -ne 0 ]; then
  exit 2
fi

# 判断仓库文件在「基准安装位」是否已存在（仅同步目标已存在的 .py，不新增文件）
BASE_TARGET="${TARGETS[0]}"
target_has_file() {
  [ -f "$BASE_TARGET/$1" ]
}

any_drift=0
copied=0
missing_in_target=0

for f in "$SRC_DIR"/*.py; do
  [ -f "$f" ] || continue
  name="$(basename "$f")"

  # 规则：目标不存在则跳过（不新增文件）
  if ! target_has_file "$name"; then
    echo "  - $name  跳过（目标安装位无此文件，不新增）"
    continue
  fi

  # 逐目标 diff
  file_drift=0
  for t in "${TARGETS[@]}"; do
    if [ ! -f "$t/$name" ]; then
      file_drift=1
      missing_in_target=1
      echo "  ✗ $name  目标缺失: $t"
      continue
    fi
    if ! diff -q "$f" "$t/$name" >/dev/null 2>&1; then
      file_drift=1
    fi
  done

  if [ "$file_drift" -eq 0 ]; then
    echo "  ✓ $name  全部一致"
    continue
  fi

  # 有漂移 → check 模式只报告；sync 模式复制 + 复 diff 校验
  if [ "$MODE" = "check" ]; then
    any_drift=1
    echo "  ✗ $name  存在漂移（check 模式不改写）"
    continue
  fi

  file_ok=1
  for t in "${TARGETS[@]}"; do
    if [ ! -f "$t/$name" ]; then
      continue  # 目标缺失在汇总时计数，不复制
    fi
    if diff -q "$f" "$t/$name" >/dev/null 2>&1; then
      continue  # 该位已一致
    fi
    cp "$f" "$t/$name"
    if diff -q "$f" "$t/$name" >/dev/null 2>&1; then
      echo "  ✓ $name  → $t  已同步并校验一致"
    else
      echo "  ✗ $name  → $t  复制后 diff 校验失败" >&2
      file_ok=0
    fi
  done
  if [ "$file_ok" -eq 1 ]; then
    copied=$((copied + 1))
  else
    any_drift=1
  fi
done

echo
echo "===== 汇总 ====="
echo "安装位数量: ${#TARGETS[@]}"
if [ "$missing_in_target" -ne 0 ]; then
  echo "✗ 存在目标目录中缺失的 engine .py（sync 不新增文件，需人工处理）"
  any_drift=1
fi
if [ "$MODE" = "check" ]; then
  if [ "$any_drift" -eq 0 ]; then
    echo "✓ check 通过：全部安装位与仓库一致"
    exit 0
  else
    echo "✗ check 失败：存在漂移（可运行 sync 恢复）"
    exit 1
  fi
else
  if [ "$any_drift" -eq 0 ]; then
    echo "✓ sync 完成：全部安装位与仓库一致（本次同步文件数: ${copied}）"
    exit 0
  else
    echo "✗ sync 存在未解决漂移，请检查上述 ✗ 项"
    exit 1
  fi
fi
