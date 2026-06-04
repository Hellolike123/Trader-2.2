def _load_historical_win_rate(symbol: str) -> dict | None:
    import os
    import json
    path = os.path.expanduser("~/.trader/signal_results.jsonl")
    if not os.path.exists(path):
        return None

    normalized_symbol = symbol.replace(".SH", "").replace(".SZ", "").strip()

    trades = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    res_rec = json.loads(line)
                    r_symbol = str(res_rec.get("symbol") or "")
                    r_name = str(res_rec.get("name") or "")
                    norm_r_symbol = r_symbol.replace(".SH", "").replace(".SZ", "").strip()
                    if normalized_symbol == norm_r_symbol or normalized_symbol == r_name:
                        trades.append(res_rec)
                except Exception:
                    continue
    except Exception:
        return None

    if len(trades) < 5:
        return None

    total = len(trades)
    wins = 0
    total_gains = 0.0
    total_losses = 0.0
    max_gain = -999.0
    max_loss = 999.0

    for t in trades:
        pnl = t.get("return_pct")
        if pnl is None:
            pnl = t.get("r_5d")
        if pnl is None:
            pnl = t.get("pnl_pct", 0.0)
        pnl = float(pnl)

        if pnl > 0:
            wins += 1
            total_gains += pnl
        else:
            total_losses += abs(pnl)

        if pnl > max_gain:
            max_gain = pnl
        if pnl < max_loss:
            max_loss = pnl

    win_rate = (wins / total) * 100
    eps = 0.001
    profit_factor = (total_gains + eps) / (total_losses + eps)
    avg_pnl = sum(float(t.get("return_pct") or t.get("r_5d") or t.get("pnl_pct", 0.0)) for t in trades) / total

    if win_rate >= 60.0 and profit_factor >= 1.5:
        conclusion = "系统在该股表现出高度适应性，信号极具参考价值"
    elif win_rate < 45.0:
        conclusion = "易发生磨损（低胜率），需谨慎跟单，建议降低单笔仓位"
    else:
        conclusion = "表现中性，正常参考"

    return {
        "total": total,
        "wins": wins,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_pnl": avg_pnl,
        "max_gain": max_gain,
        "max_loss": max_loss,
        "conclusion": conclusion
    }


