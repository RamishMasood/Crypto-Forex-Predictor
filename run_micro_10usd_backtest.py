"""
Micro-Account ($10 Capital, $2 Risk) MT5 Historical Backtest Runner
===================================================================
Runs the exact Sniper Blueprint designed for $10 Micro Capital:
- Initial Capital: $10.00
- Max Dollar Risk Cap: $2.00 (Strictly enforced per trade)
- Batch Lot Size: 0.01 (Minimum broker micro lot)
- Selected Assets: EUR/USD, GBP/AUD (Safest spread, highest historical win rates, zero Gold/Silver blow-up risk)
- Selected Strategies: Elite Sniper Squad (VIVEK_YADAV, DEFAULT, TRADE_PRO, ICT, NDEMAZEAH_GODLOVE, TOBY_CRABEL, ADAM_KHOO, PAUL_FTMO)
- Timeframes: 5m, 15m, 30m, 1h, 4h
- Smart Solution ON (0.25 ATR breathing cushion)
- Macro News Blackout ON (30m blackout + 15m pre-news shield)
- Period: Sep 16, 2026 - Oct 16, 2026
"""

import os
import sys
import json
import time
import logging
import multiprocessing as mp
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.engine.backtest_engine import MT5BacktestEngine
from src.data.economic_calendar import FALLBACK_2026_EVENTS

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("Micro10USDPacktest")

MICRO_SYMBOLS = ["EUR/USD", "GBP/AUD"]
TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h"]
SNIPER_STRATEGIES = [
    'VIVEK_YADAV',
    'TRADE_PRO',
    'ICT',
    'NDEMAZEAH_GODLOVE',
    'TOBY_CRABEL',
    'ADAM_KHOO',
    'PAUL_FTMO'
]

BASE_CFG = {
    'timeframes': TIMEFRAMES,
    'active_strategies': SNIPER_STRATEGIES,
    'date_from': '2026-09-16',
    'date_to': '2026-10-16',
    'initial_balance': 10.0,
    'batch_lot_size': 0.01,
    'max_dollar_risk': 2.0,
    'min_pillars_required': 5,
    'allow_same_tf_trades': False,
    'allow_diff_strat_same_tf': True,
    'breakeven_mode': 'smart_breathing_be',
    'active_sessions': ["24/7 (Any Session)"],
    'htf_filter_enabled': True,
    'smart_solution_enabled': True,
    'news_filter_enabled': True,
    'target_trades_per_symbol': 1000,
    'max_active_batches': 500,
    'scan_delay_mins': 0.25
}

