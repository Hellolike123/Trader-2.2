from __future__ import annotations
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any
import fcntl
import time
from datetime import datetime
from contextlib import contextmanager
from typing import Iterator

from trader_shared._logging import get_logger

_logger = get_logger(__name__)

# 线程本地：记录当前线程已持有的锁 key，避免重入死锁
_thread_lock_keys: threading.local = threading.local()


def _get_lock_keys() -> set[str]:
    if not hasattr(_thread_lock_keys, "keys"):
        _thread_lock_keys.keys: set[str] = set()
    return _thread_lock_keys.keys


class DataManager:
    """
    统一数据总线管理器
    一站式接管所有模块的状态读写，彻底消除数据孤岛与多进程写冲突。
    统一存储目录: ~/.trader/
    """
    
    ROOT_DIR = Path.home() / ".trader"
    SIGNALS_FILE = ROOT_DIR / "signals.jsonl"
    
    @classmethod
    def _init_dir(cls):
        cls.ROOT_DIR.mkdir(parents=True, exist_ok=True)
        
    @classmethod
    @contextmanager
    def state_lock(cls, key: str, path: Path | None = None) -> Iterator[None]:
        """获取独占锁（可重入：同一线程重复调用自动跳过）"""
        lock_path = cls._get_state_path(key, path).with_name(f"{key}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        keys = _get_lock_keys()
        if key in keys:
            yield  # 已持有锁，直接放行
            return
        keys.add(key)
        with lock_path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                keys.discard(key)
        
    @classmethod
    def _get_state_path(cls, key: str, path: Path | None = None) -> Path:
        if path:
            return path
        cls._init_dir()
        return cls.ROOT_DIR / f"{key}.json"
        
    @classmethod
    def load_state(cls, key: str, default: Any = None, path: Path | None = None) -> Any:
        """读取指定模块的状态缓存（使用 state_lock 确保与 save_state 互斥）"""
        if default is None:
            default = {}

        target_path = cls._get_state_path(key, path)
        if not target_path.exists():
            return default

        try:
            # 使用 state_lock 的共享锁模式：与 save_state 的独占锁互斥
            with cls._read_lock(key, path):
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data
        except (json.JSONDecodeError, OSError) as e:
            # 文件损坏时自动备份并返回默认值
            _logger.warning("State file corrupted for %s, creating backup: %s", key, e)
            backup = target_path.with_suffix(target_path.suffix + f".broken-{datetime.now().strftime('%Y%m%d%H%M%S')}")
            shutil.copy2(target_path, backup)
            return default

    @classmethod
    @contextmanager
    def _read_lock(cls, key: str, path: Path | None = None) -> Iterator[None]:
        """获取读取锁（如果已在 state_lock 内则跳过，避免死锁）"""
        keys = _get_lock_keys()
        if key in keys:
            yield  # 已持有 state_lock，跳过
            return
        lock_path = cls._get_state_path(key, path).with_name(f"{key}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @classmethod
    def save_state(cls, key: str, data: Any, path: Path | None = None) -> None:
        """
        保存指定模块的状态缓存（原子写入 + 排他锁覆盖整个写操作）
        """
        target_path = cls._get_state_path(key, path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(target_path.suffix + f".tmp.{os.getpid()}")

        # 写入临时文件
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # 使用 state_lock 独占锁保护 os.replace（原子替换）
        with cls.state_lock(key, path):
            try:
                os.replace(tmp_path, target_path)
            except OSError:
                # 如果目标文件已存在但 replace 失败，尝试覆盖
                if tmp_path.exists():
                    os.replace(tmp_path, target_path)

    @classmethod
    def update_state(cls, key: str, updater: Any, path: Path | None = None) -> Any:
        """原子化 read-modify-write：在独占锁内完成读取、修改、写入。

        Parameters
        ----------
        key : str
            状态键名。
        updater : callable
            ``(data) -> None``，在锁内被调用，就地修改 data。
            返回修改后的 data（通常就是入参本身）。
        path : Path | None
            可选：覆盖默认路径。

        Returns
        -------
        修改后的 data dict/list。

        用法::

            data = DataManager.update_state("pool", lambda d: d.setdefault("items", []))
            # 或者用显式回调：
            def _mutate(d):
                d["items"].append(new_item)
                d["updated_at"] = now()
            data = DataManager.update_state("pool", _mutate)
        """
        with cls.state_lock(key, path):
            target_path = cls._get_state_path(key, path)
            default: Any = {}
            if not target_path.exists():
                data = default
            else:
                try:
                    with open(target_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    data = default
            updater(data)
            # 原子写回
            tmp_path = target_path.with_suffix(target_path.suffix + f".tmp.{os.getpid()}")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target_path)
            return data

    @classmethod
    def load_signals(cls, path: Path | None = None) -> list[dict[str, Any]]:
        """读取完整的信号事件流（委托给 signal_store 统一路径）"""
        cls._init_dir()
        target_path = path or cls.SIGNALS_FILE
        from trader_shared.signal_store import _read_store
        return _read_store(target_path)

    @classmethod
    def append_signal(cls, signal: dict[str, Any], path: Path | None = None) -> None:
        """向 signals.jsonl 安全追加单条信号"""
        cls._init_dir()
        target_path = path or cls.SIGNALS_FILE
        target_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(signal, ensure_ascii=False, default=str) + "\n"
        
        with open(target_path, "a", encoding="utf-8") as f:
            # 独占锁，确保多进程安全追加
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f, fcntl.LOCK_UN)
