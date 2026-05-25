from __future__ import annotations
import json
import os
import shutil
from pathlib import Path
from typing import Any
import fcntl
import time
from datetime import datetime
from contextlib import contextmanager
from typing import Iterator

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
        lock_path = cls._get_state_path(key, path).with_name(f"{key}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        
    @classmethod
    def _get_state_path(cls, key: str, path: Path | None = None) -> Path:
        if path:
            return path
        cls._init_dir()
        return cls.ROOT_DIR / f"{key}.json"
        
    @classmethod
    def load_state(cls, key: str, default: Any = None, path: Path | None = None) -> Any:
        """读取指定模块的状态缓存"""
        if default is None:
            default = {}
            
        target_path = cls._get_state_path(key, path)
        if not target_path.exists():
            return default
            
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                # 申请共享锁 (读锁)
                fcntl.flock(f, fcntl.LOCK_SH)
                data = json.load(f)
                fcntl.flock(f, fcntl.LOCK_UN)
                return data
        except Exception as e:
            # 文件损坏时自动备份并返回默认值
            backup = target_path.with_suffix(target_path.suffix + f".broken-{datetime.now().strftime('%Y%m%d%H%M%S')}")
            shutil.copy2(target_path, backup)
            return default
            
    @classmethod
    def save_state(cls, key: str, data: Any, path: Path | None = None) -> None:
        """
        保存指定模块的状态缓存（原子写入 + 排他锁）
        """
        target_path = cls._get_state_path(key, path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(target_path.suffix + f".tmp.{os.getpid()}")
        
        # 写入临时文件
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
            
        # 原子替换（POSIX 下安全，覆盖旧文件）
        try:
            # 尝试在目标文件上加独占锁（写锁），确保其他进程没有在读取它
            if target_path.exists():
                with open(target_path, "r") as old_f:
                    fcntl.flock(old_f, fcntl.LOCK_EX)
                    os.replace(tmp_path, target_path)
                    fcntl.flock(old_f, fcntl.LOCK_UN)
            else:
                os.replace(tmp_path, target_path)
        except OSError:
            # Fallback 强制替换
            os.replace(tmp_path, target_path)

    @classmethod
    def load_signals(cls, path: Path | None = None) -> list[dict[str, Any]]:
        """读取完整的信号事件流"""
        cls._init_dir()
        target_path = path or cls.SIGNALS_FILE
        if not target_path.exists():
            return []
            
        results = []
        with open(target_path, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            for line in f:
                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            fcntl.flock(f, fcntl.LOCK_UN)
        return results

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
