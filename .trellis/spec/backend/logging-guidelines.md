# Logging Guidelines

> How logging and output are handled in this project.

---

## Overview

This project does **not** use Python's `logging` module. Instead, it uses two output channels:

1. **`print()` to stdout** — User-facing reports (Markdown output for WeChat/mobile)
2. **`print(..., file=sys.stderr)` to stderr** — Operational warnings and debug info
3. **`warnings.warn()`** — Deprecation and non-fatal issues

The final output is pushed to WeChat/mobile, so all user-facing output must follow strict formatting rules (see Output Format section below).

---

## Output Channels

### stdout — User-Facing Reports

All skill output goes to stdout. The format must be **plain text compatible with WeChat/mobile rendering**:

```python
# From final_report.py — stdout is the report
print(render_markdown(report))
```

### stderr — Operational Messages

Debug info, warnings, and operational messages go to stderr:

```python
# From decision_core.py
print(f"WARN: rule engine loaded from {rules_path} but evaluation failed: {exc}", file=sys.stderr)

# From run_analysis.py
import warnings
warnings.warn(
    "[trader] shared module not available — pool operations disabled.",
    stacklevel=2,
)
```

### Signal Store — Structured Event Logging

The `signals.jsonl` file serves as the structured event log. All significant events (T0 triggers, analysis signals, review results) are written here:

```python
from trader_shared.signal_store import append_signal

append_signal({
    "source_skill": "t0",
    "symbol": "688248.SH",
    "signal_type": "low_buy_triggered",
    "direction": "bullish",
    "action": "low_buy",
    "confidence": "high",
    "trigger": {"price": 57.50, "reason": "到达低吸区"},
})
```

---

## What to Log

### Always Log (to stderr)

- Module import failures (fallback activation)
- Data source failover events (mootdx → Tencent → Sina)
- Cache corruption or parse failures
- Signal validation failures
- Unexpected data shapes (missing fields, wrong types)

### Log to `signals.jsonl`

- T0 state changes (trigger price reached, big order detected)
- Analysis signals (buy/sell/hold decisions)
- Review results (post-market assessment)
- Pool changes (add/remove stock)

### Never Log

- Raw API response bodies (too verbose)
- Full K-line data arrays
- User credentials or API keys
- PII (there's none in this system, but be aware)

---

## Output Format Rules (WeChat/Mobile Critical)

All user-facing output must follow these rules. Violating them breaks WeChat rendering.

### Forbidden Markdown

| Element | Status | Alternative |
|---------|--------|-------------|
| `#` headings | FORBIDDEN | Use emoji + plain text (e.g., `🧭 简要分析`) |
| `---` / `***` horizontal rules | FORBIDDEN | Use blank lines |
| `**bold**` | FORBIDDEN | Use emoji prefixes (📍 ❗ 🔴 🟢) |
| `|...|` tables | FORBIDDEN | Use `｜` (full-width pipe) inline |
| `>` blockquotes | FORBIDDEN | Direct text |
| `*` / `-` list markers | FORBIDDEN | Use `·` prefix or plain lines |
| `①②③` circled numbers | FORBIDDEN | Use plain numbers or `·` |

### Required Format

Every report must start with a fixed emoji + title:

```
分析报告 — 南网科技（688248）

现价：59.33元（+2.70%）
MA5：59.63 ｜ MA10：60.74 ｜ MA20：60.60

🧭 简要分析
基础状态：防守观察 ｜ 体系结论：防守观察

📍 决策
状态：防守观察
  空仓：在 57.50-58.64元 试探买 5%, 止损 56.11
```

### Emoji Section Headers

Use these standard emoji prefixes for sections:

| Emoji | Section |
|-------|---------|
| 🧭 | 简要分析 (Brief Analysis) |
| 📍 | 决策 (Decision) |
| ❗ | 关键价位 (Key Price Levels) |
| ✨ | 亮点与风险 (Highlights & Risks) |
| 📊 | 关键价位 / 持仓速览 |
| 🔎 | 分时走势与大单回溯 |
| 📈 | 五层打分 / 仓位建议 |
| 🎯 | T0 触发价 |
| 🔔 | 决策信号 |
| 💡 | 操作信号 |

---

## Print Patterns in the Codebase

### Debug Output (stderr)

```python
# Pattern: prefix with module name, use stderr
print(f"[light_data] mootdx timeout, falling back to Tencent HTTP", file=sys.stderr)
print(f"[market_env] cache bloat detected: {len(bars)} bars, deduplicating", file=sys.stderr)
```

### Warning Pattern

```python
import warnings
warnings.warn(
    "[trader] shared module not available — signal tracking disabled.",
    stacklevel=2,  # Always use stacklevel=2
)
```

### Fusion Log (Conditional)

```python
# From fusion_core.py — conditional debug logging
FUSION_LOG_ONLY = os.environ.get("FUSION_LOG_ONLY", "false").lower() in ("true", "1", "yes")

def _log_fusion(result: dict) -> None:
    """Print fusion debug log. Only catches JSON errors, not logic errors."""
    try:
        log_data = {k: v for k, v in result.items() if k != "signals_detail"}
        print(f"[fusion] {json.dumps(log_data, ensure_ascii=False, default=str)}", file=sys.stderr)
    except Exception:
        pass
```

---

## Environment Variable Debug Controls

Several modules support debug logging via environment variables:

| Variable | Effect |
|----------|--------|
| `FUSION_LOG_ONLY=true` | Log fusion decisions without changing behavior |
| `THEORY_ADJUST_LOG_ONLY=true` | Log theory adjustments without applying them |
| `BAYESIAN_FUSION=true` | Enable Bayesian fusion (logs posterior probabilities) |
| `HMM_REGIME_ENABLED=false` | Disable HMM regime detection |

---

## Common Mistakes

1. **Printing to stdout in shared modules**: Shared modules should never print user-facing output. Use stderr for debug/warnings.

2. **Using `logging` module**: This project doesn't use `logging`. Don't introduce it — use `print()` to stderr instead.

3. **Emoji in stderr messages**: Debug output should be plain ASCII for terminal compatibility.

4. **Forgetting `stacklevel=2`**: Always use `stacklevel=2` in `warnings.warn()` so the warning points to the caller.

5. **Printing full data structures**: Don't `print(large_list)` — print a summary (count, first/last item).
