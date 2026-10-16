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
magic_deals = [d for d in deals if d.magic == MAGIC_NUMBER]

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

print(f"Loaded {len(closed_batches)} closed batches for component isolation testing.")

# We will test 5 distinct configurations on the exact same 167 trades:
# Config 0: Baseline (Actual MT5 Result)
# Config 1: ONLY Breathing-Room Breakeven (TP1 stays 0.38 ATR, no early cut, runners get 0.30 ATR cushion)
# Config 2: ONLY Early Cut at 1.20 ATR (not tight 0.75, giving breathing room but cutting catastrophic slippage)
# Config 3: Moderate TP1 (0.50 ATR instead of 0.75 ATR) + Breathing Room
# Config 4: The 3-Tier Smart Solution (TP1 0.75 ATR + Early Cut 0.75 ATR + Soft BE 0.40 ATR)

configs = {
    "Baseline (Current Reality)": {"tp1_mult": 0.38, "cut_mult": 0.0, "be_cushion": 0.0, "use_actual": True},
    "Config 1: Only Breathing-Room BE (0.25 ATR cushion)": {"tp1_mult": 0.38, "cut_mult": 0.0, "be_cushion": 0.25, "use_actual": False},
    "Config 2: Modest TP1 (0.50 ATR) + Breathing BE": {"tp1_mult": 0.50, "cut_mult": 0.0, "be_cushion": 0.25, "use_actual": False},
    "Config 3: Safe Early Cut (1.20 ATR) + Legacy TP1": {"tp1_mult": 0.38, "cut_mult": 1.20, "be_cushion": 0.0, "use_actual": False},
    "Config 4: Full Smart Solution (TP1 0.75, Cut 0.75)": {"tp1_mult": 0.75, "cut_mult": 0.75, "be_cushion": 0.40, "use_actual": False},
}

results = {name: {"wins": 0, "losses": 0, "be": 0, "pnl": 0.0, "tp2_hits": 0, "premature_cuts": 0} for name in configs}

# Pre-fetch candle cache for all batches to run lightning fast
candle_cache = {}
for bid, p_tuples in closed_batches:
    sym = p_tuples[0][1][0].symbol
    entry_deals = [d for pid, d_list in p_tuples for d in d_list if d.entry == 0]
    exit_deals = [d for pid, d_list in p_tuples for d in d_list if d.entry == 1]
    if not entry_deals or not exit_deals:
        continue
    dt_entry = datetime.fromtimestamp(min(d.time for d in entry_deals))
    dt_exit = datetime.fromtimestamp(max(d.time for d in exit_deals))
    rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, dt_entry - timedelta(minutes=2), dt_exit + timedelta(minutes=30))
    if rates is None or len(rates) == 0:
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, dt_entry - timedelta(minutes=10), dt_exit + timedelta(minutes=60))
    if rates is not None and len(rates) > 0:
        candle_cache[bid] = pd.DataFrame(rates)

print(f"Candles cached for {len(candle_cache)} batches.")

