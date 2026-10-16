import sys
import os
import json
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

print("=" * 80)
print("🚀 CONNECTING TO MT5 & LOADING ALL-TIME AUTONOMOUS HISTORY (1,100+ TRADES)")
print("=" * 80)

if not mt5.initialize():
    print("MT5 initialization failed")
    sys.exit(1)

MAGIC_NUMBER = 999888
t_start = datetime(2020, 1, 1)
now = datetime.now()

deals = mt5.history_deals_get(t_start, now)
if deals is None:
    print("No deals found in MT5 history.")
    sys.exit(1)

magic_deals = [d for d in deals if d.magic == MAGIC_NUMBER]
print(f"Total Magic 999888 Deals in MT5 History: {len(magic_deals)}")

# Group deals by position_id
pos_map = defaultdict(list)
for d in magic_deals:
    pos_map[d.position_id].append(d)

print(f"Total Unique Positions: {len(pos_map)}")

# Reconstruct batches
batch_positions = defaultdict(list)
batch_meta = {}
VALID_TFS = {'1m', '2m', '3m', '5m', '15m', '30m', '45m', '1h', '2h', '3h', '4h', 'd', '1d', 'daily', 'w', '1w'}

for pid, d_list in pos_map.items():
    entry_deal = next((d for d in d_list if d.entry == 0), None)
    if not entry_deal:
        continue

    comm = entry_deal.comment if entry_deal else d_list[0].comment
    bid = None
    tf = "1h"
    strat_tag = "CORE"
    if "QS_" in comm:
        parts = comm.split("_")
        if len(parts) >= 2:
            bid = parts[1]
        for part in parts[2:]:
            p_clean = part.lower().strip()
            if p_clean in VALID_TFS or (len(p_clean) >= 2 and p_clean[-1] in 'mhd' and p_clean[:-1].isdigit()):
                tf = p_clean
                break
        if len(parts) >= 4:
            strat_tag = parts[2].upper().strip()
    elif "AUTOBE_" in comm:
        parts = comm.split("_")
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
            "comment": comm
        }

# Check currently open positions to strictly filter for 100% completed/closed batches
current_open_positions = mt5.positions_get()
open_pids = set(p.ticket for p in current_open_positions) if current_open_positions else set()

closed_batches = []
for bid, p_tuples in batch_positions.items():
    all_closed = all(pid not in open_pids and any(d.entry == 1 for d in d_list) for pid, d_list in p_tuples)
    if all_closed:
        closed_batches.append((bid, p_tuples))

print(f"Total Valid Closed Batches for Simulation: {len(closed_batches)}")

# Extract start and end dates
all_entry_times = [d.time for bid, p_tuples in closed_batches for pid, d_list in p_tuples for d in d_list if d.entry == 0]
min_dt = datetime.fromtimestamp(min(all_entry_times))
max_dt = datetime.fromtimestamp(max(all_entry_times))
print(f"Dataset Timeline: {min_dt.strftime('%Y-%m-%d %H:%M')} to {max_dt.strftime('%Y-%m-%d %H:%M')} ({(max_dt - min_dt).days} days)")

print("-" * 80)
print("Fetching real M1 historical candles for all trades...")
t0_fetch = time.time()

candle_cache = {}
skipped_no_candles = 0

for idx, (bid, p_tuples) in enumerate(closed_batches):
    sym = p_tuples[0][1][0].symbol
    entry_deals = [d for pid, d_list in p_tuples for d in d_list if d.entry == 0]
    exit_deals = [d for pid, d_list in p_tuples for d in d_list if d.entry == 1]
    if not entry_deals or not exit_deals:
        continue

    dt_entry = datetime.fromtimestamp(min(d.time for d in entry_deals))
    dt_exit = datetime.fromtimestamp(max(d.time for d in exit_deals))

    # Fetch M1 bars with 2 min pre-buffer and 30 min post-buffer
    rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, dt_entry - timedelta(minutes=2), dt_exit + timedelta(minutes=30))
    if rates is None or len(rates) == 0:
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, dt_entry - timedelta(minutes=10), dt_exit + timedelta(minutes=60))

    if rates is not None and len(rates) > 0:
        candle_cache[bid] = pd.DataFrame(rates)
    else:
        skipped_no_candles += 1

