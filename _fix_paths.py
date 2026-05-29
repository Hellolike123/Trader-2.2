"""Fix parents[3] path resolution in all entry scripts — dual-mode skill/repo."""
import sys
from pathlib import Path

FIXES = []

# ── run_analysis.py ──
FIXES.append((
    "01-功能包-packages/01-单票分析-trader/scripts/run_analysis.py",
    '''ROOT = Path(__file__).resolve().parents[3]
SHARED_CANDIDATE = ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate"
SHARED_MARKET = ROOT / "02-共享模块-shared" / "01-行情数据-market-data"
SHARED_SCRIPTS = ROOT / "02-共享模块-shared" / "scripts"
SHARED_ROOT = ROOT / "02-共享模块-shared"
for _path in (SHARED_CANDIDATE, SHARED_MARKET, SHARED_SCRIPTS, SHARED_ROOT):
    if _path.exists() and str(_path) not in sys.path:
        sys.path.append(str(_path))''',
    '''# 双模式路径发现：Hermes skill 包内 vs 仓库开发
_SCRIPT_DIR = Path(__file__).resolve().parent
if (_SCRIPT_DIR.parent / "trader_shared").exists():
    _SHARED = _SCRIPT_DIR.parent          # skill 模式
else:
    _SHARED = _SCRIPT_DIR.parents[3] / "02-共享模块-shared"  # 仓库模式

SHARED_CANDIDATE = _SHARED / "02-候选逻辑-candidate"
SHARED_MARKET = _SHARED / "01-行情数据-market-data"
SHARED_SCRIPTS = _SHARED / "scripts"
SHARED_ROOT = _SHARED
for _path in (SHARED_CANDIDATE, SHARED_MARKET, SHARED_SCRIPTS, SHARED_ROOT):
    if _path.exists() and str(_path) not in sys.path:
        sys.path.append(str(_path))'''
))

# ── monitor.py ──
FIXES.append((
    "01-功能包-packages/02-盘中T0-t0-trader/scripts/monitor.py",
    '''CONTRACTS = Path(__file__).resolve().parents[3] / "02-共享模块-shared" / "03-输出校验-contracts"
SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "02-共享模块-shared" / "scripts"
SHARED_ROOT = Path(__file__).resolve().parents[3] / "02-共享模块-shared"
SHARED_MARKET = Path(__file__).resolve().parents[3] / "02-共享模块-shared" / "01-行情数据-market-data"
for _p in (CONTRACTS, SHARED_SCRIPTS, SHARED_ROOT, SHARED_MARKET):''',
    '''# 双模式路径发现：Hermes skill 包内 vs 仓库开发
_SCRIPT_DIR = Path(__file__).resolve().parent
if (_SCRIPT_DIR.parent / "trader_shared").exists():
    _SHARED = _SCRIPT_DIR.parent          # skill 模式
else:
    _SHARED = _SCRIPT_DIR.parents[3] / "02-共享模块-shared"  # 仓库模式

CONTRACTS = _SHARED / "03-输出校验-contracts"
SHARED_SCRIPTS = _SHARED / "scripts"
SHARED_ROOT = _SHARED
SHARED_MARKET = _SHARED / "01-行情数据-market-data"
for _p in (CONTRACTS, SHARED_SCRIPTS, SHARED_ROOT, SHARED_MARKET):'''
))

# ── t0_run.py ──
FIXES.append((
    "01-功能包-packages/02-盘中T0-t0-trader/scripts/t0_run.py",
    '''ROOT = Path(__file__).resolve().parents[3]
SHARED_MARKET = ROOT / "02-共享模块-shared" / "01-行情数据-market-data"
SHARED_SCRIPTS = ROOT / "02-共享模块-shared" / "scripts"
SHARED_ROOT = ROOT / "02-共享模块-shared"
TRADER_SHARED = ROOT / "02-共享模块-shared" / "trader_shared"
CONTRACTS = ROOT / "02-共享模块-shared" / "03-输出校验-contracts"
for _p in (SHARED_MARKET, SHARED_SCRIPTS, SHARED_ROOT, CONTRACTS, TRADER_SHARED):''',
    '''# 双模式路径发现：Hermes skill 包内 vs 仓库开发
_SCRIPT_DIR = Path(__file__).resolve().parent
if (_SCRIPT_DIR.parent / "trader_shared").exists():
    _SHARED = _SCRIPT_DIR.parent          # skill 模式
else:
    _SHARED = _SCRIPT_DIR.parents[3] / "02-共享模块-shared"  # 仓库模式

SHARED_MARKET = _SHARED / "01-行情数据-market-data"
SHARED_SCRIPTS = _SHARED / "scripts"
SHARED_ROOT = _SHARED
TRADER_SHARED = _SHARED / "trader_shared"
CONTRACTS = _SHARED / "03-输出校验-contracts"
for _p in (SHARED_MARKET, SHARED_SCRIPTS, SHARED_ROOT, CONTRACTS, TRADER_SHARED):'''
))

