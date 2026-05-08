"""Light data: qfqday fallback to day for newly listed stocks."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Ensure light_data.py is importable
import sys, pathlib
_market_data = pathlib.Path(__file__).resolve().parent.parent / "01-行情数据-market-data"
if str(_market_data) not in sys.path:
    sys.path.insert(0, str(_market_data))

import light_data
from light_data import HttpClient, Security


def _make_rows(pairs: list[tuple[str, float, float, float, float, float]]) -> list[list[Any]]:
    """Build Tencent-style rows."""
    return [[d, o, c, h, l, v] for d, o, c, h, l, v in pairs]


def _mock_http(qfqday: list[list[Any]] | None = None, day: list[list[Any]] | None = None) -> MagicMock:
    """Return a MagicMock HttpClient that returns the given rows."""
    http = MagicMock(spec=HttpClient)
    sec = MagicMock()
    sec.qq_symbol = "688248.SZ"

    payload = {"data": {"688248.SZ": {}}}
    result_dict = payload["data"]["688248.SZ"]
    if qfqday is not None:
        result_dict["qfqday"] = qfqday
    if day is not None:
        result_dict["day"] = day

    raw = str(result_dict).replace("'", '"')
    http.get_text.return_value = f"_var = {raw}"
    return http, sec


class TestQfqDayFallback:
    """Verify that fetch_qfq_daily falls back to day when qfqday is empty."""

    def test_qfqday_produces_bars(self) -> None:
        days = _make_rows([
            ("2026-05-07", 20.00, 20.50, 21.00, 19.80, 50000),
            ("2026-05-08", 20.50, 21.00, 21.50, 20.30, 60000),
        ])
        http, sec = _mock_http(qfqday=days)

        # patch extract_jsonp to return the dict payload directly
        with patch("light_data.extract_jsonp", side_effect=lambda text: _parse_jsonp(text)):
            bars = light_data.fetch_qfq_daily(sec, http, days=30)
        assert len(bars) == 2
        assert bars[0]["date"] == "2026-05-07"
        assert bars[0]["close"] == 20.50
        assert bars[0]["volume"] == 50000.0

    def test_qfqday_empty_fallbacks_to_day(self) -> None:
        day_rows = _make_rows([
            ("2026-02-01", 30.00, 30.50, 31.00, 29.50, 10000),
            ("2026-02-02", 30.50, 31.00, 31.50, 30.00, 12000),
            ("2026-02-03", 31.00, 31.50, 32.00, 30.80, 15000),
        ])
        http, sec = _mock_http(day=day_rows)  # qfqday=None → empty

        with patch("light_data.extract_jsonp", side_effect=lambda text: _parse_jsonp(text)):
            bars = light_data.fetch_qfq_daily(sec, http, days=30)
        assert len(bars) == 3
        assert bars[0]["close"] == 30.50
        assert bars[2]["close"] == 31.50

    def test_qfqday_empty_and_day_empty_raises(self) -> None:
        http, sec = _mock_http()  # both qfqday and day are empty

        with patch("light_data.extract_jsonp", side_effect=lambda text: _parse_jsonp(text)):
            with pytest.raises(RuntimeError, match="Tencent qfq daily bars unavailable"):
                light_data.fetch_qfq_daily(sec, http, days=30)

    def test_qfqday_nonempty_is_not_fallback(self) -> None:
        """qfqday has data → should NOT read day field."""
        qfqday = _make_rows([
            ("2026-05-08", 40.00, 40.50, 41.00, 39.50, 20000),
        ])
        day = _make_rows([
            ("2026-02-01", 30.00, 30.50, 31.00, 29.50, 10000),
            ("2026-02-02", 30.50, 31.00, 31.50, 30.00, 12000),
        ])
        http, sec = _mock_http(qfqday=qfqday, day=day)

        with patch("light_data.extract_jsonp", side_effect=lambda text: _parse_jsonp(text)):
            bars = light_data.fetch_qfq_daily(sec, http, days=30)
        # Should get exactly the qfqday bar, not the day bars
        assert len(bars) == 1
        assert bars[0]["close"] == 40.50


def _parse_jsonp(text: str) -> dict:
    """Minimal JSONP extraction: strip _var = prefix."""
    if text.startswith("_var = "):
        text = text[7:]
    return eval(text)  # noqa: S307
