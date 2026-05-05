#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="$ROOT_DIR/03-安装包-dist"
PRESET="codex"
TARGET_ROOT=""
SKIP_PACKAGE=0
AGGRESSIVE_CACHE=0

usage() {
  cat <<'EOF'
Usage:
  scripts/reset_install_skills.sh [--preset codex|hermes|openclaw|codebuddy|workbuddy] [--target-root PATH] [--skip-package] [--aggressive-cache]

Purpose:
  Remove old Trader/T0 skill installs, optionally clear global skill cache hints,
  rebuild all official zips, reinstall all official skills, and run smoke checks.

Recommended:
  Hermes local install: scripts/reset_install_skills.sh --preset hermes --aggressive-cache
  OpenClaw install:     scripts/reset_install_skills.sh --preset openclaw --aggressive-cache
  Codex/Agents install: scripts/reset_install_skills.sh --preset codex --aggressive-cache
  CodeBuddy install:    scripts/reset_install_skills.sh --preset codebuddy --aggressive-cache
  WorkBuddy install:    scripts/reset_install_skills.sh --preset workbuddy --aggressive-cache

Default:
  --preset codex installs to ~/.agents/skills for Codex/Agents testing.

Preset roots:
  hermes    -> ~/.hermes/skills
  openclaw  -> ~/.openclaw/workspace/skills
  codex     -> ~/.agents/skills
  codebuddy -> ~/.codebuddy/skills
  workbuddy -> ~/.workbuddy/skills
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --preset)
      PRESET="${2:?missing preset value}"
      shift 2
      ;;
    --target-root)
      TARGET_ROOT="${2:?missing target root value}"
      shift 2
      ;;
    --skip-package)
      SKIP_PACKAGE=1
      shift
      ;;
    --aggressive-cache)
      AGGRESSIVE_CACHE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$TARGET_ROOT" ]]; then
  case "$PRESET" in
    codex) TARGET_ROOT="$HOME/.agents/skills" ;;
    hermes) TARGET_ROOT="$HOME/.hermes/skills" ;;
    openclaw) TARGET_ROOT="$HOME/.openclaw/workspace/skills" ;;
    codebuddy) TARGET_ROOT="$HOME/.codebuddy/skills" ;;
    workbuddy) TARGET_ROOT="$HOME/.workbuddy/skills" ;;
    *)
      echo "Unsupported preset: $PRESET" >&2
      echo "Use --target-root /path/to/skills for project-local or custom agent roots." >&2
      exit 2
      ;;
  esac
fi

SKILLS=(trader t0-trader trader-compare trader-portfolio review-trader trader-pool)
LEGACY=(trader-hermes trader-import t0-trader-import trader-old t0-old)

package_dir_for() {
  case "$1" in
    trader) echo "$ROOT_DIR/01-功能包-packages/01-单票分析-trader" ;;
    t0-trader) echo "$ROOT_DIR/01-功能包-packages/02-盘中T0-t0-trader" ;;
    trader-compare) echo "$ROOT_DIR/01-功能包-packages/03-多股比较-trader-compare" ;;
    trader-portfolio) echo "$ROOT_DIR/01-功能包-packages/04-仓位轮动-trader-portfolio" ;;
    review-trader) echo "$ROOT_DIR/01-功能包-packages/05-盘后复盘-review-trader" ;;
    trader-pool) echo "$ROOT_DIR/01-功能包-packages/06-选股池-trader-pool" ;;
    *)
      echo "Unknown Trader skill package: $1" >&2
      exit 2
      ;;
  esac
}

echo "ROOT_DIR=$ROOT_DIR"
echo "TARGET_ROOT=$TARGET_ROOT"
if [[ "$AGGRESSIVE_CACHE" -eq 1 ]]; then
  echo "CACHE_MODE=aggressive"
else
  echo "CACHE_MODE=conservative"
fi

mkdir -p "$TARGET_ROOT"

echo "== Remove old Trader skill directories =="
for name in "${SKILLS[@]}" "${LEGACY[@]}"; do
  if [[ -e "$TARGET_ROOT/$name" ]]; then
    echo "REMOVE=$TARGET_ROOT/$name"
    rm -rf "$TARGET_ROOT/$name"
  fi
done
find "$TARGET_ROOT" -maxdepth 1 -type d \( -iname '*trader-hermes*' -o -iname '*trader-import*' -o -iname '*t0-trader-import*' \) -print -exec rm -rf {} +

