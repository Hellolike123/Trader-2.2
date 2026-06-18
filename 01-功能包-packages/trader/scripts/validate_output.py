#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys

import trader_shared
from trader_shared.schema.v1 import validate_trader
validate = validate_trader

# 融合层方向校验：emoji 必须与加权分方向一致
_DIRECTION_EMOJI = {"🟢", "🔴", "🟡", "⚪", "🟠"}
_BEARISH_EMOJI = {"🔴", "🟠"}
_BULLISH_EMOJI = {"🟢"}
_NEUTRAL_EMOJI = {"⚪", "🟡"}

# 禁止用语（额外补充 schema/v1.py 中的 banned list）
_EXTRA_BANNED = (
    "肯定", "一定", "guaranteed", "黑马", "妖股", "翻倍股",
    "抄底信号", "逃顶信号",
)


def _check_fusion_direction(markdown: str) -> list[str]:
    """校验融合层方向是否与加权分一致。"""
    errors: list[str] = []
    # 匹配融合｜emoji action（加权分 X.XX，置信度 XX%）
    pattern = r"融合[｜|]\s*(🟢|🔴|🟡|⚪|🟠)\s*(.+?)（加权分\s*([-\d.]+)"
    m = re.search(pattern, markdown)
    if not m:
        return errors  # 没有融合行，跳过
    emoji = m.group(1)
    score_str = m.group(3)
    try:
        score = float(score_str)
    except ValueError:
        return errors
    if score >= 0.25 and emoji not in _BULLISH_EMOJI:
        errors.append(f"fusion direction mismatch: score={score:.2f} (strong bullish) but emoji={emoji}")
    elif 0.1 <= score < 0.25 and emoji != "🟡":
        errors.append(f"fusion direction mismatch: score={score:.2f} (weak bullish) but emoji={emoji}")
    elif -0.05 <= score < 0.1 and emoji not in _NEUTRAL_EMOJI:
        errors.append(f"fusion direction mismatch: score={score:.2f} (neutral) but emoji={emoji}")
    elif -0.12 <= score < -0.05 and emoji != "🟡":
        errors.append(f"fusion direction mismatch: score={score:.2f} (weak bearish) but emoji={emoji}")
    elif -0.2 <= score < -0.12 and emoji != "🟠":
        errors.append(f"fusion direction mismatch: score={score:.2f} (lean bearish) but emoji={emoji}")
    elif score < -0.2 and emoji not in _BEARISH_EMOJI:
        errors.append(f"fusion direction mismatch: score={score:.2f} (strong bearish) but emoji={emoji}")
    return errors


def _check_extra_banned(markdown: str) -> list[str]:
    """校验额外禁止用语。"""
    errors: list[str] = []
    for term in _EXTRA_BANNED:
        if term in markdown:
            errors.append(f"banned term found: '{term}'")
    return errors


def _check_price_grounding(markdown: str, json_path: str | None) -> list[str]:
    """校验输出中的价格数字是否在 JSON 源数据中出现过。"""
    errors: list[str] = []
    if not json_path:
        return errors
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return errors

    # 提取 JSON 中所有价格数字
    json_prices: set[str] = set()
    for key in ("current", "support", "resistance", "confirm", "stop",
                "low_zone_lower", "low_zone_upper", "high_zone_lower", "high_zone_upper",
                "fib_ext_1382", "fib_ext_1618", "trailing_stop"):
        val = data.get(key)
        if val is not None:
            try:
                json_prices.add(f"{float(val):.2f}")
            except (ValueError, TypeError):
                pass

    if not json_prices:
        return errors

    # 从输出中提取所有 XX.XX 格式的价格
    output_prices = set(re.findall(r"\d+\.\d{2}", markdown))
    # 允许输出中有 JSON 中没有的价格（如 MA、ATR 等衍生值）
    # 只检查关键价位是否至少有一部分来自 JSON
    key_prices_found = output_prices & json_prices
    if not key_prices_found and json_prices:
        errors.append(f"no JSON-grounded prices found in output (expected at least one of {json_prices})")
    return errors


def _read_text(path: str | None) -> str:
    if path is None:
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Hermes Trader V2 markdown.")
    parser.add_argument("path", nargs="?")
    parser.add_argument("--json", dest="json_path", help="Source JSON file for price grounding check")
    args = parser.parse_args()
    markdown = _read_text(args.path)
    errors = validate(markdown)

    # 额外校验
    errors.extend(_check_fusion_direction(markdown))
    errors.extend(_check_extra_banned(markdown))
    errors.extend(_check_price_grounding(markdown, args.json_path))

    if errors:
        for error in errors:
            print(error)
        return 1
    print("VALID_TRADER_OUTPUT=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
