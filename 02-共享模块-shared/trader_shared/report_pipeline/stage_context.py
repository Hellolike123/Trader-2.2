# -*- coding: utf-8 -*-
"""阶段间传递的上下文对象（避免 builder 海量 dict 解包）。"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Mapping


class StageContext(SimpleNamespace):
    """轻量命名空间：支持 dict 构造、update 累积与 .get 兼容。

    build_report 用单一 bag：各 stage 返回后 ``ctx.update(...)``，
    assemble/attach 从 ctx 取 kwargs，禁止平行 locals 双真相。
    """

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "StageContext":
        return cls(**dict(data or {}))

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def update(
        self, data: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> "StageContext":
        if data:
            self.__dict__.update(dict(data))
        if kwargs:
            self.__dict__.update(kwargs)
        return self

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)
