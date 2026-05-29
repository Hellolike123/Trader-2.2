#!/usr/bin/env python3
"""A-Share Trader 全局中央指挥官路由器 (run_trader.py)

统一管理系统生命周期中的盘中（live）和盘后（review）指令路由。
"""

from __future__ import annotations

import argparse
import sys
import os
from pathlib import Path

# ── 物理路径全注入，彻底消除跨模块与 SandBox 的导入问题 ─────────────────────
_ROOT = Path(__file__).resolve().parent.parent if "scripts" in str(Path(__file__).resolve()) else Path(__file__).resolve()
_PATH_MATRIX = [
    _ROOT / "01-功能包-packages" / "01-单票分析-trader" / "scripts",
    _ROOT / "01-功能包-packages" / "02-盘中T0-t0-trader" / "scripts",
    _ROOT / "01-功能包-packages" / "03-选股池-trader-pool" / "scripts",
    _ROOT / "01-功能包-packages" / "04-仓位轮动-trader-portfolio" / "scripts",
    _ROOT / "01-功能包-packages" / "05-盘后复盘-review-trader" / "scripts",
    _ROOT / "02-共享模块-shared" / "01-行情数据-market-data",
    _ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate",
    _ROOT / "02-共享模块-shared",
    _ROOT / "02-共享模块-shared" / "03-输出校验-contracts",
    _ROOT / "02-共享模块-shared" / "scripts",
]
for _p in _PATH_MATRIX:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trader Central Commander — 统一大路由控制台",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True, help="子空间指令")
    
    # ── 1. 盘中现场子空间 (live) ──
    live_parser = subparsers.add_parser("live", help="盘中交易与实时监控空间")
    live_parser.add_argument("--target", help="指定个股进行诊断，例如: 南网科技 或 688248")
    live_parser.add_argument("--monitor", action="store_true", help="启动盘中T0实时哨兵监控")
    live_parser.add_argument("--show", action="store_true", help="显示选股池与持仓个股的盘中实时天梯快照")
    live_parser.add_argument("--add", action="store_true", help="诊断得分及格后自动将其录入选股池开始监控")
    live_parser.add_argument("--once", action="store_true", help="被动扫描只执行单次检查 (供定时任务/Hermes 触发)")
    live_parser.add_argument("--cost", type=float, help="个性化持仓成本")
    live_parser.add_argument("--position", type=int, help="个性化做T底仓股数")
    
    # ── 2. 盘后战术子空间 (review) ──
    review_parser = subparsers.add_parser("review", help="盘后统计与战术复盘空间")
    review_parser.add_argument("--target", help="指定个股进行盘后五层得分深度复盘")
    review_parser.add_argument("--all", action="store_true", help="【一键全盘复盘】对池内与持仓个股全自动流式处理，输出综合大面板")
    review_parser.add_argument("--date", help="指定复盘的历史交易日 YYYY-MM-DD")
    review_parser.add_argument("--output", choices=["markdown", "json"], default="markdown", help="输出格式")

    return parser.parse_args()


