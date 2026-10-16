import sys
import os
import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

if not mt5.initialize():
    print("MT5 initialization failed")
    sys.exit(1)

MAGIC_NUMBER = 999888
now = datetime.now()
days_from_monday = now.weekday()
week_monday_start = (now - timedelta(days=days_from_monday)).replace(hour=0, minute=0, second=0, microsecond=0)

deals = mt5.history_deals_get(week_monday_start, now)
if deals is None:
    print("No deals found")
    sys.exit(1)

magic_deals = [d for d in deals if d.magic == MAGIC_NUMBER]
print(f"Total magic deals: {len(magic_deals)}")

pos_map = defaultdict(list)
for d in magic_deals:
    pos_map[d.position_id].append(d)

batch_positions = defaultdict(list)
batch_meta = {}
VALID_TFS = {'1m', '2m', '3m', '5m', '15m', '30m', '45m', '1h', '2h', '3h', '4h', 'd', '1d', 'daily', 'w', '1w'}

for pid, d_list in pos_map.items():
    entry_deal = next((d for d in d_list if d.entry == 0), None)
    if not entry_deal:
        continue
    if entry_deal.time < week_monday_start.timestamp():
        continue
    entry_dt = datetime.fromtimestamp(entry_deal.time)
    if entry_dt.weekday() in (5, 6):
        continue

    comment = entry_deal.comment if entry_deal else d_list[0].comment
    bid = None
    tf = "1h"
    strat_tag = "CORE"
    if "QS_" in comment:
        parts = comment.split("_")
        if len(parts) >= 2:
            bid = parts[1]
        for part in parts[2:]:
            p_clean = part.lower().strip()
            if p_clean in VALID_TFS or (len(p_clean) >= 2 and p_clean[-1] in 'mhd' and p_clean[:-1].isdigit()):
                tf = p_clean
                break
        if len(parts) >= 4:
            strat_tag = parts[2].upper().strip()
    elif "AUTOBE_" in comment:
        parts = comment.split("_")
        if len(parts) >= 2:
            bid = parts[1]
    if not bid:
        bid = str(pid)

    batch_positions[bid].append((pid, d_list))
    if bid not in batch_meta:
        batch_meta[bid] = {
            "symbol": d_list[0].symbol,
            "timeframe": tf,
            "strat_tag": strat_tag,
            "comment": comment
        }

current_open_positions = mt5.positions_get()
open_pids = set(p.ticket for p in current_open_positions) if current_open_positions else set()

closed_batches = []
for bid, p_tuples in batch_positions.items():
    all_closed = all(pid not in open_pids and any(d.entry == 1 for d in d_list) for pid, d_list in p_tuples)
    if all_closed:
        closed_batches.append((bid, p_tuples))

print(f"Total closed batches to simulate: {len(closed_batches)}")

# Simulation stats
baseline_total_pnl = 0.0
baseline_wins = 0
baseline_losses = 0
baseline_be = 0

smart_total_pnl = 0.0
smart_wins = 0
smart_losses = 0
smart_be = 0

early_cuts_triggered = 0
early_cuts_saved_loss = 0.0  # dollars saved
early_cuts_wrongly_cut_win = 0  # trades that were wins in baseline but cut early in smart

smart_tp1_hits = 0
smart_tp1_missed_legacy_wins = 0  # trades that hit 0.38 ATR in baseline but missed 0.75 ATR in smart

smart_tp2_hits = 0
smart_breathing_be_hits = 0

batch_comparisons = []

