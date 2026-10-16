import sys
import os
import json
import re
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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

TF_MAP = {
    '1m': mt5.TIMEFRAME_M1,
    '2m': mt5.TIMEFRAME_M2,
    '3m': mt5.TIMEFRAME_M3,
    '5m': mt5.TIMEFRAME_M5,
    '15m': mt5.TIMEFRAME_M15,
    '30m': mt5.TIMEFRAME_M30,
    '1h': mt5.TIMEFRAME_H1,
    '2h': mt5.TIMEFRAME_H2,
    '3h': mt5.TIMEFRAME_H3,
    '4h': mt5.TIMEFRAME_H4,
    '1d': mt5.TIMEFRAME_D1,
    'daily': mt5.TIMEFRAME_D1,
}

for pid, d_list in pos_map.items():
    entry_deal = next((d for d in d_list if d.entry == 0), None)
    if not entry_deal or entry_deal.time < week_monday_start.timestamp():
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

open_pids = {p.ticket for p in (mt5.positions_get() or [])}

closed_batches = []
for bid, p_tuples in batch_positions.items():
    all_closed = all(pid not in open_pids and any(d.entry == 1 for d in d_list) for pid, d_list in p_tuples)
    if all_closed:
        closed_batches.append((bid, p_tuples))

print(f"Total closed batches to analyze: {len(closed_batches)}")

from src.engine.live_trade_monitor import LiveTradeMonitor
mon = LiveTradeMonitor()

# Models to test:
# Model 1: Time-Stop Expiry (Exit after 12 bars if negative)
# Model 2: Structural Bar-Close Invalidation (Candle closes > 0.50 ATR against entry)
# Model 3: Hybrid (Elapsed >= 6 bars AND Candle closes > 0.50 ATR against entry)

models = {
    "Model_1_TimeStop_12Bars": {
        "name": "Time-Stop Expiry (Exit if negative after 12 bars)",
        "wins": 0, "losses": 0, "be": 0, "total_pnl": 0.0,
        "saved_losses_count": 0, "saved_losses_dollars": 0.0,
        "killed_winners_count": 0, "killed_winners_dollars": 0.0,
        "by_strategy": defaultdict(lambda: {"saved": 0, "killed": 0, "net_diff": 0.0}),
        "by_timeframe": defaultdict(lambda: {"saved": 0, "killed": 0, "net_diff": 0.0})
    },
    "Model_2_Structural_BarClose_0.50ATR": {
        "name": "Structural Bar-Close Invalidation (Candle closes > 0.50 ATR against entry)",
        "wins": 0, "losses": 0, "be": 0, "total_pnl": 0.0,
        "saved_losses_count": 0, "saved_losses_dollars": 0.0,
        "killed_winners_count": 0, "killed_winners_dollars": 0.0,
        "by_strategy": defaultdict(lambda: {"saved": 0, "killed": 0, "net_diff": 0.0}),
        "by_timeframe": defaultdict(lambda: {"saved": 0, "killed": 0, "net_diff": 0.0})
    },
    "Model_3_Hybrid_6Bars_0.50ATR": {
        "name": "Hybrid Time-Stop (Elapsed >= 6 bars AND Candle closes > 0.50 ATR against entry)",
        "wins": 0, "losses": 0, "be": 0, "total_pnl": 0.0,
        "saved_losses_count": 0, "saved_losses_dollars": 0.0,
        "killed_winners_count": 0, "killed_winners_dollars": 0.0,
        "by_strategy": defaultdict(lambda: {"saved": 0, "killed": 0, "net_diff": 0.0}),
        "by_timeframe": defaultdict(lambda: {"saved": 0, "killed": 0, "net_diff": 0.0})
    }
}

baseline_wins = 0
baseline_losses = 0
baseline_be = 0
baseline_pnl = 0.0

trade_sim_details = []