# ── final_pool.py ──
FIXES.append((
    "01-功能包-packages/03-选股池-trader-pool/scripts/final_pool.py",
    '''ROOT = Path(__file__).resolve().parents[3]
SHARED_CANDIDATE = ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate"
SHARED_SCRIPTS = ROOT / "02-共享模块-shared" / "scripts"
SHARED_ROOT = ROOT / "02-共享模块-shared"
for _p in (SHARED_CANDIDATE, SHARED_SCRIPTS, SHARED_ROOT):''',
    '''# 双模式路径发现：Hermes skill 包内 vs 仓库开发
_SCRIPT_DIR = Path(__file__).resolve().parent
if (_SCRIPT_DIR.parent / "trader_shared").exists():
    _SHARED = _SCRIPT_DIR.parent          # skill 模式
else:
    _SHARED = _SCRIPT_DIR.parents[3] / "02-共享模块-shared"  # 仓库模式

SHARED_CANDIDATE = _SHARED / "02-候选逻辑-candidate"
SHARED_SCRIPTS = _SHARED / "scripts"
SHARED_ROOT = _SHARED
for _p in (SHARED_CANDIDATE, SHARED_SCRIPTS, SHARED_ROOT):'''
))

# ── Simple _ROOT = parents[3] files ──
for fpath, varname in [
    ("01-功能包-packages/04-仓位轮动-trader-portfolio/scripts/portfolio_run.py", "_ROOT"),
    ("01-功能包-packages/05-盘后复盘-review-trader/scripts/final_review.py", "_ROOT"),
    ("01-功能包-packages/05-盘后复盘-review-trader/scripts/review_single.py", "_ROOT"),
    ("01-功能包-packages/05-盘后复盘-review-trader/scripts/review_compare.py", "_ROOT"),
    ("01-功能包-packages/06-信号追踪-trader-tracking/scripts/final_tracker.py", "_ROOT"),
]:
    FIXES.append((
        fpath,
        f'{varname} = Path(__file__).resolve().parents[3]',
        f'''# 双模式路径发现：Hermes skill 包内 vs 仓库开发
_SCRIPT_DIR = Path(__file__).resolve().parent
if (_SCRIPT_DIR.parent / "trader_shared").exists():
    {varname} = _SCRIPT_DIR.parent          # skill 模式
else:
    {varname} = _SCRIPT_DIR.parents[3]      # 仓库模式''',
    ))

# ── 6x validate_output.py (all same: `ROOT = Path(__file__).resolve().parents[3]`) ──
for skill_slug in [
    "01-单票分析-trader",
    "02-盘中T0-t0-trader",
    "03-选股池-trader-pool",
    "04-仓位轮动-trader-portfolio",
    "05-盘后复盘-review-trader",
    "06-信号追踪-trader-tracking",
]:
    fpath = f"01-功能包-packages/{skill_slug}/scripts/validate_output.py"
    FIXES.append((
        fpath,
        'ROOT = Path(__file__).resolve().parents[3]',
        '''# 双模式路径发现：Hermes skill 包内 vs 仓库开发
_SCRIPT_DIR = Path(__file__).resolve().parent
if (_SCRIPT_DIR.parent / "trader_shared").exists():
    ROOT = _SCRIPT_DIR.parent          # skill 模式
else:
    ROOT = _SCRIPT_DIR.parents[3]      # 仓库模式''',
    ))


# ── Apply ──
ok = 0
fail = 0
for fpath, old, new in FIXES:
    p = Path(fpath)
    if not p.exists():
        print(f"  SKIP (not found): {fpath}")
        fail += 1
        continue
    content = p.read_text(encoding="utf-8")
    if old not in content:
        print(f"  SKIP (old text not found): {fpath}")
        # Debug: show what's around parents[3]
        for i, line in enumerate(content.split("\n")):
            if "parents[3]" in line:
                print(f"    line {i+1}: {line.strip()}")
        fail += 1
        continue
    content = content.replace(old, new, 1)
    p.write_text(content, encoding="utf-8")
    print(f"  OK: {fpath}")
    ok += 1

print(f"\nDone: {ok} patched, {fail} skipped")