print(f"Fetched candles for {len(candle_cache)} batches in {time.time() - t0_fetch:.2f}s (Skipped: {skipped_no_candles})")
print("=" * 80)

# Configurations to test:
# 1. Baseline: Exactly what actually happened on MT5 broker execution
# 2. Smart Solution (0.25 ATR cushion): Breathing-Room BE on runners after 0.38 ATR scalp bank
# 3. Smart Solution (0.35 ATR cushion): Slightly wider breathing room on runners

configs = {
    "Baseline (Actual MT5 Reality)": {"be_cushion": 0.0, "use_actual": True},
    "Smart Solution (0.25 ATR Breathing BE)": {"be_cushion": 0.25, "use_actual": False},
    "Smart Solution (0.35 ATR Breathing BE)": {"be_cushion": 0.35, "use_actual": False},
}

summary_results = {}
strat_results = defaultdict(lambda: defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0}))
sym_results = defaultdict(lambda: defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0}))

for cfg_name, cfg in configs.items():
    cushion_m = cfg["be_cushion"]
    is_actual = cfg["use_actual"]

    total_pnl = 0.0
    wins = 0
    losses = 0
    breakevens = 0
    tp1_hits = 0
    tp2_hits = 0
    tp3_hits = 0
    be_stops = 0
    full_sl_hits = 0

    win_amounts = []
    loss_amounts = []

    for bid, p_tuples in closed_batches:
        # 1. Baseline actual PnL
        actual_batch_pnl = 0.0
        for pid, d_list in p_tuples:
            for d in d_list:
                actual_batch_pnl += float(d.profit) + float(getattr(d, 'swap', 0.0) or 0.0) + float(getattr(d, 'commission', 0.0) or 0.0)
        actual_batch_pnl = round(actual_batch_pnl, 2)

        sym = p_tuples[0][1][0].symbol
        b_meta = batch_meta.get(bid, {})
        strat = b_meta.get("strat_tag", "CORE")

        if is_actual:
            total_pnl += actual_batch_pnl
            if actual_batch_pnl > 0.15:
                wins += 1
                win_amounts.append(actual_batch_pnl)
                strat_results[cfg_name][strat]["wins"] += 1
                sym_results[cfg_name][sym]["wins"] += 1
            elif actual_batch_pnl < -0.15:
                losses += 1
                loss_amounts.append(actual_batch_pnl)
                strat_results[cfg_name][strat]["losses"] += 1
                sym_results[cfg_name][sym]["losses"] += 1
            else:
                breakevens += 1
            strat_results[cfg_name][strat]["pnl"] += actual_batch_pnl
            sym_results[cfg_name][sym]["pnl"] += actual_batch_pnl
            continue

        df = candle_cache.get(bid)
        if df is None:
            # Fallback to actual
            total_pnl += actual_batch_pnl
            if actual_batch_pnl > 0.15:
                wins += 1
                win_amounts.append(actual_batch_pnl)
            elif actual_batch_pnl < -0.15:
                losses += 1
                loss_amounts.append(actual_batch_pnl)
            else:
                breakevens += 1
            continue

        entry_deals = [d for pid, d_list in p_tuples for d in d_list if d.entry == 0]
        is_buy = (entry_deals[0].type == 0)
        entry_price = float(entry_deals[0].price)
        order_type_mt5 = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL

        # Find initial SL and tickets
        sl_price = 0.0
        tickets_info = []
        for pid, d_list in p_tuples:
            e_deal = next((d for d in d_list if d.entry == 0), None)
            vol = e_deal.volume if e_deal else 0.01
            role = "TP1"
            ords = mt5.history_orders_get(position=pid)
            if ords:
                for o in ords:
                    if o.sl > 0 and sl_price == 0.0:
                        sl_price = float(o.sl)
                    if "_TP1" in o.comment:
                        role = "TP1"
                    elif "_TP2" in o.comment:
                        role = "TP2"
                    elif "_TP3" in o.comment:
                        role = "TP3"
            tickets_info.append({"pid": pid, "role": role, "volume": vol})

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

        if sl_price <= 0.0 or entry_price <= 0.0:
            total_pnl += actual_batch_pnl
            if actual_batch_pnl > 0.15: wins += 1; win_amounts.append(actual_batch_pnl)
            elif actual_batch_pnl < -0.15: losses += 1; loss_amounts.append(actual_batch_pnl)
            else: breakevens += 1
            continue

        risk_dist = abs(entry_price - sl_price)
        if risk_dist <= 0:
            total_pnl += actual_batch_pnl
            continue

        safe_atr = risk_dist / 1.80

        # Precision TP1 Scalp Bank (0.38 * ATR)
        target_tp1 = entry_price + (0.38 * safe_atr) if is_buy else entry_price - (0.38 * safe_atr)
        # Breathing Breakeven SL for runners
        cushion_sl = entry_price - (cushion_m * safe_atr) if is_buy else entry_price + (cushion_m * safe_atr)
        # Macro runner targets (1:1+ and 2:1+)
        target_tp2 = entry_price + (1.15 * risk_dist) if is_buy else entry_price - (1.15 * risk_dist)
        target_tp3 = entry_price + (2.20 * risk_dist) if is_buy else entry_price - (2.20 * risk_dist)

        tp1_banked = False
        runner_sl = sl_price
        ticket_outcomes = {}

        tp1_tickets = [t for t in tickets_info if t["role"] == "TP1"]
        if not tp1_tickets and tickets_info:
            tp1_tickets = [tickets_info[0]]
        runner_tickets = [t for t in tickets_info if t not in tp1_tickets]

        # Candle-by-candle evaluation
        for _, row in df.iterrows():
            c_high = float(row['high'])
            c_low = float(row['low'])

            if not tp1_banked:
                # Check adverse full stop first
                if is_buy:
                    hit_full_sl = (c_low <= sl_price)
                    hit_tp1 = (c_high >= target_tp1)
                else:
                    hit_full_sl = (c_high >= sl_price)
                    hit_tp1 = (c_low <= target_tp1)

                if hit_full_sl:
                    full_sl_hits += 1
                    for t in tickets_info:
                        ticket_outcomes[t["pid"]] = (sl_price, "FULL_SL")
                    break

                if hit_tp1:
                    tp1_banked = True
                    tp1_hits += 1
                    for t in tp1_tickets:
                        ticket_outcomes[t["pid"]] = (target_tp1, "TP1_BANKED")
                    runner_sl = cushion_sl
                    if not runner_tickets:
                        break
            else:
                # Runner phase: Check runners against cushion_sl and macro targets
                all_done = True
                for t in runner_tickets:
                    if t["pid"] in ticket_outcomes:
                        continue
                    all_done = False
                    t_role = t["role"]
                    target_tp = target_tp3 if t_role == "TP3" else target_tp2

                    if is_buy:
                        hit_tp = (c_high >= target_tp)
                        hit_stop = (c_low <= runner_sl)
                    else:
                        hit_tp = (c_low <= target_tp)
                        hit_stop = (c_high >= runner_sl)

                    if hit_tp:
                        ticket_outcomes[t["pid"]] = (target_tp, f"{t_role}_HIT")
                        if t_role == "TP3":
                            tp3_hits += 1
                        else:
                            tp2_hits += 1
                    elif hit_stop:
                        ticket_outcomes[t["pid"]] = (runner_sl, "BE_STOP")
                        be_stops += 1

                if all_done:
                    break

        # Settle any unclosed tickets at final candle close
        final_close_p = float(df['close'].iloc[-1])
        for t in tickets_info:
            if t["pid"] not in ticket_outcomes:
                ticket_outcomes[t["pid"]] = (final_close_p, "MARKET_CLOSE")

        # Calculate exact dollar profit across all tickets
        batch_sim_pnl = 0.0
        for t in tickets_info:
            pid = t["pid"]
            vol = t["volume"]
            exit_p, reason = ticket_outcomes.get(pid, (entry_price, "UNKNOWN"))
            pnl_val = mt5.order_calc_profit(order_type_mt5, sym, vol, entry_price, exit_p)
            if pnl_val is not None:
                batch_sim_pnl += pnl_val
            else:
                diff = (exit_p - entry_price) if is_buy else (entry_price - exit_p)
                batch_sim_pnl += diff * vol * 100000

        batch_sim_pnl = round(batch_sim_pnl, 2)
        total_pnl += batch_sim_pnl

        if batch_sim_pnl > 0.15:
            wins += 1
            win_amounts.append(batch_sim_pnl)
            strat_results[cfg_name][strat]["wins"] += 1
            sym_results[cfg_name][sym]["wins"] += 1
        elif batch_sim_pnl < -0.15:
            losses += 1
            loss_amounts.append(batch_sim_pnl)
            strat_results[cfg_name][strat]["losses"] += 1
            sym_results[cfg_name][sym]["losses"] += 1
        else:
            breakevens += 1

        strat_results[cfg_name][strat]["pnl"] += batch_sim_pnl
        sym_results[cfg_name][sym]["pnl"] += batch_sim_pnl

    denom = wins + losses
    wr = round((wins / denom * 100.0), 1) if denom > 0 else 0.0
    avg_win = round(sum(win_amounts) / len(win_amounts), 2) if win_amounts else 0.0
    avg_loss = round(sum(loss_amounts) / len(loss_amounts), 2) if loss_amounts else 0.0

    summary_results[cfg_name] = {
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": wr,
        "total_pnl": round(total_pnl, 2),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "tp1_hits": tp1_hits,
        "tp2_hits": tp2_hits,
        "tp3_hits": tp3_hits,
        "be_stops": be_stops,
        "full_sl_hits": full_sl_hits
    }