for bid, p_tuples in closed_batches:
    b_meta = batch_meta.get(bid, {})
    sym = b_meta.get("symbol", p_tuples[0][1][0].symbol)
    tf_str = b_meta.get("timeframe", "1h")
    strat_key, strat_name = mon._lookup_strategy_for_batch(bid, comment=b_meta.get("comment", ""), strat_tag=b_meta.get("strat_tag"))

    # Calculate actual baseline PnL
    actual_batch_pnl = sum(float(d.profit) + float(getattr(d, 'swap', 0)) + float(getattr(d, 'commission', 0)) for pid, d_list in p_tuples for d in d_list)
    actual_batch_pnl = round(actual_batch_pnl, 2)
    baseline_pnl += actual_batch_pnl
    if actual_batch_pnl > 0.15:
        baseline_wins += 1
        base_outcome = "WIN"
    elif actual_batch_pnl < -0.15:
        baseline_losses += 1
        base_outcome = "LOSS"
    else:
        baseline_be += 1
        base_outcome = "BE"

    entry_deals = [d for pid, d_list in p_tuples for d in d_list if d.entry == 0]
    exit_deals = [d for pid, d_list in p_tuples for d in d_list if d.entry == 1]
    if not entry_deals or not exit_deals:
        for m_key in models:
            models[m_key]["total_pnl"] += actual_batch_pnl
            if actual_batch_pnl > 0.15: models[m_key]["wins"] += 1
            elif actual_batch_pnl < -0.15: models[m_key]["losses"] += 1
            else: models[m_key]["be"] += 1
        continue

    is_buy = (entry_deals[0].type == 0)
    entry_price = float(entry_deals[0].price)
    entry_time = min(d.time for d in entry_deals)
    exit_time = max(d.time for d in exit_deals)

    total_lots = sum(float(d.volume) for d in entry_deals)
    if total_lots <= 0:
        total_lots = 0.03

    # Calculate SL distance and estimated ATR
    sl_price = 0.0
    for pid, d_list in p_tuples:
        ords = mt5.history_orders_get(position=pid)
        if ords:
            for o in ords:
                if o.sl > 0:
                    sl_price = float(o.sl)
                    break
        if sl_price > 0: break
    if sl_price <= 0:
        for pid, d_list in p_tuples:
            for d in d_list:
                if '[sl ' in d.comment:
                    m = re.search(r'\[sl\s+([0-9.]+)\]', d.comment)
                    if m:
                        sl_price = float(m.group(1))
                        break
            if sl_price > 0: break

    risk_dist = abs(entry_price - sl_price) if sl_price > 0 else 0.0
    est_atr = risk_dist / 1.80 if risk_dist > 0 else entry_price * 0.005

    # Fetch MT5 candles on the trade's timeframe between entry_time and exit_time
    mt5_tf = TF_MAP.get(tf_str, mt5.TIMEFRAME_M15)
    rates = mt5.copy_rates_range(sym, mt5_tf, entry_time - 3600, exit_time + 3600)
    if rates is None or len(rates) == 0:
        # Fallback to M1
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, entry_time - 600, exit_time + 600)

    # Convert to dataframe
    df_bars = pd.DataFrame(rates) if rates is not None and len(rates) > 0 else pd.DataFrame()
    if len(df_bars) > 0:
        trade_bars = df_bars[(df_bars['time'] >= entry_time) & (df_bars['time'] <= exit_time)]
    else:
        trade_bars = pd.DataFrame()

    batch_sim = {
        "bid": bid, "symbol": sym, "strategy": strat_name, "timeframe": tf_str,
        "entry_price": entry_price, "actual_pnl": actual_batch_pnl, "base_outcome": base_outcome,
        "models": {}
    }

    # Simulate each model
    for m_key, m_data in models.items():
        cut_triggered = False
        cut_price = 0.0
        cut_time = 0
        cut_bar_idx = 0

        if len(trade_bars) >= 2:
            for bar_idx, (_, bar) in enumerate(trade_bars.iterrows(), start=1):
                b_close = float(bar['close'])
                b_open = float(bar['open'])
                b_time = int(bar['time'])

                # Adverse distance from entry
                adverse_dist = (entry_price - b_close) if is_buy else (b_close - entry_price)
                is_adverse = (adverse_dist > 0)

                # Check Condition for Model 1:
                if m_key == "Model_1_TimeStop_12Bars":
                    if bar_idx >= 12 and is_adverse:
                        cut_triggered = True
                        cut_price = b_close
                        cut_time = b_time
                        cut_bar_idx = bar_idx
                        break

                # Check Condition for Model 2:
                elif m_key == "Model_2_Structural_BarClose_0.50ATR":
                    if adverse_dist >= 0.50 * est_atr:
                        cut_triggered = True
                        cut_price = b_close
                        cut_time = b_time
                        cut_bar_idx = bar_idx
                        break

                # Check Condition for Model 3:
                elif m_key == "Model_3_Hybrid_6Bars_0.50ATR":
                    if bar_idx >= 6 and adverse_dist >= 0.50 * est_atr:
                        cut_triggered = True
                        cut_price = b_close
                        cut_time = b_time
                        cut_bar_idx = bar_idx
                        break

        if cut_triggered and cut_price > 0:
            # Estimate PnL at early cut:
            # Price delta * total_lots
            # Approximate ratio based on actual PnL
            if risk_dist > 0:
                loss_ratio = (entry_price - cut_price) / risk_dist if is_buy else (cut_price - entry_price) / risk_dist
                # Estimated loss dollar
                sim_pnl = -abs(loss_ratio * abs(actual_batch_pnl)) if loss_ratio > 0 else abs(actual_batch_pnl) * 0.2
            else:
                sim_pnl = actual_batch_pnl * 0.5
            sim_pnl = round(sim_pnl, 2)

            # Analyze if this was a SAVED LOSS or a KILLED WINNER:
            pnl_diff = sim_pnl - actual_batch_pnl

            if base_outcome == "LOSS":
                # Real trade lost (e.g. -$28). We cut early at (e.g. -$12).
                # This is a TRUE POSITIVE (Saved Loss!)
                m_data["saved_losses_count"] += 1
                saved_amt = max(0.0, pnl_diff)
                m_data["saved_losses_dollars"] += saved_amt
                m_data["by_strategy"][strat_name]["saved"] += 1
                m_data["by_strategy"][strat_name]["net_diff"] += pnl_diff
                m_data["by_timeframe"][tf_str]["saved"] += 1
                m_data["by_timeframe"][tf_str]["net_diff"] += pnl_diff
                res_type = "SAVED_LOSS"
            elif base_outcome == "WIN":
                # Real trade WON (e.g. +$4.50). We cut early at a loss (e.g. -$8.00).
                # This is a FALSE POSITIVE (Killed Winner!)
                m_data["killed_winners_count"] += 1
                killed_amt = abs(pnl_diff)
                m_data["killed_winners_dollars"] += killed_amt
                m_data["by_strategy"][strat_name]["killed"] += 1
                m_data["by_strategy"][strat_name]["net_diff"] += pnl_diff
                m_data["by_timeframe"][tf_str]["killed"] += 1
                m_data["by_timeframe"][tf_str]["net_diff"] += pnl_diff
                res_type = "KILLED_WINNER"
            else:
                res_type = "NEUTRAL_BE"

            final_pnl = sim_pnl
        else:
            final_pnl = actual_batch_pnl
            res_type = "NO_TRIGGER"

        m_data["total_pnl"] += final_pnl
        if final_pnl > 0.15: m_data["wins"] += 1
        elif final_pnl < -0.15: m_data["losses"] += 1
        else: m_data["be"] += 1

        batch_sim["models"][m_key] = {
            "cut_triggered": cut_triggered,
            "res_type": res_type,
            "sim_pnl": final_pnl,
            "cut_bar_idx": cut_bar_idx
        }

    trade_sim_details.append(batch_sim)