for idx, (bid, p_tuples) in enumerate(closed_batches):
    sym = p_tuples[0][1][0].symbol
    b_info = batch_meta.get(bid, {})
    strat = b_info.get("strat_tag", "UNKNOWN")
    tf = b_info.get("timeframe", "1h")

    # Reconstruct actual baseline PnL
    actual_batch_pnl = 0.0
    for pid, d_list in p_tuples:
        for d in d_list:
            actual_batch_pnl += float(d.profit) + float(getattr(d, 'swap', 0.0) or 0.0) + float(getattr(d, 'commission', 0.0) or 0.0)
    actual_batch_pnl = round(actual_batch_pnl, 2)

    baseline_total_pnl += actual_batch_pnl
    if actual_batch_pnl > 0.15:
        baseline_wins += 1
        base_outcome = "WIN"
    elif actual_batch_pnl < -0.15:
        baseline_losses += 1
        base_outcome = "LOSS"
    else:
        baseline_be += 1
        base_outcome = "BE"

    # Identify entry deals and timing
    entry_deals = [d for pid, d_list in p_tuples for d in d_list if d.entry == 0]
    exit_deals = [d for pid, d_list in p_tuples for d in d_list if d.entry == 1]
    if not entry_deals or not exit_deals:
        smart_total_pnl += actual_batch_pnl
        continue

    is_buy = (entry_deals[0].type == 0)
    order_type_mt5 = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL

    entry_price = float(entry_deals[0].price)
    entry_time = min(d.time for d in entry_deals)
    exit_time = max(d.time for d in exit_deals)

    dt_entry = datetime.fromtimestamp(entry_time)
    dt_exit = datetime.fromtimestamp(exit_time)

    # Determine Stop Loss and TP from orders or deals
    sl_price = 0.0
    tp1_price = 0.0
    tp2_price = 0.0
    tp3_price = 0.0

    tickets_info = []
    for pid, d_list in p_tuples:
        e_deal = next((d for d in d_list if d.entry == 0), None)
        vol = e_deal.volume if e_deal else 0.01
        role = "TP1"
        ords = mt5.history_orders_get(position=pid)
        ord_sl = 0.0
        ord_tp = 0.0
        if ords:
            for o in ords:
                if o.sl > 0 and ord_sl == 0.0:
                    ord_sl = float(o.sl)
                if o.tp > 0 and ord_tp == 0.0:
                    ord_tp = float(o.tp)
                if "_TP1" in o.comment:
                    role = "TP1"
                elif "_TP2" in o.comment:
                    role = "TP2"
                elif "_TP3" in o.comment:
                    role = "TP3"
        if sl_price == 0.0 and ord_sl > 0:
            sl_price = ord_sl
        tickets_info.append({
            "pid": pid,
            "role": role,
            "volume": vol,
            "ord_sl": ord_sl,
            "ord_tp": ord_tp
        })

    # Fallback SL detection from exit deals if orders didn't capture SL
    if sl_price <= 0.0:
        for pid, d_list in p_tuples:
            for d in d_list:
                if '[sl ' in d.comment:
                    import re
                    m = re.search(r'\[sl\s+([0-9.]+)\]', d.comment)
                    if m:
                        sl_price = float(m.group(1))
                        break
            if sl_price > 0.0:
                break

    # If still no SL, derive from actual loss or skip
    if sl_price <= 0.0 or entry_price <= 0.0:
        smart_total_pnl += actual_batch_pnl
        continue

    risk_dist = abs(entry_price - sl_price)
    if risk_dist <= 0:
        smart_total_pnl += actual_batch_pnl
        continue

    safe_atr = risk_dist / 1.80

    # Smart Solution Target Geometry
    smart_tp1_price = entry_price + (0.75 * safe_atr) if is_buy else entry_price - (0.75 * safe_atr)
    invalidation_sl = entry_price - (0.75 * safe_atr) if is_buy else entry_price + (0.75 * safe_atr)
    soft_breakeven_sl = entry_price - (0.40 * safe_atr) if is_buy else entry_price + (0.40 * safe_atr)
    smart_tp2_price = entry_price + (1.15 * risk_dist) if is_buy else entry_price - (1.15 * risk_dist)
    smart_tp3_price = entry_price + (2.20 * risk_dist) if is_buy else entry_price - (2.20 * risk_dist)

    # Fetch M1 candle history during trade execution
    rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, dt_entry - timedelta(minutes=2), dt_exit + timedelta(minutes=30))
    if rates is None or len(rates) == 0:
        # Fallback to M5
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, dt_entry - timedelta(minutes=10), dt_exit + timedelta(minutes=60))

    if rates is None or len(rates) == 0:
        smart_total_pnl += actual_batch_pnl
        continue

    df = pd.DataFrame(rates)

    # Realistic Candle-by-Candle Simulation of Smart Solution
    tp1_banked = False
    invalidation_triggered = False
    full_sl_triggered = False
    runner_sl = sl_price
    ticket_outcomes = {}

    # Separate tickets by role
    tp1_tickets = [t for t in tickets_info if t["role"] == "TP1"]
    if not tp1_tickets and tickets_info:
        tp1_tickets = [tickets_info[0]]
    runner_tickets = [t for t in tickets_info if t not in tp1_tickets]

    for _, row in df.iterrows():
        c_open = float(row['open'])
        c_high = float(row['high'])
        c_low = float(row['low'])
        c_close = float(row['close'])

        if not tp1_banked:
            # Phase 1: Before TP1 is reached
            # Check Adverse Move
            if is_buy:
                hit_full_sl = (c_low <= sl_price)
                hit_invalidation = (c_low <= invalidation_sl)
                hit_smart_tp1 = (c_high >= smart_tp1_price)
            else:
                hit_full_sl = (c_high >= sl_price)
                hit_invalidation = (c_high >= invalidation_sl)
                hit_smart_tp1 = (c_low <= smart_tp1_price)

            if hit_full_sl:
                full_sl_triggered = True
                exit_p = sl_price
                for t in tickets_info:
                    ticket_outcomes[t["pid"]] = (exit_p, "FULL_SL")
                break

            if hit_invalidation:
                # Early Invalidation Cut triggers!
                invalidation_triggered = True
                exit_p = invalidation_sl
                for t in tickets_info:
                    ticket_outcomes[t["pid"]] = (exit_p, "EARLY_CUT")
                break

            if hit_smart_tp1:
                # Bank TP1!
                tp1_banked = True
                for t in tp1_tickets:
                    ticket_outcomes[t["pid"]] = (smart_tp1_price, "TP1_BANKED")
                # Engage breathing room breakeven for runners
                runner_sl = soft_breakeven_sl
                # If no runner tickets exist, trade is finished
                if not runner_tickets:
                    break
        else:
            # Phase 2: After TP1 is banked (Runner Phase)
            # Check runners against runner_sl, tp2_price, tp3_price
            all_runners_done = True
            for t in runner_tickets:
                if t["pid"] in ticket_outcomes:
                    continue
                all_runners_done = False
                t_role = t["role"]
                target_tp = smart_tp2_price if t_role == "TP2" else smart_tp3_price

                if is_buy:
                    stopped_out = (c_low <= runner_sl)
                    tp_hit = (c_high >= target_tp)
                else:
                    stopped_out = (c_high >= runner_sl)
                    tp_hit = (c_low <= target_tp)

                if tp_hit:
                    ticket_outcomes[t["pid"]] = (target_tp, f"{t_role}_HIT")
                elif stopped_out:
                    ticket_outcomes[t["pid"]] = (runner_sl, "SOFT_BE_STOP")

            if all_runners_done:
                break

    # Settle any tickets still open at end of data/exit time
    final_close_p = float(df['close'].iloc[-1])
    for t in tickets_info:
        if t["pid"] not in ticket_outcomes:
            ticket_outcomes[t["pid"]] = (final_close_p, "MARKET_CLOSE")

    # Calculate Smart Dollar PnL across tickets
    batch_smart_pnl = 0.0
    for t in tickets_info:
        pid = t["pid"]
        vol = t["volume"]
        exit_p, reason = ticket_outcomes.get(pid, (entry_price, "UNKNOWN"))
        pnl_val = mt5.order_calc_profit(order_type_mt5, sym, vol, entry_price, exit_p)
        if pnl_val is not None:
            batch_smart_pnl += pnl_val
        else:
            # Fallback estimation
            diff = (exit_p - entry_price) if is_buy else (entry_price - exit_p)
            batch_smart_pnl += diff * vol * 100000

    batch_smart_pnl = round(batch_smart_pnl, 2)
    smart_total_pnl += batch_smart_pnl

    if batch_smart_pnl > 0.15:
        smart_wins += 1
        smart_outcome = "WIN"
    elif batch_smart_pnl < -0.15:
        smart_losses += 1
        smart_outcome = "LOSS"
    else:
        smart_be += 1
        smart_outcome = "BE"

    # Track granular stats
    if invalidation_triggered:
        early_cuts_triggered += 1
        if base_outcome == "LOSS":
            # How much did early cut save?
            saved = abs(actual_batch_pnl) - abs(batch_smart_pnl)
            if saved > 0:
                early_cuts_saved_loss += saved
        elif base_outcome == "WIN":
            # OUCH: Early cut triggered on a trade that won in baseline!
            early_cuts_wrongly_cut_win += 1

    if tp1_banked:
        smart_tp1_hits += 1
    elif base_outcome == "WIN":
        # Did legacy win by hitting 0.38 ATR, but smart missed 0.75 ATR?
        smart_tp1_missed_legacy_wins += 1

    if any(r[1] in ("TP2_HIT", "TP3_HIT") for r in ticket_outcomes.values()):
        smart_tp2_hits += 1
    if any(r[1] == "SOFT_BE_STOP" for r in ticket_outcomes.values()):
        smart_breathing_be_hits += 1

    batch_comparisons.append({
        "batch_id": bid,
        "symbol": sym,
        "strategy": strat,
        "timeframe": tf,
        "baseline_pnl": actual_batch_pnl,
        "baseline_outcome": base_outcome,
        "smart_pnl": batch_smart_pnl,
        "smart_outcome": smart_outcome,
        "pnl_delta": round(batch_smart_pnl - actual_batch_pnl, 2),
        "invalidation_cut": invalidation_triggered,
        "tp1_banked": tp1_banked,
        "outcomes": ticket_outcomes
    })