def format_live_wechat_card(r: dict) -> str:
    """微信端友好、细节说服型去 Markdown 去 HTML 粗体个股验票卡片"""
    ma = r.get("ma") or {}
    display_code = str(r["symbol"]).replace(".SH", "").replace(".SZ", "")
    name = str(r["name"])
    
    # 现价与涨幅
    current = float(r.get("current") or r.get("current_price") or 0.0)
    change_pct = float(r.get("change_pct") or r.get("current_change_pct") or 0.0)
    
    # 大盘环境与 HMM 置信度
    try:
        from trader_shared import get_env_for_skill
        env = get_env_for_skill("trader")
        market_level = env.get("level", "正常")
        hmm_regime = env.get("hmm_regime_en", "range")
        hmm_cn = {"bull": "🟢偏牛", "bear": "🔴偏熊", "range": "🟡震荡"}.get(hmm_regime, "🟡震荡")
    except Exception:
        market_level = "正常"
        hmm_cn = "🟡震荡"
        
    status_text = str(r.get("state_label") or "")
    base_status_text = str(r.get("base_status") or "")
    theory_status_text = str(r.get("theory_status") or status_text)
    
    # 黄金挂单 (Golden Bid)
    fib_retrace = r.get("fib_retrace") or r.get("fibonacci_retrace") or {}
    golden_bid = fib_retrace.get("golden_bid") if isinstance(fib_retrace, dict) else None
    
    # 四维诊断大白话依据
    # 1. 缠论结构
    chan_result = r.get("chanlun") or {}
    chan_desc = f"中枢走势: {chan_result.get('trend_label', '震荡')}，买点参考: {chan_result.get('buy_point_text', '暂无')}"
    if not chan_result.get("buy_point_text"):
        chan_desc = "日线级别中枢震荡，底分型确认后可提供安全垫"
        
    # 2. 威科夫量价
    wyck_desc = r.get("volume_text", "量能平稳空转，未出现假突破。")
    if "无量" in wyck_desc or "空转" in wyck_desc:
        wyck_desc = "处于筑底整理无量空转期，需等突破放量支撑"
        
    # 3. 筹码分布
    chip_zone = r.get("chip_zone") or {}
    chip_desc = f"主筹码峰在 {r.get('support', current*0.975):.2f} 元附近吸筹充分，下方防御力强"
    
    # 4. 动能大单
    fusion = r.get("fusion") or {}
    weighted_score = fusion.get("weighted_score", 0.0)
    mom_dir = "偏多" if weighted_score > 0 else "偏空" if weighted_score < 0 else "中性"
    mom_desc = f"MACD大方向{mom_dir}，今日主力资金决策置信度 {int(fusion.get('confidence', 50))}%"
    
    low_zone = str(r.get("low_zone") or f"{r.get('support', current*0.985):.2f}-{current:.2f}元")
    stop = float(r.get("stop") or r.get("defense") or current*0.945)
    confirm = float(r.get("confirm") or r.get("trigger") or current*1.035)
    position_cap = int(r.get("position_cap") or 10)
    
    lines = [
        f"分析报告 — {name}（{display_code}）",
        "",
        f"现价：{current:.2f}元（{change_pct:+.2f}%）",
        f"大盘：🌍 环境{market_level} ｜ HMM状态：{hmm_cn}",
        "",
        "🧭 简要分析",
        f"基础位置：{base_status_text} ｜ 体系结论：{theory_status_text}",
        "",
        "📈 四维诊断白话依据",
        f"  · 缠论结构：{chan_desc}",
        f"  · 威科夫量价：{wyck_desc}",
        f"  · 筹码分布：{chip_desc}",
        f"  · 动能大单：{mom_desc}",
        ""
    ]
    
    if golden_bid:
        lines.extend([
            "📍 黄金挂单",
            f"  · 黄金挂单价：{golden_bid:.2f}元 (50.0%黄金分割点共振，安全边际极佳)",
            ""
        ])
        
    lines.extend([
        "📍 决策",
        f"状态：{status_text or '防守观察'}",
        f"  空仓：在 {low_zone} 试探买 {position_cap}%, 止损 {stop:.2f}",
        f"  有底仓：反弹 {confirm:.2f} 冲不动就减 10-20%",
        f"  加仓：放量站稳 {confirm:.2f} 且回踩不破才评估",
        "",
        "❗ 关键价位",
        f"{stop:.2f}  ← 止损位",
        f"{r.get('support', current*0.975):.2f}  ← 支撑位",
        f"{current:.2f}  ← 当前位置",
        f"{confirm:.2f}  ← 确认位",
    ])
    
    return "\n".join(lines)