def render_markdown(r: dict) -> str:
    ma = r.get("ma") or {}
    ma_raw = r.get("ma_raw") or ma
    display_code = str(r.get("symbol", "")).replace(".SH", "").replace(".SZ", "")
    name = str(r.get("name", ""))

    atr14 = float(r.get("atr14", 0) or 0)
    atr_ratio = float(r.get("atr_ratio", 0) or 0)
    atr_level = str(r.get("atr_level") or "")

    confirm = float(r.get("confirm") or 0)
    low_price = float(r.get("support") or 0)
    stop = float(r.get("stop") or 0)
    resistance_val = float(r.get("resistance") or 0)
    current_price = float(r.get("current") or 0)
    change_pct = float(r.get("change_pct") or 0)
    position_cap = int(r.get("position_cap") or 10)

    major_stage = str(r.get("major_stage") or "")
    if not major_stage:
        old_stage = str(r.get("stage") or "")
        stage_map = {
            "修复": "蓄势",
            "走强": "主升",
            "震荡": "派发",
            "转弱": "衰退",
        }
        major_stage = stage_map.get(old_stage, old_stage)
    momentum = str(r.get("short_term_momentum") or "")
    
    stage_action_map = {
        "蓄势": "低吸高抛",
        "主升": "持股待涨",
        "派发": "逢高减仓",
        "衰退": "不碰",
    }
    stage_action_text = stage_action_map.get(major_stage, major_stage)
    
    ma5_text = f"{ma_raw.get('ma5', 0):.2f}" if isinstance(ma_raw.get("ma5"), (int, float)) else "--"
    ma10_text = f"{ma_raw.get('ma10', 0):.2f}" if isinstance(ma_raw.get("ma10"), (int, float)) else "--"
    ma20_text = f"{ma_raw.get('ma20', 0):.2f}" if isinstance(ma_raw.get("ma20"), (int, float)) else "--"
    ma30_text = f"{ma_raw.get('ma30', 0):.2f}" if isinstance(ma_raw.get("ma30"), (int, float)) else "--"
    
    lines: list[str] = [
        f"分析报告 — {name}（{display_code}）",
        "",
        f"现价：{current_price:.2f}元（{change_pct:+.2f}%）",
        f"MA5：{ma5_text}｜MA10：{ma10_text}｜MA20：{ma20_text}｜MA30：{ma30_text}",
    ]
    if atr14 > 0:
        lines.append(f"ATR {atr14:.2f}（{atr_ratio*100:.1f}%）{atr_level}")
        
    lines.extend([
        "",
        f"📊 {major_stage}期 + {momentum} → {stage_action_text}",
        "",
        "📍 买卖点"
    ])
    
    if stop > 0:
        lines.append(f"  {stop:.2f} 止损")
    if low_price > 0:
        lines.append(f"  {low_price:.2f} ← 买 {position_cap}%（缩量企稳）")
    if current_price > 0:
        lines.append(f"  {current_price:.2f} 当前")
    
    exit_plan = r.get("exit_plan") or {}
    exit_plan_items = exit_plan.get("exit_plan") or []
    for item in exit_plan_items:
        p = item.get("price")
        ratio = item.get("ratio", 0)
        reason = item.get("reason", "")
        if p is not None and p > 0:
            lines.append(f"  {p:.2f} → 卖 {ratio:.0%}（{reason}）")
    
    if resistance_val > 0:
        lines.append(f"  {resistance_val:.2f} 压力")
        
    stage_exit = exit_plan.get("stage_exit")
    if stage_exit:
        lines.append(f"  阶段转{stage_exit} → 清仓")
    
    lines.extend(["", "💡 为什么这么操作"])
    stage_desc_map = {
        "蓄势": "区间震荡，低吸高抛",
        "主升": "趋势向上，持股待涨",
        "派发": "高位震荡，逢高减仓",
        "衰退": "趋势向下，不碰",
    }
    stage_desc = stage_desc_map.get(major_stage, "")
    lines.append(f"  阶段：{major_stage}期（{stage_desc}）")
    
    trend_desc = f"价格在 {confirm:.2f} 下方" if current_price < confirm else f"价格站上 {confirm:.2f}"
    trend_action = "不追" if current_price < confirm else "可加仓"
    lines.append(f"  趋势：短期偏弱（{trend_desc}），{trend_action}")

    has_position = r.get("has_position", False)
    cost_price = float(r.get("cost_price") or 0)
    if has_position and cost_price > 0:
        pnl_pct = (current_price - cost_price) / cost_price * 100
        pnl_text = f"盈 {pnl_pct:+.1f}%" if pnl_pct >= 0 else f"亏 {abs(pnl_pct):.1f}%"
        lines.extend([
            "",
            f"📌 如果你有持仓（成本 {cost_price:.2f}）"
        ])
        if pnl_pct >= 0:
            if major_stage == "主升":
                lines.append(f"  现在：持有，让利润跑（{pnl_text}）")
            elif major_stage == "派发":
                lines.append(f"  现在：减仓，锁定利润（{pnl_text}）")
            else:
                lines.append(f"  现在：部分止盈，留底仓等突破（{pnl_text}）")
        else:
            if major_stage == "衰退":
                lines.append(f"  现在：止损，认亏走人（{pnl_text}）")
            elif major_stage == "主升":
                lines.append(f"  现在：持有，主升期大概率会回来（{pnl_text}）")
            else:
                lines.append(f"  现在：持有，不加仓（{pnl_text}）")
                
        lines.append(f"  反弹到 {cost_price:.2f}：减 50%（保本）")
        if stop > 0:
            lines.append(f"  跌破 {stop:.2f}：止损（认亏）")
            
    chip_peaks = r.get("chip_peaks") or []
    if chip_peaks:
        lines.extend(["", "🔍 主力筹码", "  筹码峰："])
        sorted_peaks = sorted(chip_peaks, key=lambda x: x.get("price", 0))
        for peak in sorted_peaks[:3]:
            p = peak.get("price", 0)
            share = peak.get("share_of_total", 0)
            level = peak.get("support_level", "")
            if p > 0:
                lines.append(f"    {p:.2f}（{level}）｜ 占比 {share:.2f}%")
        
        current_pct = r.get("chip_current_pct")
        mid_price = r.get("chip_mid_price")
        if current_pct is not None:
            lines.append(f"  当前价以上：{current_pct:.1f}%")
        if mid_price is not None:
            lines.append(f"  中位数价格：{mid_price:.2f}")
            
        chip_migration = r.get("chip_migration") or {}
        has_history = chip_migration.get("has_history", False)
        
        if has_history:
            lines.extend(["", f"  筹码变化（对比昨天）："])
            
            support_diff = chip_migration.get("support_diff", 0)
            resistance_diff = chip_migration.get("resistance_diff", 0)
            
            support_peaks = [p for p in chip_peaks if "支撑" in str(p.get("support_level", ""))]
            if support_peaks:
                strongest_supp = max(support_peaks, key=lambda p: p.get("share_of_total", 0))
                supp_price = strongest_supp.get("price", 0)
                curr_supp_share = strongest_supp.get("share_of_total", 0)
                prev_supp_share = curr_supp_share - support_diff
                if prev_supp_share > 0:
                    chg_pct = round((curr_supp_share - prev_supp_share) / prev_supp_share * 100)
                    dir_txt = "底部筹码减少" if curr_supp_share < prev_supp_share else "底部筹码增加"
                    sign = "+" if chg_pct > 0 else ""
                    lines.append(f"    {supp_price:.2f}（支撑）：{prev_supp_share:.2f}% → {curr_supp_share:.2f}%（{sign}{chg_pct}%）← {dir_txt}")
                    
            res_peaks = [p for p in chip_peaks if "阻力" in str(p.get("support_level", ""))]
            if res_peaks:
                strongest_res = max(res_peaks, key=lambda p: p.get("share_of_total", 0))
                res_price = strongest_res.get("price", 0)
                curr_res_share = strongest_res.get("share_of_total", 0)
                prev_res_share = curr_res_share - resistance_diff
                if prev_res_share > 0:
                    chg_pct = round((curr_res_share - prev_res_share) / prev_res_share * 100)
                    dir_txt = "顶部筹码减少" if curr_res_share < prev_res_share else "顶部筹码增加"
                    sign = "+" if chg_pct > 0 else ""
                    lines.append(f"    {res_price:.2f}（阻力）：{prev_res_share:.2f}% → {curr_res_share:.2f}%（{sign}{chg_pct}%）← {dir_txt}")
            
            warning_text = chip_migration.get("warning_text", "底部筹码基本稳定，无明显搬家")
            
            if "筹码在搬家" in warning_text:
                lines.append(f"    结论：筹码在搬家，主力在出货")
            elif "主力在吸筹" in warning_text:
                lines.append(f"    结论：主力在吸筹")
            else:
                lines.append(f"    结论：{warning_text}")
            
    fusion = r.get("fusion") or {}
    signals = fusion.get("signals_detail") or {}
    chan_score = signals.get("chan", {}).get("confidence", 0) * 100 if isinstance(signals.get("chan"), dict) else 75
    wyk_score = signals.get("wyckoff", {}).get("confidence", 0) * 100 if isinstance(signals.get("wyckoff"), dict) else 45
    mom_score = signals.get("momentum", {}).get("confidence", 0) * 100 if isinstance(signals.get("momentum"), dict) else 50
    chip_score = 50
    
    lines.extend(["", "📊 五层打分", f"  结构{chan_score:.0f}/量价{wyk_score:.0f}｜筹码{chip_score:.0f}｜动能{mom_score:.0f}"])
    chan_reason = signals.get("chan", {}).get("reason", "回调段。一类买、二类买") if isinstance(signals.get("chan"), dict) else "无信号"
    lines.append(f"  缠论：{chan_reason}")
    wyckoff_data = r.get("wyckoff") or {}
    wyckoff_desc = wyckoff_data.get("description", "无明显威科夫信号") if isinstance(wyckoff_data, dict) else "无明显威科夫信号"
    lines.append(f"  威科夫：{wyckoff_desc}")
    
    lines.extend(["", "🎯 信号判断"])
    bullish_signals = []
    cautious_signals = []
    
    chan_data = signals.get("chan") or {}
    if isinstance(chan_data, dict) and chan_data.get("direction", 0) > 0:
        bullish_signals.append("结构（两次接近位置止跌）")
        
    volume_ratio = float(r.get("volume_ratio") or 0)
    if volume_ratio < 0.8:
        cautious_signals.append("量价（午后缩量）")
        
    chip_migration = r.get("chip_migration") or {}
    if chip_migration.get("warning_level") in ("warning", "critical") or "出货" in str(chip_migration.get("warning_text", "")):
        cautious_signals.append("筹码（上方成交密集区）")
    elif float(r.get("chip_current_pct") or 0) > 60:
        cautious_signals.append("筹码（上方成交密集区）")
        
    if bullish_signals:
        lines.append(f"  偏多：✓ {'  ✓ '.join(bullish_signals)}")
    if cautious_signals:
        lines.append(f"  警惕：! {'  ! '.join(cautious_signals)}")
        
    lines.append("")
    if current_price >= low_price:
        lines.append(f"✅ 亮点：{current_price:.2f} 仍站在防守位 {low_price:.2f} 上方")
    else:
        lines.append(f"✅ 亮点：价格超跌，关注 {low_price:.2f} 附近企稳机会")
        
    if "出货" in str(chip_migration.get("warning_text", "")):
        lines.append(f"⚠️ 风险：筹码在搬家，主力在出货，警惕继续下跌")
    else:
        lines.append(f"⚠️ 风险：最大风险是 {confirm:.2f} 未确认前提前追入")
        
    lines.append("")
    win_rate_data = _load_historical_win_rate(display_code)
    lines.append("📊 股性与历史回测")
    if win_rate_data is not None:
        lines.append(f"  历史记录：最近共生成 {win_rate_data['total']} 次已平仓信号")
        lines.append(f"  说买 → 涨了：{win_rate_data['wins']}/{win_rate_data['total']} 次（胜率 {win_rate_data['win_rate']:.1f}%）")
        lines.append(f"  平均盈亏比：{win_rate_data['profit_factor']:.2f} ｜ 平均每笔收益：{win_rate_data['avg_pnl']:+.2f}%")
        lines.append(f"  单笔最强：{win_rate_data['max_gain']:+.2f}% ｜ 单笔最弱：{win_rate_data['max_loss']:+.2f}%")
        lines.append(f"  结论：{win_rate_data['conclusion']}")
    else:
        lines.append("  历史交易数据不足，暂不统计")
    lines.append("")

    pool_count = _pool_count()
    if pool_count > 0:
        lines.extend(["", f"当前池 {pool_count}/10，回复 1 入池"])
    
    return "\n".join(lines)
