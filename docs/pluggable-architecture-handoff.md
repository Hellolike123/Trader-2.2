---
title: "Agent Skill Pluggable Architecture & Chip Distribution Metrics"
slug: "agentic-finance-pluggable-arch-v2"
description: "Unified score/livermore rules via YAML, 30s realtime caching, independent chip distribution module, integrated into trader/review outputs."
categories: ["Agent", "Infrastructure"]
verification: "tested_pass"
tools:
  - "rule_engine.py"
  - "chip_distribution.py"
---

# Agent Skill Pluggable Architecture

This document details the refactoring of the A-share analysis system into a pluggable architecture, replacing hardcoded logic with configurable YAML rules, adding an independent chip distribution metric module, and optimizing data retrieval with caching.

## Overview

### 1. Configuration & Decision Engine
Replaced hardcoded if/chains in scoring and position sizing with **Sandboxed YAML Rule Engines**.

| Component                | Rules (YAML)          | Behavior                                              |
|--------------------------|-----------------------|-------------------------------------------------------|
| `score_rules.yml`        | 9 rules               | Modifies scores for conditions (-40, +10, etc.)       |
| `livermore_rules.yml`    | 6 rules               | Determines pyramid tier (1 to 5) for加仓 rules        |
| `status_rules.yml`       | 10 rules              | Determines market status (e.g., `低吸观察`, `暂不碰`)  |

**Usage pattern:** If YAML fails to load, the engine gracefully falls back to hardcoded Python logic.

### 2. Standalone Chip Distribution Metrics
New module `chip_distribution.py` in the shared index for calculating approximate chip distribution (volume accumulation at price levels).

- **Standard Formula**: Distributes daily volume evenly across daily High/Low ranges.
- **Total Conservation Verified**: `total_chip == total_original_volume` (0% deviation).
- **Outputs**: `peaks` (top 3 concentration zones by volume), `mid_price` (50% percentile).

## API Usage

All modules are accessed via the shared interface.

```python
# 1. Pluggable Rules (Score)
from trader_shared.modifier_rule_engine import apply_score_modifiers
modifier = apply_score_modifiers(item_dict) 

# 2. Pluggable Rules (LIVEMORE / Scale)
from trader_shared.modifier_rule_engine import apply_livermore_scale
tier = apply_livermore_scale(status="优先候选", score=85) # -> Returns 3

# 3. New Chip Distribution Module
from trader_shared.chip_distribution import calc_chip_distribution
from light_data import load_market_snapshot

snapshot = load_market_snapshot('南网科技', days=20)
daily_bars = snapshot.daily_bars
result = calc_chip_distribution(daily_bars)

print(result['peaks'])
# [{'price': 56.68, 'volume': 4363721, 'share_of_total': 4.05, 'support_level': '强支撑'}, ...]
```

## Integration into Review & Trader

| Module         | Feature Integration                                     |
|----------------|---------------------------------------------------------|
| `review_core`  | `build_review()` now includes `chip_distribution` data. |
| `review_render`| Added Chip Distribution section (`📊 筹码`) to markdown output. |
| `review_compare`| Merged chip data into multi-stock comparison views.   |
| `final_review` | Fixed `sys.path` dependency graph for running standalone. |

## Verification & Test Results

- **Test Suite**: `146 passed`, 1 pre-existing failure (`test_fill`).
- **Formula Check**: `total_chip` exactly equals sum of daily volumes (0% deviation).
- **Cache Latency**: `fetch_quote()` returns cached value in < 1ms if within 30 seconds.