def handle_live_show(args: argparse.Namespace) -> int:
    """显示选股池与持仓个股的盘中实时天梯快照，去加粗去 Markdown 化排版"""
    from final_pool import load_pool, active_items, sort_items, action_summary_for_scene
    import time
    
    pool = load_pool()
    items = sort_items(active_items(pool))
    if not items:
        print("💡 选股池为空，无需盯盘快照。")
        return 0
        
    now_str = time.strftime("%H:%M")
    lines = [
        f"📡 选股池盯盘快照 — {now_str} ｜ 实时现场",
        ""
    ]
    
    for i, item in enumerate(items[:5], 1):
        name = item.get("name", "?")
        current = float(item.get("current") or 0.0)
        trigger = float(item.get("trigger") or 0.0)
        defense = float(item.get("defense") or 0.0)
        support = float(item.get("support") or 0.0)
        scene = str(item.get("scene") or "")
        status = str(item.get("status") or "?")
        
        # 尝试拉取实时报价（若有行情模块）
        change_pct = 0.0
        try:
            from light_data import fetch_quote, HttpClient, resolve_security
            sec = resolve_security(name)
            q = fetch_quote(sec, HttpClient())
            if q and q.get("current_price"):
                current = float(q.get("current_price"))
                change_pct = float(q.get("current_change_pct") or 0.0)
        except Exception:
            pass
            
        atr14 = float(item.get("atr14") or 0.0)
        thresh_pct = min(atr14 * 2, 0.03) if atr14 > 0 else 0.02
        atr_note = f" (日幅±{atr14:.2f})" if atr14 > 0 else ""
        
        stock_alerts = []
        # 1. 破防守位
        if defense > 0 and current < defense:
            stock_alerts.append("🛑 跌破防守！跌破防守" + atr_note)
        # 2. 靠近防守
        elif defense > 0 and current > defense:
            dist_def = abs(current - defense) / current * 100
            if dist_def < thresh_pct * 100:
                stock_alerts.append(f"⚠️ 靠近防守，距防守仅 {dist_def:.1f}%" + atr_note)
        # 3. 靠近触发
        elif trigger > 0:
            dist_trig = abs(trigger - current) / current * 100
            if dist_trig < thresh_pct * 100:
                if current >= trigger:
                    stock_alerts.append("🟢 已到触发位附近" + atr_note)
                else:
                    stock_alerts.append(f"⚡ 距触发仅 {dist_trig:.1f}%" + atr_note)
                    
        # 4. 靠近支撑
        if support > 0 and current <= support * 1.01:
            dist_sup = abs(current - support) / current * 100
            if dist_sup < thresh_pct * 100:
                stock_alerts.append(f"📊 距支撑仅 {dist_sup:.1f}%" + atr_note)
                
        rank_emoji = ["🥇", "🥈", "🥉", " 4. ", " 5. "][i - 1]
        if stock_alerts:
            alert_line = " ｜ ".join(stock_alerts)
            lines.append(f"  {rank_emoji} {name}  {current:.2f}元（{change_pct:+.2f}%）  {alert_line}")
        else:
            action = action_summary_for_scene(scene)
            lines.append(f"  {rank_emoji} {name}  {current:.2f}元（{change_pct:+.2f}%）  👉 {action}{atr_note}")
            
    print("\n".join(lines))
    return 0


def handle_live(args: argparse.Namespace) -> int:
    """处理盘中所有的主动与被动看盘逻辑。"""
    # A. 盘中主动快照查看 (没事看一眼)
    if args.show:
        try:
            return handle_live_show(args)
        except Exception as exc:
            print(f"❌ 盘中快照调取失败: {exc}", file=sys.stderr)
            return 1

    # B. 盘中盯盘哨兵 (被动自动提醒)
    if args.monitor:
        try:
            from monitor import run_monitor
            target_stock = args.target
            if not target_stock:
                # 默认读取 last_target.txt
                last_target_path = Path.home() / ".trader" / "last_target.txt"
                if last_target_path.exists():
                    target_stock = last_target_path.read_text(encoding="utf-8").strip()
            
            if not target_stock:
                print("❌ 盯盘失败: 未指定 --target 且本地未缓存历史个股", file=sys.stderr)
                return 1
                
            print(f"📡 [UnifiedRouter] 后台实时监控哨兵已激活，正在扫描: {target_stock}")
            return run_monitor(
                target_stock,
                interval=3,
                cost=args.cost,
                position=args.position,
                once=args.once,
                verbose=True
            )
        except Exception as exc:
            print(f"❌ 盘中T0监控哨兵执行失败: {exc}", file=sys.stderr)
            return 1

    # C. 单票深度验票
    if args.target:
        try:
            from run_analysis import build_report
            report = build_report(args.target)
            
            # 使用微信去加粗、双空行呼吸感格式排版
            wechat_content = format_live_wechat_card(report)
            
            # 如果带了 --add 并且符合条件，自动加入股票池
            if args.add:
                try:
                    from final_pool import cmd_add
                    class Args:
                        target = args.target
                        offline = False
                    cmd_add(Args())
                    wechat_content += f"\n\n✅ 诊断总分符合条件，股票 {args.target} 已成功自动录入选股池。"
                except Exception as add_err:
                    wechat_content += f"\n\n⚠️ 自动录入选股池失败: {add_err}"
            
            print(wechat_content)
            
            # 自动写诊断缓存供 monitor 读取
            last_target_path = Path.home() / ".trader" / "last_target.txt"
            last_target_path.parent.mkdir(parents=True, exist_ok=True)
            last_target_path.write_text(args.target, encoding="utf-8")
            return 0
        except Exception as exc:
            print(f"❌ 盘中深度验票执行失败: {exc}", file=sys.stderr)
            return 1

    print("❌ 参数错误: live 指令必须指定 --target, --monitor 或 --show")
    return 1


