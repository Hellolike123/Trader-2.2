#!/bin/bash
# Batch-11 应用脚本：测试 → 提交(不push) → 打包 → 双装
# 用法：在 Mac 终端里运行  bash /Users/like/Documents/Opencode/Trader3.0/scripts/batch11_apply.sh
set -u
REPO=/Users/like/Documents/Opencode/Trader3.0
PY=/Users/like/.workbuddy/binaries/python/envs/default/bin/python
cd "$REPO" || { echo "无法进入仓库 $REPO"; exit 1; }

echo "===== 1/6 语法检查 ====="
"$PY" -m py_compile \
  02-共享模块-shared/trader_shared/structure_core.py \
  01-功能包-packages/trader/scripts/run_analysis.py \
  01-功能包-packages/t0/scripts/price_point_engine.py && echo "COMPILE_OK"

echo "===== 2/6 主回归 test_structure_core (期望 31 passed) ====="
export PYTHONPATH="02-共享模块-shared:01-功能包-packages/trader/scripts"
"$PY" -m pytest 02-共享模块-shared/tests/test_structure_core.py -q
if [ $? -ne 0 ]; then echo "!!! 结构测试失败，中止（请把上面输出贴给 agent）"; exit 1; fi
echo "STRUCTURE_OK"

echo "===== 3/6 融合集成测试 ====="
"$PY" -m pytest 01-功能包-packages/trader/tests/test_fusion_integration.py -q
if [ $? -ne 0 ]; then echo "!!! 融合测试失败，中止（请把上面输出贴给 agent）"; exit 1; fi
echo "FUSION_OK"

echo "===== 4/6 提交（不 push） ====="
git add 02-共享模块-shared/trader_shared/structure_core.py \
       02-共享模块-shared/tests/test_structure_core.py \
       01-功能包-packages/t0/scripts/price_point_engine.py \
       01-功能包-packages/trader/scripts/run_analysis.py \
       docs/audit/batch-11-implementation.md \
       .workbuddy/memory/2026-07-08.md 2>/dev/null
git commit -m "$(cat <<'EOF'
fix(structure): 支撑压力位有效性改进（Batch-11，不含阈值收紧）

A. 删 structure_core 死代码 opposite
E. 有效位选择优先触碰次数最多（structure_core + t0）
B. 补对称支撑回归测试 test_broken_support_falls_back_to_window_low
C. t0 find_key_levels 加破位过滤（剔除已跌破支撑/已突破阻力）
D. run_analysis 渲染去重标注【双线/三线共振】保留多周期确认信息

验证：test_structure_core 31 passed
EOF
)" && echo "COMMIT_OK"

echo "===== 5/6 打包（--no-install） ====="
"$PY" 02-共享模块-shared/scripts/pack_all.py --no-install && echo "PACK_OK"

echo "===== 6/6 干净安装到两个 skill 副本 ====="
"$PY" - <<'PYEOF'
import shutil, os, zipfile, datetime
for base in ["~/.workbuddy/skills", "~/.hermes/skills"]:
    SK = os.path.expanduser(base)
    DIST = "/Users/like/Documents/Opencode/Trader3.0/03-安装包-dist/releases"
    subs = [d for d in os.listdir(DIST) if os.path.isdir(os.path.join(DIST, d))]
    dist_dir = os.path.join(DIST, sorted(subs)[-1])
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(SK, ".backup", ts)
    os.makedirs(backup, exist_ok=True)
    for s in ["trader", "t0", "review", "daily_briefing"]:
        src = os.path.join(SK, s)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(backup, s)); shutil.rmtree(src)
        with zipfile.ZipFile(os.path.join(dist_dir, f"{s}.zip")) as z:
            z.extractall(SK)
    print("  [install] ->", SK)
# 验证两份 trader 都含共振标注
for base in ["~/.workbuddy/skills", "~/.hermes/skills"]:
    p = os.path.expanduser(base + "/trader/scripts/run_analysis.py")
    ok = "三线共振" in open(p, encoding="utf-8").read()
    print(f"  [verify] {base}/trader 含『三线共振』: {ok}")
print("INSTALL_DONE")
PYEOF

echo ""
echo "===== ALL DONE ====="
echo "已 commit（未 push）。两个 skill 副本（workbuddy + hermes）均已更新到含 Batch-11 修复的版本。"
