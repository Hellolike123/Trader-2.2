# -*- coding: utf-8 -*-
"""阶段间传递的上下文对象（避免 builder 海量 dict 解包）。"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Mapping


class StageContext(SimpleNamespace):
    """轻量命名空间：支持 dict 构造与 .get 兼容。"""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "StageContext":
        return cls(**dict(data or {}))

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)