def handle_review_all(args: argparse.Namespace) -> int:
    """【一键全盘复盘】对池内个股流式批量处理，输出战术终极综合面板并支持平仓回填与参数自校准。"""
    from final_pool import load_pool, active_items, record_from_report, sort_items, counts, _pool_signal_verifications, save_pool
    from final_portfolio import load_positions
    from portfolio_run import build_portfolio
    from run_analysis import build_report
    from concurrent.futures import ThreadPoolExecutor
    import time
    
    pool = load_pool()
    items = active_items(pool)
    if not items:
        print("💡 当前选股池为空，今日无复盘任务。")
        return 0
        
    print("📡 [UnifiedRouter] 正在一键全盘大盘点，进行盘后批量诊断与优先级重排...")
    
    # 1. 批量并发拉取池内股票的最新诊断
    results = []
    def process_stock(item):
        target = item.get("target") or item.get("name")
        try:
            report = build_report(target)
            record = record_from_report(target, report, offline=False)
            return target, report, record
        except Exception:
            return target, None, None

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(process_stock, items))
        
    valid_records = []
    reports_map = {}
    for target, report, record in results:
        if record is not None:
            valid_records.append(record)
            reports_map[target] = report
        else:
            print(f"⚠️ 股票 {target} 当日收盘数据获取失败，跳过本次重排。")
            
    if not valid_records:
        print("❌ 一键复盘失败：无法获取任何股票的当日实盘收盘行情。")
        return 1
        
    # 2. 重新进行收盘算分排序 (🥇/🥈/🥉) 并存回 pool.json
    sorted_records = sort_items(valid_records)
    pool["items"] = sorted_records
    save_pool(pool)
    
    # 3. 仓位轮动配置分析
    active_targets = [r["name"] for r in sorted_records]
    positions = load_positions()
    holdings = {p["name"]: p for p in positions if p.get("name") in active_targets}
    try:
        portfolio_res = build_portfolio(
            active_targets,
            holdings=holdings or None,
            max_total=80,
            cash_floor=20,
            main_cap=50
        )
        portfolio_markdown = portfolio_res.get("portfolio_markdown", "")
    except Exception as e:
        portfolio_markdown = f"⚠️ 仓位轮动分析发生异常: {e}"
        
    # 4. 选股池信号准确率回测
    try:
        verifications, summary = _pool_signal_verifications(sorted_records)
    except Exception:
        verifications, summary = [], {}
        
    # 5. 融合成极具视觉说服力的微信友好排版（草案 B）
    try:
        from trader_shared import get_env_for_skill
        env = get_env_for_skill("trader")
        market_level = env.get("level", "正常")
    except Exception:
        market_level = "正常"
        
    pool_counts = counts(sorted_records)
    today_str = time.strftime("%Y-%m-%d")
    
    lines = [
        f"📌 盘后全盘复盘 — {today_str}",
        f"容量 {len(sorted_records)}/10 ｜ 执行 {pool_counts.get('执行', 0)} ｜ 观察 {pool_counts.get('观察', 0)} ｜ 淘汰 {pool_counts.get('淘汰', 0)}",
        "",
        f"🌍 大盘环境：{market_level} ｜ 建议总仓位 ≤5成",
        ""
    ]
    
    # 渲染优先级 Top3
    for i, r in enumerate(sorted_records[:3]):
        medal = ["🥇", "🥈", "🥉"][i]
        name = r["name"]
        status = r["status"]
        score = r["total_score"]
        current = r["current"]
        support = r["support"]
        trigger = r["trigger"]
        
        report = reports_map.get(name) or {}
        
        # 黄金挂单
        fib_retrace = report.get("fib_retrace") or report.get("fibonacci_retrace") or {}
        golden_bid = fib_retrace.get("golden_bid")
        golden_txt = f"  黄金挂单：{golden_bid:.2f}元 (50.0%黄金回调共振)\n" if golden_bid else ""
        
        # 缠/威/大单提取
        chan_result = report.get("chanlun") or {}
        chan_text = chan_result.get("buy_point_text") or "中枢盘整"
        wyck_text = report.get("volume_text") or "量能平稳"
        if "无量" in wyck_text or "空转" in wyck_text:
            wyck_text = "筑底缩量整理"
            
        big_order = report.get("big_order") or {}
        big_order_summary = big_order.get("summary") or "大单无主力异常流入"
        
        lines.extend([
            f"{medal} {name} ｜ {status} ｜ 总分：{score}",
            f"  现价：{current:.2f}元 ｜ 下方支撑：{support:.2f} ｜ 上方压力：{trigger:.2f}",
            f"{golden_txt}  诊断详情：缠论{chan_text}，威科夫{wyck_text}，{big_order_summary}。",
            f"  操作建议：明日只盯 {trigger:.2f} 压力线是否放量突破；未放量不买入。",
            ""
        ])
        
    # 渲染其他活跃股
    if len(sorted_records) > 3:
        lines.append("其他活跃个股建议")
        for r in sorted_records[3:]:
            lines.append(f"  · {r['name']} ｜ 现价 {r['current']:.2f}元 ｜ 操作建议：{r['status']}观察，暂不盲动")
        lines.append("")
        
    # 信号回测渲染
    if verifications:
        lines.extend([
            "📊 选股池信号回测",
            ""
        ])
        for v in verifications[:5]:
            lines.append(f"  · {v['name']} ({v.get('sig_text','无')})：{v.get('verify_status','⏳ 跟踪中')}")
            
        total_verified = summary.get("已验证", 0)
        total_wrong = summary.get("信号错了", 0)
        total_unverified = summary.get("未验证", 0)
        total_with_signal = total_verified + total_wrong
        
        if total_with_signal > 0:
            accuracy = total_verified / total_with_signal * 100
            lines.append(f"  合计：本月已验证 {total_with_signal} 次，对了 {total_verified} 次，准确率 {accuracy:.0f}%。未验证 {total_unverified} 次。")
        else:
            lines.append(f"  合计：本月无已验证信号记录（未验证 {total_unverified} 次）。")
        lines.append("")
        
    # 仓位配置渲染 (去除加粗与 Markdown 多级标题)
    clean_portfolio_markdown = portfolio_markdown.replace("**", "").replace("### ", "").replace("## ", "").replace("- ", "  · ")
    lines.extend([
        "💼 仓位轮动与配置建议",
        clean_portfolio_markdown,
        "",
        "仓位纪律：执行首次1成，确认加至3成，单票风险1R，明天重点盯防前两名优先个股。"
    ])
    
    print("\n".join(lines))
    
    # 6. 平仓交互与异步自校准大闭环
    try:
        from final_review import run_postmarket_backfill_and_calibration
        run_postmarket_backfill_and_calibration()
    except Exception as e:
        print(f"\n📡 [AutoBackfill-Warn] 盘后平仓提问回填与自校准拉起异常: {e}", file=sys.stderr)
        
    return 0


def handle_review(args: argparse.Namespace) -> int:
    """处理盘后复盘打分与一键决策大闭环。"""
    # A. 一键全盘复盘
    if args.all:
        try:
            return handle_review_all(args)
        except Exception as exc:
            print(f"❌ 一键全盘复盘失败: {exc}", file=sys.stderr)
            return 1

    # B. 盘后单票五层复盘
    if args.target:
        try:
            from review_single import run_single
            text = run_single(args.target, trade_date=args.date, output=args.output)
            print(text)
            
            # 执行盘后活跃信号提问回填与自校准
            if args.output == "markdown":
                try:
                    from final_review import run_postmarket_backfill_and_calibration
                    run_postmarket_backfill_and_calibration()
                except Exception as e:
                    print(f"⚠️ 自校准处理异常: {e}", file=sys.stderr)
            return 0
        except Exception as exc:
            print(f"❌ 单票复盘失败: {exc}", file=sys.stderr)
            return 1

    print("❌ 参数错误: review 指令必须指定 --target 或 --all")
    return 1


def main() -> int:
    args = parse_args()
    if args.command == "live":
        return handle_live(args)
    elif args.command == "review":
        return handle_review(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