if [[ "$AGGRESSIVE_CACHE" -eq 1 ]]; then
  echo "== Clear global registry/cache hints =="
  for cache_path in \
    "$HOME/.agents/.skill-lock.json" \
    "$HOME/.agents/skill-cache" \
    "$HOME/.agents/skills-cache" \
    "$HOME/.agents/registry" \
    "$HOME/.agents/skill-registry" \
    "$HOME/.hermes/skill-cache" \
    "$HOME/.hermes/skills-cache" \
    "$HOME/.hermes/registry" \
    "$HOME/.hermes/skill-registry" \
    "$HOME/.openclaw/skill-cache" \
    "$HOME/.openclaw/skills-cache" \
    "$HOME/.openclaw/registry" \
    "$HOME/.openclaw/skill-registry" \
    "$HOME/.codebuddy/skill-cache" \
    "$HOME/.codebuddy/skills-cache" \
    "$HOME/.codebuddy/registry" \
    "$HOME/.codebuddy/skill-registry" \
    "$HOME/.workbuddy/skill-cache" \
    "$HOME/.workbuddy/skills-cache" \
    "$HOME/.workbuddy/registry" \
    "$HOME/.workbuddy/skill-registry"; do
    if [[ -e "$cache_path" ]]; then
      echo "REMOVE_CACHE=$cache_path"
      rm -rf "$cache_path"
    fi
  done
else
  echo "== Skip global registry/cache cleanup =="
  echo "Use --aggressive-cache only when an agent keeps using stale skill metadata."
fi

if [[ "$SKIP_PACKAGE" -eq 0 ]]; then
  echo "== Rebuild zips =="
  for name in "${SKILLS[@]}"; do
    python3 "$(package_dir_for "$name")/scripts/package_skill.py"
  done
fi

echo "== Install official skills =="
for name in "${SKILLS[@]}"; do
  "$ROOT_DIR/scripts/install_import_zip.sh" "$name" "$OUTPUT_DIR/$name-import.zip" --preset "$PRESET" --target-root "$TARGET_ROOT"
done

echo "== Version stamps =="
for name in "${SKILLS[@]}"; do
  echo "--- $name"
  cat "$TARGET_ROOT/$name/VERSION_STAMP"
done

echo "== Smoke checks =="
python3 "$TARGET_ROOT/trader/scripts/final_report.py" --target 南网科技 > /tmp/trader_reset_smoke.md
python3 "$TARGET_ROOT/trader/scripts/validate_output.py" /tmp/trader_reset_smoke.md

python3 "$TARGET_ROOT/t0-trader/scripts/final_t0.py" --target 南网科技 > /tmp/t0_reset_smoke.md
python3 "$TARGET_ROOT/t0-trader/scripts/validate_output.py" /tmp/t0_reset_smoke.md

python3 "$TARGET_ROOT/trader-compare/scripts/final_compare.py" --targets 南网科技 中国铝业 > /tmp/compare_reset_smoke.md
python3 "$TARGET_ROOT/trader-compare/scripts/validate_output.py" /tmp/compare_reset_smoke.md

python3 "$TARGET_ROOT/trader-portfolio/scripts/final_portfolio.py" --targets 南网科技 中国铝业 > /tmp/portfolio_reset_smoke.md
python3 "$TARGET_ROOT/trader-portfolio/scripts/validate_output.py" /tmp/portfolio_reset_smoke.md

python3 "$TARGET_ROOT/review-trader/scripts/final_review.py" --target 南网科技 --cost 57.60 --session close > /tmp/review_reset_smoke.md
python3 "$TARGET_ROOT/review-trader/scripts/validate_output.py" /tmp/review_reset_smoke.md

POOL_HOME="$(mktemp -d)"
HOME="$POOL_HOME" python3 "$TARGET_ROOT/trader-pool/scripts/final_pool.py" add --target 南网科技 --offline > /tmp/pool_add_reset_smoke.md
HOME="$POOL_HOME" python3 "$TARGET_ROOT/trader-pool/scripts/final_pool.py" show > /tmp/pool_reset_smoke.md
python3 "$TARGET_ROOT/trader-pool/scripts/validate_output.py" /tmp/pool_reset_smoke.md

echo "== Legacy output guard =="
if grep -R "trader-hermes" "$TARGET_ROOT" >/tmp/trader_legacy_hits.txt 2>/dev/null; then
  cat /tmp/trader_legacy_hits.txt >&2
  echo "LEGACY_CHECK_FAILED=trader-hermes reference found in installed skills" >&2
  exit 3
fi

if grep -E "⏱️ 盘中 T0|T0买入价|T0卖出价|先买后卖" /tmp/t0_reset_smoke.md >/tmp/t0_legacy_bad.txt; then
  cat /tmp/t0_legacy_bad.txt >&2
  echo "LEGACY_CHECK_FAILED=old T0 template appeared in generated output" >&2
  exit 4
fi

if grep -E "⏱️ T0 简版|t0-trader|执行价" /tmp/trader_reset_smoke.md >/tmp/trader_legacy_bad.txt; then
  cat /tmp/trader_legacy_bad.txt >&2
  echo "LEGACY_CHECK_FAILED=old Trader template appeared in generated output" >&2
  exit 5
fi

echo "RESET_INSTALL_OK=$TARGET_ROOT"
