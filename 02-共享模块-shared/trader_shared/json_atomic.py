"""JSON 持久化：锁内 RMW + tmp/fsync/replace。

对齐 structure_core.save_trailing_watermark 模式；供 buy_point_lifecycle /
chip_history / wyckoff_phase / position_add_store 共用（审计 M2/M8）。
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any, Callable


def load_json_dict(path: Path) -> dict[str, Any]:
    """无锁读取；损坏/缺失 → {}。"""
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8") or "{}")
            if isinstance(raw, dict):
                return raw
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        pass
    return {}


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """已持锁前提下：tmp + fsync + replace。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def locked_rmw_json(
    path: Path,
    mutator: Callable[[dict[str, Any]], dict[str, Any] | None],
    *,
    skip_on_corrupt: bool = False,
) -> dict[str, Any]:
    """fcntl.LOCK_EX 包住 load→mutate→atomic write。

    mutator(data) → 新 data；返回 None 表示跳过写入（仍返回读到的 data）。
    skip_on_corrupt：文件损坏时不写（对齐 watermark 防抹其它键）。
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a", encoding="utf-8") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            data: dict[str, Any] = {}
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
                except (json.JSONDecodeError, OSError):
                    if skip_on_corrupt:
                        return {}
                    raw = {}
                if not isinstance(raw, dict):
                    if skip_on_corrupt:
                        return {}
                    raw = {}
                data = raw
            updated = mutator(data)
            if updated is None:
                return data
            if not isinstance(updated, dict):
                raise TypeError("mutator must return dict or None")
            atomic_write_json(path, updated)
            return updated
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