# Print Summary Results
print("\n" + "=" * 80)
print("🎯 MASTER FORENSIC SIMULATION: POST-TRADE TIME-STOP & BAR INVALIDATION GUARD")
print("=" * 80)

total_trades = baseline_wins + baseline_losses + baseline_be
base_wr = (baseline_wins / total_trades * 100) if total_trades > 0 else 0.0
print(f"\n📌 REAL BASELINE (CURRENT SYSTEM):")
print(f"  Total Trades: {total_trades} | Wins: {baseline_wins} | Losses: {baseline_losses} | BE: {baseline_be}")
print(f"  Win Rate: {base_wr:.1f}% | Net PnL: ${baseline_pnl:.2f}")

report_data = {
    "baseline": {
        "total_trades": total_trades,
        "wins": baseline_wins,
        "losses": baseline_losses,
        "be": baseline_be,
        "win_rate_pct": round(base_wr, 1),
        "net_pnl_usd": round(baseline_pnl, 2)
    },
    "models": {}
}

for m_key, m_data in models.items():
    m_tot = m_data["wins"] + m_data["losses"] + m_data["be"]
    m_wr = (m_data["wins"] / m_tot * 100) if m_tot > 0 else 0.0
    pnl_diff = m_data["total_pnl"] - baseline_pnl
    wr_diff = m_wr - base_wr

    print(f"\n📊 {m_data['name'].upper()}:")
    print(f"  Total Trades: {m_tot} | Wins: {m_data['wins']} | Losses: {m_data['losses']} | BE: {m_data['be']}")
    print(f"  Win Rate: {m_wr:.1f}% (Diff: {wr_diff:+.1f}%) | Net PnL: ${m_data['total_pnl']:.2f} (Diff: ${pnl_diff:+.2f})")
    print(f"  🛡️ True Positives (Saved Losses): {m_data['saved_losses_count']} trades (Saved +${m_data['saved_losses_dollars']:.2f})")
    print(f"  🛑 False Positives (Killed Winners): {m_data['killed_winners_count']} trades (Destroyed -${m_data['killed_winners_dollars']:.2f})")

    report_data["models"][m_key] = {
        "name": m_data["name"],
        "wins": m_data["wins"],
        "losses": m_data["losses"],
        "be": m_data["be"],
        "win_rate_pct": round(m_wr, 1),
        "win_rate_diff": round(wr_diff, 1),
        "net_pnl_usd": round(m_data["total_pnl"], 2),
        "net_pnl_diff": round(pnl_diff, 2),
        "saved_losses_count": m_data["saved_losses_count"],
        "saved_losses_dollars": round(m_data["saved_losses_dollars"], 2),
        "killed_winners_count": m_data["killed_winners_count"],
        "killed_winners_dollars": round(m_data["killed_winners_dollars"], 2),
        "by_strategy": {k: dict(v) for k, v in m_data["by_strategy"].items()},
        "by_timeframe": {k: dict(v) for k, v in m_data["by_timeframe"].items()}
    }

