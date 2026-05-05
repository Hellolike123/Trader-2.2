from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "final_pool.py"


def run_pool(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PYTHONPATH"] = str(ROOT / "scripts") + ":" + str(ROOT.parents[1] / "02-共享模块-shared" / "trader_shared")
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def pool_file(tmp_path: Path) -> Path:
    return tmp_path / ".trader" / "pool.json"


def test_analyze_outputs_admission_suggestion_without_writing_pool(tmp_path: Path) -> None:
    result = run_pool(tmp_path, "analyze", "--target", "南网科技")

    assert result.returncode == 0, result.stderr
    assert "入池建议" in result.stdout
    assert "下一步：如确认，请说“加入选股池”" in result.stdout
    assert not pool_file(tmp_path).exists()


def test_add_writes_pool_and_repeated_add_updates_same_record(tmp_path: Path) -> None:
    first = run_pool(tmp_path, "add", "--target", "南网科技")
    second = run_pool(tmp_path, "add", "--target", "南网科技")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "已加入选股池" in second.stdout
    data = json.loads(pool_file(tmp_path).read_text(encoding="utf-8"))
    assert len(data["items"]) == 1
    assert data["items"][0]["name"]
    assert data["items"][0]["status"] in {"执行", "观察", "淘汰"}


def test_pool_capacity_rejects_eleventh_unique_record(tmp_path: Path) -> None:
    for index in range(10):
        item = run_pool(tmp_path, "add", "--target", f"测试{index}", "--offline")
        assert item.returncode == 0, item.stderr

    extra = run_pool(tmp_path, "add", "--target", "测试10", "--offline")

    assert extra.returncode == 3
    assert "候选池容量已满：10/10" in extra.stdout
    data = json.loads(pool_file(tmp_path).read_text(encoding="utf-8"))
    assert len(data["items"]) == 10


def test_show_plan_and_review_contracts(tmp_path: Path) -> None:
    add = run_pool(tmp_path, "add", "--target", "南网科技")
    assert add.returncode == 0, add.stderr

    show = run_pool(tmp_path, "show")
    assert show.returncode == 0, show.stderr
    assert "选股池" in show.stdout
    assert "1/10" in show.stdout

    plan = run_pool(tmp_path, "plan")
    assert plan.returncode == 0, plan.stderr
    assert "选股池盘后分析" in plan.stdout
    assert "评分总览" in plan.stdout
    assert "交易指导" in plan.stdout
    assert (tmp_path / ".trader" / "last_plan.json").exists()

    review = run_pool(tmp_path, "review")
    assert review.returncode == 0, review.stderr
    assert "选股池次日复盘" in review.stdout
    assert "复盘命中表" in review.stdout


def test_rank_outputs_pool_action_comparison(tmp_path: Path) -> None:
    first = run_pool(tmp_path, "add", "--target", "测试A", "--offline")
    second = run_pool(tmp_path, "add", "--target", "测试B", "--offline")
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    rank = run_pool(tmp_path, "rank")

    assert rank.returncode == 0, rank.stderr
    assert "持仓排序" in rank.stdout


def test_remove_deletes_record(tmp_path: Path) -> None:
    add = run_pool(tmp_path, "add", "--target", "南网科技")
    assert add.returncode == 0, add.stderr

    removed = run_pool(tmp_path, "remove", "--target", "南网科技")

    assert removed.returncode == 0, removed.stderr
    assert "已移除" in removed.stdout
    data = json.loads(pool_file(tmp_path).read_text(encoding="utf-8"))
    assert data["items"] == []