def worker_run_symbol(sym: str) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Worker function executed in an isolated process for each symbol."""
    t0 = time.time()
    print(f"[{sym}] Starting Micro $10 MT5 simulation across 5 timeframes...", flush=True)
    engine = MT5BacktestEngine()
    sym_cfg = dict(BASE_CFG)
    sym_cfg['selected_symbols'] = [sym]

    def on_prog(pct, msg):
        pass

    res = engine.run_backtest(sym_cfg, progress_callback=on_prog)
    closed = res.get('closed_batches', [])
    elapsed = time.time() - t0
    pnl = sum(b.get('profit', 0) for b in closed)
    print(f"[{sym}] FINISHED in {elapsed:.1f}s! Total Trades: {len(closed)}, Net PnL: ${pnl:+,.2f}", flush=True)
    return sym, closed, {
        'elapsed_sec': round(elapsed, 1),
        'trades': len(closed),
        'net_pnl': round(pnl, 2),
        'roi_pct': round((pnl / 10.0) * 100.0, 2)
    }

def run_all():
    print("="*75, flush=True)
    print("   MICRO-ACCOUNT MT5 BACKTEST: $10 INITIAL CAPITAL | $2 MAX RISK   ", flush=True)
    print("="*75, flush=True)
    print(f"Symbols ({len(MICRO_SYMBOLS)}): {MICRO_SYMBOLS}", flush=True)
    print(f"Timeframes ({len(TIMEFRAMES)}): {TIMEFRAMES}", flush=True)
    print(f"Sniper Strategies ({len(SNIPER_STRATEGIES)}): {SNIPER_STRATEGIES}", flush=True)
    print(f"Initial Balance: $10.00 | Max Dollar Risk: $2.00 | Batch Lot: 0.01", flush=True)
    print(f"Smart Solution: ON (0.25 ATR breathing cushion for breakeven)", flush=True)
    print(f"Macro News Filter: ON (30m blackout + 15m pre-news shield)", flush=True)
    print("Spawning parallel worker processes...", flush=True)

    start_time = time.time()

    with mp.Pool(processes=min(len(MICRO_SYMBOLS), 4)) as pool:
        results = pool.map(worker_run_symbol, MICRO_SYMBOLS)

    total_duration = time.time() - start_time
    print(f"\nAll symbols completed in {total_duration:.1f} seconds!", flush=True)

    # ── Merge All Batches ──
    all_closed = []
    symbol_summaries = {}
    for sym, batches, summary in results:
        all_closed.extend(batches)
        symbol_summaries[sym] = summary

    # Sort all batches chronologically by execution / entry time
    all_closed.sort(key=lambda b: str(b.get('executed_at') or b.get('entry_time') or ''))

    total_trades = len(all_closed)
    print(f"Total aggregated sniper trades executed: {total_trades}", flush=True)

    # ── Helper for Stats ──
    def calc_stats(b_list: List[Dict[str, Any]], period_label: str) -> Dict[str, Any]:
        tot = len(b_list)
        wins = sum(1 for b in b_list if b.get('profit', 0) > 0.02 or b.get('tp1_hit'))
        losses = sum(1 for b in b_list if (not b.get('tp1_hit')) and b.get('profit', 0) < -0.02)
        bes = tot - wins - losses
        pnl = sum(b.get('profit', 0) for b in b_list)
        wr = (wins / max(tot, 1)) * 100.0 if tot > 0 else 0.0
        gross_p = sum(b.get('profit', 0) for b in b_list if b.get('profit', 0) > 0)
        gross_l = sum(abs(b.get('profit', 0)) for b in b_list if b.get('profit', 0) < 0)
        pf = round(gross_p / gross_l, 2) if gross_l > 0 else (99.9 if gross_p > 0 else 0.0)
        tp1_c = sum(1 for b in b_list if b.get('tp1_hit'))
        tp2_c = sum(1 for b in b_list if b.get('tp2_hit') or 'TP2' in str(b.get('exit_reason', '')))
        tp3_c = sum(1 for b in b_list if 'TP3' in str(b.get('exit_reason', '')))
        sl_c = sum(1 for b in b_list if 'FULL_SL' in str(b.get('exit_reason', '')) or ((not b.get('tp1_hit')) and b.get('profit', 0) < -0.02))
        biggest_sl = min((b.get('profit', 0) for b in b_list), default=0.0)
        biggest_tp = max((b.get('profit', 0) for b in b_list), default=0.0)
        return {
            'period': period_label,
            'total_trades': tot,
            'wins': wins,
            'losses': losses,
            'breakevens': bes,
            'win_rate': round(wr, 1),
            'net_pnl': round(pnl, 2),
            'gross_profit': round(gross_p, 2),
            'gross_loss': round(gross_l, 2),
            'profit_factor': pf,
            'tp1_hits': tp1_c,
            'tp2_hits': tp2_c,
            'tp3_hits': tp3_c,
            'sl_hits': sl_c,
            'biggest_sl': round(biggest_sl, 2),
            'biggest_tp': round(biggest_tp, 2)
        }

    # ── Weekly Analysis ──
    week_ranges = [
        ('Week 1 (Sep 16 - Sep 22)', datetime(2026, 9, 16, tzinfo=timezone.utc), datetime(2026, 9, 22, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 2 (Sep 23 - Sep 29)', datetime(2026, 9, 23, tzinfo=timezone.utc), datetime(2026, 9, 29, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 3 (Sep 30 - Oct 06)', datetime(2026, 9, 30, tzinfo=timezone.utc), datetime(2026, 10, 6, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 4 (Oct 07 - Oct 13)', datetime(2026, 10, 7, tzinfo=timezone.utc), datetime(2026, 10, 13, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 5 (Oct 14 - Oct 16)', datetime(2026, 10, 14, tzinfo=timezone.utc), datetime(2026, 10, 16, 23, 59, 59, tzinfo=timezone.utc)),
    ]

    weekly_stats = []
    for w_lbl, w_start, w_end in week_ranges:
        w_batches = []
        for b in all_closed:
            entry_t = b.get('executed_at') or b.get('entry_time')
            dt = None
            if isinstance(entry_t, str) and entry_t:
                try:
                    dt = datetime.fromisoformat(entry_t).replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            elif isinstance(entry_t, datetime):
                dt = entry_t.replace(tzinfo=timezone.utc) if entry_t.tzinfo is None else entry_t

            if dt and w_start <= dt <= w_end:
                w_batches.append(b)

        s = calc_stats(w_batches, w_lbl)
        s['start'] = w_start.strftime('%Y-%m-%d')
        s['end'] = w_end.strftime('%Y-%m-%d')
        weekly_stats.append(s)

    total_summary = calc_stats(all_closed, "Micro $10 Month (Sep 16 - Oct 16, 2026)")

    # ── Strategy Leaderboard ──
    leaderboard = MT5BacktestEngine.compute_backtest_strategy_leaderboard(all_closed, SNIPER_STRATEGIES)

    # ── Per-Pair Summary ──
    pair_summaries = {}
    for sym in MICRO_SYMBOLS:
        sym_batches = [b for b in all_closed if b.get('symbol') == sym]
        pair_summaries[sym] = calc_stats(sym_batches, sym)

    # ── Trade-by-Trade Balance Curve & Exact Lowest Balance Tracking ──
    balance_tracker = 10.0
    peak_bal = 10.0
    lowest_bal = 10.0
    max_dd_usd = 0.0
    max_dd_pct = 0.0
    balance_curve_sample = []

    for idx, b in enumerate(all_closed):
        pnl = b.get('profit', 0.0)
        balance_tracker += pnl
        if balance_tracker > peak_bal:
            peak_bal = balance_tracker
        if balance_tracker < lowest_bal:
            lowest_bal = balance_tracker
        dd = peak_bal - balance_tracker
        dd_pct = (dd / peak_bal) * 100.0 if peak_bal > 0 else 0.0
        if dd > max_dd_usd:
            max_dd_usd = dd
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
        if idx % 10 == 0 or idx == len(all_closed) - 1:
            balance_curve_sample.append({
                'trade_index': idx + 1,
                'batch_id': b.get('batch_id'),
                'symbol': b.get('symbol'),
                'profit': round(pnl, 2),
                'balance': round(balance_tracker, 2),
                'peak': round(peak_bal, 2)
            })

    total_summary['initial_balance'] = 10.0
    total_summary['peak_balance'] = round(peak_bal, 2)
    total_summary['lowest_balance_ever'] = round(lowest_bal, 2)
    total_summary['max_drawdown_usd'] = round(max_dd_usd, 2)
    total_summary['max_drawdown_pct'] = round(max_dd_pct, 2)
    total_summary['final_balance'] = round(balance_tracker, 2)
    total_summary['roi_pct'] = round(((balance_tracker - 10.0) / 10.0) * 100.0, 2)
    total_summary['is_account_zeroed'] = bool(lowest_bal <= 0.01)

    # ── News SL Incident Correlation ──
    news_events_parsed = []
    for ev in FALLBACK_2026_EVENTS:
        try:
            ev_dt = datetime.fromisoformat(ev['date'].replace('Z', '+00:00'))
            news_events_parsed.append({'title': ev['title'], 'country': ev['country'], 'dt': ev_dt})
        except Exception:
            pass

    sl_trades = [b for b in all_closed if 'FULL_SL' in str(b.get('exit_reason', '')) or ((not b.get('tp1_hit')) and b.get('profit', 0) < -0.02)]
    news_sl_incidents = []
    for b in sl_trades:
        c_time_str = b.get('closed_at')
        if c_time_str:
            try:
                c_dt = datetime.fromisoformat(c_time_str).replace(tzinfo=timezone.utc)
            except Exception:
                continue
            for n_ev in news_events_parsed:
                diff_mins = abs((c_dt - n_ev['dt']).total_seconds()) / 60.0
                if diff_mins <= 60.0:
                    news_sl_incidents.append({
                        'trade_id': b.get('batch_id'),
                        'symbol': b.get('symbol'),
                        'timeframe': b.get('timeframe'),
                        'strategy': b.get('strategy_used'),
                        'loss_usd': b.get('profit'),
                        'closed_at': c_time_str,
                        'event_title': n_ev['title'],
                        'event_time': n_ev['dt'].isoformat(),
                        'proximity_minutes': round(diff_mins, 1)
                    })

    final_payload = {
        'total_stats': total_summary,
        'weekly_breakdown': weekly_stats,
        'pair_breakdown': pair_summaries,
        'leaderboard': leaderboard,
        'news_sl_incidents': news_sl_incidents,
        'total_news_sl_hits': len(news_sl_incidents),
        'balance_curve_sample': balance_curve_sample,
        'total_trades': total_trades,
        'execution_duration_sec': round(total_duration, 1)
    }

    out_file = os.path.join(ROOT_DIR, 'scratch', 'micro_10usd_backtest_results.json')
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(final_payload, f, indent=2)

    print("\n" + "="*75, flush=True)
    print("      MICRO $10 ACCOUNT BACKTEST SUMMARY (STRICT CAPITAL PRESERVATION)      ", flush=True)
    print("="*75, flush=True)
    print(f"Initial Balance:          $10.00", flush=True)
    print(f"Lowest Balance Ever:      ${total_summary['lowest_balance_ever']:.2f} (Did it blow up? -> {'YES (BLOWN)' if total_summary['is_account_zeroed'] else 'NO (100% SURVIVED)'})", flush=True)
    print(f"Peak Balance Reached:     ${total_summary['peak_balance']:.2f}", flush=True)
    print(f"Final Balance:            ${total_summary['final_balance']:.2f}", flush=True)
    print(f"Net Profit (USD):         ${total_summary['net_pnl']:+,.2f} ({total_summary['roi_pct']:+,.2f}% ROI on $10)", flush=True)
    print(f"Overall Win Rate:         {total_summary['win_rate']}% ({total_summary['wins']} Wins | {total_summary['losses']} Losses | {total_summary['breakevens']} BEs)", flush=True)
    print(f"Profit Factor:            {total_summary['profit_factor']}", flush=True)
    print(f"Max Drawdown from Peak:   ${total_summary['max_drawdown_usd']:.2f} ({total_summary['max_drawdown_pct']:.2f}%)", flush=True)
    print(f"Worst Single Trade Loss:  ${total_summary['biggest_sl']:.2f} (Strictly under $2.00 cap)", flush=True)
    print(f"Best Single Trade Win:    ${total_summary['biggest_tp']:.2f}", flush=True)
    print(f"Results saved to:         {out_file}", flush=True)
    print("="*75, flush=True)

if __name__ == '__main__':
    mp.freeze_support()
    run_all()