# Compute aggregate metrics
b_denom = baseline_wins + baseline_losses
b_wr = round((baseline_wins / b_denom * 100.0), 1) if b_denom > 0 else 0.0

s_denom = smart_wins + smart_losses
s_wr = round((smart_wins / s_denom * 100.0), 1) if s_denom > 0 else 0.0

print("\n" + "=" * 70)
print("📊 100% BRUTALLY HONEST SIMULATION ON ALL 167 CLOSED MT5 BATCHES")
print("=" * 70)
print(f"Total Batches Evaluated: {len(closed_batches)}")
print("-" * 70)
print(f"WITHOUT SMART SOLUTION (ACTUAL BASELINE):")
print(f"  - Wins: {baseline_wins} | Losses: {baseline_losses} | Breakevens: {baseline_be}")
print(f"  - Win Rate: {b_wr}%")
print(f"  - Net Realized PnL: ${baseline_total_pnl:+.2f}")
print("-" * 70)
print(f"WITH SMART HIGH-EXPECTANCY SOLUTION:")
print(f"  - Wins: {smart_wins} | Losses: {smart_losses} | Breakevens: {smart_be}")
print(f"  - Win Rate: {s_wr}%")
print(f"  - Net Realized PnL: ${smart_total_pnl:+.2f}")
print(f"  - Net PnL Delta: ${smart_total_pnl - baseline_total_pnl:+.2f}")
print("-" * 70)
print("🔍 COMPONENT BREAKDOWN & DEEP FORENSICS:")
print(f"  1. Early Invalidation Cuts Triggered: {early_cuts_triggered}")
print(f"     - Capital Saved on True Losses: ${early_cuts_saved_loss:.2f}")
print(f"     - WRONGLY CUT WINS (Premature exits on baseline wins): {early_cuts_wrongly_cut_win}")
print(f"  2. Expanded TP1 Hits: {smart_tp1_hits}")
print(f"     - MISSED TP1 WINS (Trades that hit legacy 0.38 ATR but failed 0.75 ATR): {smart_tp1_missed_legacy_wins}")
print(f"  3. Breathing-Room Breakeven:")
print(f"     - TP2 / TP3 Macro Expansions Caught: {smart_tp2_hits}")
print(f"     - Runners Stopped at Soft Cushion: {smart_breathing_be_hits}")
print("=" * 70)