print("\n" + "=" * 90)
print(f"📊 ULTIMATE ALL-TIME SIMULATION RESULTS ACROSS {len(closed_batches)} REAL MT5 CLOSED TRADES")
print("=" * 90)
print(f"{'Configuration':<38} | {'W / L / BE':<14} | {'Win Rate':<9} | {'Avg Win':<8} | {'Avg Loss':<9} | {'Net Realized PnL':<15}")
print("-" * 90)

for name, res in summary_results.items():
    wlbe = f"{res['wins']}W / {res['losses']}L / {res['breakevens']}BE"
    pnl_str = f"${res['total_pnl']:+,.2f}"
    print(f"{name:<38} | {wlbe:<14} | {res['win_rate']:<7}% | +${res['avg_win']:<6.2f} | -${abs(res['avg_loss']):<7.2f} | {pnl_str:<15}")

print("=" * 90)

# Save complete summary to json
with open("tests/all_time_1148_trades_report.json", "w", encoding="utf-8") as f:
    json.dump({
        "total_trades": len(closed_batches),
        "date_range": f"{min_dt.strftime('%Y-%m-%d')} to {max_dt.strftime('%Y-%m-%d')}",
        "summary": summary_results,
        "by_strategy": {k: dict(v) for k, v in strat_results.items()},
        "by_symbol": {k: dict(v) for k, v in sym_results.items()}
    }, f, indent=2)

print("Saved all-time simulation report to tests/all_time_1148_trades_report.json")
