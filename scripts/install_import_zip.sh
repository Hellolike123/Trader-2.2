#!/usr/bin/env bash
set -euo pipefail

PRESET="hermes"
TARGET_ROOT=""

usage() {
  cat <<'EOF'
Usage:
  scripts/install_import_zip.sh <skill_name> <zip_path> [--preset hermes|openclaw|codex|codebuddy|workbuddy] [--target-root PATH]

Examples:
  scripts/install_import_zip.sh t0-trader 03-安装包-dist/t0-trader-import.zip --preset hermes
  scripts/install_import_zip.sh t0-trader 03-安装包-dist/t0-trader-import.zip --preset workbuddy
  scripts/install_import_zip.sh t0-trader 03-安装包-dist/t0-trader-import.zip --target-root /path/to/custom/skills

Notes:
  Prefer *-import.zip for Hermes/OpenClaw/Codex installs. The installer also accepts
  *-skill.zip, but import zips avoid double-nesting mistakes.
  Hermes preset installs to ~/.hermes/skills
  OpenClaw preset installs to ~/.openclaw/workspace/skills
  Codex/Agents preset installs to ~/.agents/skills
  CodeBuddy preset installs to ~/.codebuddy/skills
  WorkBuddy preset installs to ~/.workbuddy/skills
  If your agent uses a project-local skills root, pass --target-root explicitly.
EOF
}

if [[ $# -gt 0 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
  usage
  exit 0
fi

if [[ $# -lt 2 ]]; then
  usage >&2
  exit 2
fi

SKILL_NAME="$1"
ZIP_PATH="$2"
shift 2

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
    hermes) TARGET_ROOT="$HOME/.hermes/skills" ;;
    openclaw) TARGET_ROOT="$HOME/.openclaw/workspace/skills" ;;
    codex) TARGET_ROOT="$HOME/.agents/skills" ;;
    codebuddy) TARGET_ROOT="$HOME/.codebuddy/skills" ;;
    workbuddy) TARGET_ROOT="$HOME/.workbuddy/skills" ;;
    *)
      echo "Unsupported preset: $PRESET" >&2
      echo "Use --target-root /path/to/skills for project-local or custom agent roots." >&2
      exit 2
      ;;
  esac
fi

if [[ ! -f "$ZIP_PATH" ]]; then
  echo "Zip not found: $ZIP_PATH" >&2
  exit 2
fi

case "$SKILL_NAME" in
  trader) ENTRY_SCRIPT="scripts/final_report.py" ;;
  t0-trader) ENTRY_SCRIPT="scripts/final_t0.py" ;;
  trader-compare) ENTRY_SCRIPT="scripts/final_compare.py" ;;
  trader-portfolio) ENTRY_SCRIPT="scripts/final_portfolio.py" ;;
  review-trader) ENTRY_SCRIPT="scripts/final_review.py" ;;
  trader-pool) ENTRY_SCRIPT="scripts/final_pool.py" ;;
  *)
    echo "Unknown Trader skill: $SKILL_NAME" >&2
    exit 2
    ;;
esac

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$TARGET_ROOT"
ZIP_LIST="$(zipinfo -1 "$ZIP_PATH")"

INSTALL_SOURCE=""
ZIP_KIND=""
if grep -qx "SKILL.md" <<<"$ZIP_LIST" && grep -qx "$ENTRY_SCRIPT" <<<"$ZIP_LIST"; then
  ZIP_KIND="import"
  unzip -q "$ZIP_PATH" -d "$TMP_DIR/import-root"
  INSTALL_SOURCE="$TMP_DIR/import-root"
elif grep -qx "$SKILL_NAME/SKILL.md" <<<"$ZIP_LIST" && grep -qx "$SKILL_NAME/$ENTRY_SCRIPT" <<<"$ZIP_LIST"; then
  ZIP_KIND="skill"
  unzip -q "$ZIP_PATH" -d "$TMP_DIR/skill-root"
  INSTALL_SOURCE="$TMP_DIR/skill-root/$SKILL_NAME"
else
  echo "Unsupported zip layout for $SKILL_NAME: $ZIP_PATH" >&2
  echo "Expected either import zip with SKILL.md at root or skill zip with $SKILL_NAME/SKILL.md." >&2
  exit 3
fi

TARGET="$TARGET_ROOT/$SKILL_NAME"
rm -rf "$TARGET"
mkdir -p "$TARGET"
cp -R "$INSTALL_SOURCE"/. "$TARGET"/

REQUIRED_FILES=("SKILL.md" "VERSION_STAMP" "$ENTRY_SCRIPT")
if [[ "$PRESET" == "hermes" ]]; then
  REQUIRED_FILES+=("HERMES.md" "_skillhub_meta.json" "agents/hermes.yaml")
fi

for required in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "$TARGET/$required" ]]; then
    echo "Install validation failed: missing $TARGET/$required" >&2
    echo "This usually means the zip was extracted into the wrong level or is an old package." >&2
    exit 4
  fi
done

echo "PRESET=$PRESET"
echo "TARGET_ROOT=$TARGET_ROOT"
echo "ZIP_KIND=$ZIP_KIND"
echo "INSTALLED_TO=$TARGET"
echo "ENTRY_SCRIPT=$TARGET/$ENTRY_SCRIPT"
echo "VERSION_STAMP=$(cat "$TARGET/VERSION_STAMP")"
echo "VERIFY_FILE=test -f \"$TARGET/$ENTRY_SCRIPT\""
echo "VERIFY_RUN=python3 \"$TARGET/$ENTRY_SCRIPT\" --help"
echo "INSTALL_IMPORT_ZIP_OK=$SKILL_NAME"