# Breakdown by Strategy for the best model or Model 2
print("\n" + "=" * 80)
print("🔍 STRATEGY & TIMEFRAME SENSITIVITY BREAKDOWN (MODEL 2: BAR-CLOSE INVALIDATION):")
print("=" * 80)

print("\n--- By Strategy ---")
for strat, s_data in models["Model_2_Structural_BarClose_0.50ATR"]["by_strategy"].items():
    s_clean = strat.encode('ascii', 'ignore').decode().strip()
    print(f"  {s_clean[:35]:<36} | Saved: {s_data['saved']:>2} | Killed: {s_data['killed']:>2} | Net PnL Diff: ${s_data['net_diff']:>+7.2f}")

print("\n--- By Timeframe ---")
for tf, t_data in models["Model_2_Structural_BarClose_0.50ATR"]["by_timeframe"].items():
    print(f"  Timeframe {tf:<6} | Saved: {t_data['saved']:>2} | Killed: {t_data['killed']:>2} | Net PnL Diff: ${t_data['net_diff']:>+7.2f}")

with open("tests/time_stop_simulation_results.json", "w", encoding="utf-8") as f:
    json.dump(report_data, f, indent=2)

print("\nResults written to tests/time_stop_simulation_results.json successfully.")
mt5.shutdown()