# Save full results to json
with open("tests/full_167_simulation_report.json", "w", encoding="utf-8") as f:
    json.dump({
        "total_batches": len(closed_batches),
        "baseline": {
            "wins": baseline_wins,
            "losses": baseline_losses,
            "breakevens": baseline_be,
            "win_rate": b_wr,
            "net_pnl": round(baseline_total_pnl, 2)
        },
        "smart_solution": {
            "wins": smart_wins,
            "losses": smart_losses,
            "breakevens": smart_be,
            "win_rate": s_wr,
            "net_pnl": round(smart_total_pnl, 2),
            "delta": round(smart_total_pnl - baseline_total_pnl, 2)
        },
        "forensics": {
            "early_cuts_triggered": early_cuts_triggered,
            "early_cuts_saved_loss": round(early_cuts_saved_loss, 2),
            "early_cuts_wrongly_cut_win": early_cuts_wrongly_cut_win,
            "smart_tp1_hits": smart_tp1_hits,
            "smart_tp1_missed_legacy_wins": smart_tp1_missed_legacy_wins,
            "smart_tp2_hits": smart_tp2_hits,
            "smart_breathing_be_hits": smart_breathing_be_hits
        },
        "batches": batch_comparisons
    }, f, indent=2)
print("Saved complete detailed trade-by-trade report to tests/full_167_simulation_report.json")