for cfg_name, cfg in configs.items():
    tp1_m = cfg["tp1_mult"]
    cut_m = cfg["cut_mult"]
    cushion_m = cfg["be_cushion"]
    is_actual = cfg["use_actual"]

    for bid, p_tuples in closed_batches:
        # Reconstruct actual baseline PnL
        actual_batch_pnl = 0.0
        for pid, d_list in p_tuples:
            for d in d_list:
                actual_batch_pnl += float(d.profit) + float(getattr(d, 'swap', 0.0) or 0.0) + float(getattr(d, 'commission', 0.0) or 0.0)
        actual_batch_pnl = round(actual_batch_pnl, 2)

        if is_actual:
            results[cfg_name]["pnl"] += actual_batch_pnl
            if actual_batch_pnl > 0.15:
                results[cfg_name]["wins"] += 1
            elif actual_batch_pnl < -0.15:
                results[cfg_name]["losses"] += 1
            else:
                results[cfg_name]["be"] += 1
            continue

        df = candle_cache.get(bid)
        if df is None:
            results[cfg_name]["pnl"] += actual_batch_pnl
            if actual_batch_pnl > 0.15: results[cfg_name]["wins"] += 1
            elif actual_batch_pnl < -0.15: results[cfg_name]["losses"] += 1
            else: results[cfg_name]["be"] += 1
            continue

        sym = p_tuples[0][1][0].symbol
        entry_deals = [d for pid, d_list in p_tuples for d in d_list if d.entry == 0]
        is_buy = (entry_deals[0].type == 0)
        entry_price = float(entry_deals[0].price)
        order_type_mt5 = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL

        # Find SL
        sl_price = 0.0
        tickets_info = []
        for pid, d_list in p_tuples:
            e_deal = next((d for d in d_list if d.entry == 0), None)
            vol = e_deal.volume if e_deal else 0.01
            role = "TP1"
            ords = mt5.history_orders_get(position=pid)
            if ords:
                for o in ords:
                    if o.sl > 0 and sl_price == 0.0: sl_price = float(o.sl)
                    if "_TP1" in o.comment: role = "TP1"
                    elif "_TP2" in o.comment: role = "TP2"
                    elif "_TP3" in o.comment: role = "TP3"
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
                if sl_price > 0.0: break

        if sl_price <= 0.0 or entry_price <= 0.0:
            results[cfg_name]["pnl"] += actual_batch_pnl
            continue

        risk_dist = abs(entry_price - sl_price)
        if risk_dist <= 0:
            results[cfg_name]["pnl"] += actual_batch_pnl
            continue

        safe_atr = risk_dist / 1.80

        target_tp1 = entry_price + (tp1_m * safe_atr) if is_buy else entry_price - (tp1_m * safe_atr)
        inval_sl = (entry_price - (cut_m * safe_atr) if is_buy else entry_price + (cut_m * safe_atr)) if cut_m > 0 else sl_price
        cushion_sl = (entry_price - (cushion_m * safe_atr) if is_buy else entry_price + (cushion_m * safe_atr)) if cushion_m > 0 else entry_price
        target_tp2 = entry_price + (1.15 * risk_dist) if is_buy else entry_price - (1.15 * risk_dist)

        tp1_banked = False
        runner_sl = sl_price
        ticket_outcomes = {}

        tp1_tickets = [t for t in tickets_info if t["role"] == "TP1"]
        if not tp1_tickets and tickets_info:
            tp1_tickets = [tickets_info[0]]
        runner_tickets = [t for t in tickets_info if t not in tp1_tickets]

        for _, row in df.iterrows():
            c_high = float(row['high'])
            c_low = float(row['low'])

            if not tp1_banked:
                if is_buy:
                    hit_full_sl = (c_low <= sl_price)
                    hit_inval = (c_low <= inval_sl) if cut_m > 0 else False
                    hit_tp1 = (c_high >= target_tp1)
                else:
                    hit_full_sl = (c_high >= sl_price)
                    hit_inval = (c_high >= inval_sl) if cut_m > 0 else False
                    hit_tp1 = (c_low <= target_tp1)

                if hit_full_sl:
                    for t in tickets_info: ticket_outcomes[t["pid"]] = (sl_price, "FULL_SL")
                    break
                if hit_inval:
                    for t in tickets_info: ticket_outcomes[t["pid"]] = (inval_sl, "EARLY_CUT")
                    if actual_batch_pnl > 0.15:
                        results[cfg_name]["premature_cuts"] += 1
                    break
                if hit_tp1:
                    tp1_banked = True
                    for t in tp1_tickets: ticket_outcomes[t["pid"]] = (target_tp1, "TP1_BANKED")
                    runner_sl = cushion_sl
                    if not runner_tickets: break
            else:
                all_done = True
                for t in runner_tickets:
                    if t["pid"] in ticket_outcomes: continue
                    all_done = False
                    if is_buy:
                        hit_tp2 = (c_high >= target_tp2)
                        hit_stop = (c_low <= runner_sl)
                    else:
                        hit_tp2 = (c_low <= target_tp2)
                        hit_stop = (c_high >= runner_sl)

                    if hit_tp2:
                        ticket_outcomes[t["pid"]] = (target_tp2, "TP2_HIT")
                        results[cfg_name]["tp2_hits"] += 1
                    elif hit_stop:
                        ticket_outcomes[t["pid"]] = (runner_sl, "BE_STOP")
                if all_done: break

        final_close_p = float(df['close'].iloc[-1])
        for t in tickets_info:
            if t["pid"] not in ticket_outcomes:
                ticket_outcomes[t["pid"]] = (final_close_p, "MARKET_CLOSE")

        batch_pnl = 0.0
        for t in tickets_info:
            pid = t["pid"]
            vol = t["volume"]
            exit_p, reason = ticket_outcomes.get(pid, (entry_price, "UNKNOWN"))
            pnl_val = mt5.order_calc_profit(order_type_mt5, sym, vol, entry_price, exit_p)
            if pnl_val is not None:
                batch_pnl += pnl_val
            else:
                diff = (exit_p - entry_price) if is_buy else (entry_price - exit_p)
                batch_pnl += diff * vol * 100000

        batch_pnl = round(batch_pnl, 2)
        results[cfg_name]["pnl"] += batch_pnl
        if batch_pnl > 0.15:
            results[cfg_name]["wins"] += 1
        elif batch_pnl < -0.15:
            results[cfg_name]["losses"] += 1
        else:
            results[cfg_name]["be"] += 1

print("\n" + "=" * 80)
print("🏆 ISOLATED COMPONENT COMPARISON ON ALL 167 REAL TRADES")
print("=" * 80)
print(f"{'Configuration':<42} | {'Wins':<5} | {'Loss':<5} | {'BE':<4} | {'WinRate':<7} | {'Net PnL':<10} | {'TP2 Hits'}")
print("-" * 80)

for name, res in results.items():
    w = res["wins"]
    l = res["losses"]
    b = res["be"]
    denom = w + l
    wr = round((w / denom * 100.0), 1) if denom > 0 else 0.0
    pnl = round(res["pnl"], 2)
    tp2 = res["tp2_hits"]
    print(f"{name:<42} | {w:<5} | {l:<5} | {b:<4} | {wr:<6}% | ${pnl:<9.2f} | {tp2}")
print("=" * 80)
