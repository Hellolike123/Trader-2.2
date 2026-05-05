---
name: trader
description: Cross-platform trading analysis base skill for multi-agent, web, and mobile use. Supports unified request/response, pluggable data sources, structural analysis, multi-theory reasoning, decision convergence, and multiple presentation formats.
version: 0.5.0-base-architecture
author: Trader Skill
license: MIT
platforms: [macos, linux]
tags: [finance, stocks, a-share, terminal, python, agent, web, mobile]
metadata:
  hermes:
    tags: [Finance, AShare, Terminal, Python, Agent]
    requires_toolsets: [terminal]
  openclaw:
    requires:
      bins: [python3]
dependencies: [python3]
repository: local
documentation: SKILL.md
---

# Trader

## Core Positioning
`trader` is a trading analysis base skill. It is not a BI dashboard and not a fixed-command script. It provides a reusable analysis core that can be consumed by agents, web apps, mini programs, or any other front end.

The skill is built around five layers:
- data layer
- structure layer
- theory reasoning layer
- decision convergence layer
- presentation layer

The layers below the presentation layer are the stable base. The presentation layer is the easiest part to replace.

## Operating Principle
Use intent-driven analysis, not fixed trigger words.

The caller may ask for:
- single stock analysis
- multi-stock comparison
- theory explanation
- decision guidance
- review
- monitoring
- position planning

The skill should route the request into the correct analysis path and return a standardized response.

## Request / Response Model
### Request
A request should contain:
- `target`
- `target_type`
- `analysis_mode`
- `scene`
- `context`
- `options`

### Response
A response should contain:
- `status`
- `summary`
- `data`
- `structure`
- `theories`
- `decision`
- `display`

## Layer Responsibilities
### Data Layer
Collect market facts and historical facts. Data sources should be pluggable. The layer may add, remove, or replace providers as long as the output contract stays stable.

### Structure Layer
Convert raw data into theory-readable structure summaries. This layer should describe trend, stage, support, resistance, volume-price relationship, volatility, momentum, and risk structure.

### Theory Reasoning Layer
Run multiple independent theory modules in parallel. Each theory module is pluggable and should return a standard opinion record.

### Decision Convergence Layer
Merge theory outputs with hard constraints and scene context. This layer applies weighting, hard veto rules, disagreement handling, and final state mapping.

### Presentation Layer
Render the final decision for different consumers. The same decision can be shown as Markdown, JSON, cards, web components, or mini program components.

## Theory Module Contract
Each theory module should accept:
- `structure`
- `market_data`
- `context`
- `theory_config`
- `hard_constraints`
- `available_signals`

Each theory module should return:
- `theory_name`
- `role`
- `version`
- `status`
- `bias`
- `confidence`
- `key_reason`
- `suggested_action`
- `risk_flags`
- `weight`
- `bias_score`
- `confidence_score`
- `risk_score`
- `priority`
- `evidence`
- `reasoning_chain`
- `uncertainty`

### Theory Status
- `ok`: theory is valid and can participate in convergence
- `skipped`: theory does not apply to this scene
- `insufficient`: theory applies, but input data is not enough
- `failed`: theory should run, but required fields are missing or internal computation failed

## Decision Rules
The decision layer should follow this order:
1. handle hard vetoes first
2. filter non-`ok` theories
3. apply unified weighting
4. calculate disagreement level
5. map the result into a final state

### Final States
- `低吸观察`
- `等转强`
- `防守观察`
- `冲高减仓`
- `暂不碰`
- `风险止损`
- `空间不足`

### Required Decision Outputs
- `final_status`
- `final_direction`
- `final_action`
- `final_confidence`
- `trigger`
- `invalidation`
- `summary`
- `hard_reasons`
- `soft_reasons`
- `risk_flags`
- `disagreement_level`
- `disagreement_reason`

## Position System
The position system is part of the base, but it is split into two responsibilities.

### Position Management
Position management defines the risk boundary and capital discipline. It answers what is the maximum allowed exposure.

### Position Rotation
Position rotation handles dynamic allocation within the boundary. It answers how to distribute capital across candidates.

### Recommended Position Outputs
- `position_mode`
- `max_total_pct`
- `max_single_pct`
- `cash_pct`
- `rotation_candidate`
- `primary_position`
- `secondary_position`
- `risk_flags`
- `summary`

## Presentation Rules
The presentation layer only explains the result. It must not recompute theory scores or re-decide the outcome.

### Default Presentation Blocks
- conclusion block
- key evidence block
- theory summary block
- follow-up block

### Presentation Modes
- `compact`
- `expanded`

### Presentation Outputs
- Markdown
- JSON
- card UI
- web components
- mini program components

## Plug-in Principle
The system follows a stable-interface, plug-in-inside-each-layer design.
- data sources can be replaced
- structure analyzers can be added or removed
- theory modules can be added or removed
- decision rules can be extended
- presentation renderers can be replaced

The interface between layers must remain stable.

## Applicability
This skill is suitable for:
- single stock analysis
- intraday monitoring
- post-close review
- stock pool management
- position rotation
- multi-stock comparison
- future web / mini program rendering

## Usage Notes
- Do not depend on a fixed trigger word.
- Use the skill as a reusable analysis base.
- Keep the base stable and let the presentation layer change freely.
- Prefer structured outputs that can be consumed by multiple agents.

## Minimal Working Rule
If the caller only provides a stock name or code, the skill should still be able to route to the default single-stock analysis path and produce a standard response.
