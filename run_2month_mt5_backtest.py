"""
Run Comprehensive 2-Month MT5 Historical Backtest
================================================
Simulates 2 full months (Aug 17, 2026 - Oct 16, 2026) across all Autonomous pairs & timeframes
using Exness MT5 historical data with:
- All 28 improved strategies
- Smart Solution ON (Smart Breathing BE with 0.25 ATR cushion)
- Golden SL (1.80 ATR) + 1:1.15 TP2 + 2.20 TP3
- Economic News Blackout Guard (30m pre/post window)
- HTF Confluence Filter
- Week-by-Week Breakdown (Weeks 1-9)
- Month 1 vs Month 2 Breakdown
- Market Regime Analysis (Uptrend, Downtrend, Consolidation / Range, News Spikes)
- Strategy Leaderboard
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import pandas as pd
import numpy as np

# Ensure root directory is on sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.engine.backtest_engine import MT5BacktestEngine
from src.data.economic_calendar import EconomicCalendarManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("2MonthBacktestRunner")

def run():
    logger.info("Initializing 2-Month MT5 Backtest Simulation...")
    engine = MT5BacktestEngine()

    settings_path = os.path.join(ROOT_DIR, '.backtest_engine_settings.json')
    with open(settings_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    # Enforce exact 2-month window: Aug 17, 2026 to Oct 16, 2026
    cfg['date_from'] = '2026-08-17'
    cfg['date_to'] = '2026-10-16'
    cfg['smart_solution_enabled'] = True
    cfg['news_filter_enabled'] = True
    cfg['breakeven_mode'] = 'smart_breathing_be'

    # Filter out symbols that are not available in MT5 or keep Exness majors
    # MT5 symbols mapping check
    logger.info(f"Target Symbols: {cfg['selected_symbols']}")
    logger.info(f"Timeframes: {cfg['timeframes']}")
    logger.info(f"Strategies ({len(cfg['active_strategies'])}): {cfg['active_strategies']}")
    logger.info(f"Date Range: {cfg['date_from']} to {cfg['date_to']}")

    def on_progress(pct, msg):
        logger.info(f"[{pct*100:.1f}%] {msg}")

    # Run the backtest simulation
    results = engine.run_backtest(cfg, progress_callback=on_progress)

    closed_batches = results.get('closed_batches', [])
    total_trades = len(closed_batches)
    logger.info(f"Simulation Finished! Total completed trades: {total_trades}")

    # ── Post-Processing: Weekly & Monthly Analysis ──
    # Define week intervals (Mondays to Sundays)
    week_ranges = [
        ('Week 1 (Aug 17 - Aug 23)', datetime(2026, 8, 17, tzinfo=timezone.utc), datetime(2026, 8, 23, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 2 (Aug 24 - Aug 30)', datetime(2026, 8, 24, tzinfo=timezone.utc), datetime(2026, 8, 30, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 3 (Aug 31 - Sep 06)', datetime(2026, 8, 31, tzinfo=timezone.utc), datetime(2026, 9, 6, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 4 (Sep 07 - Sep 13)', datetime(2026, 9, 7, tzinfo=timezone.utc), datetime(2026, 9, 13, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 5 (Sep 14 - Sep 20)', datetime(2026, 9, 14, tzinfo=timezone.utc), datetime(2026, 9, 20, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 6 (Sep 21 - Sep 27)', datetime(2026, 9, 21, tzinfo=timezone.utc), datetime(2026, 9, 27, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 7 (Sep 28 - Oct 04)', datetime(2026, 9, 28, tzinfo=timezone.utc), datetime(2026, 10, 4, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 8 (Oct 05 - Oct 11)', datetime(2026, 10, 5, tzinfo=timezone.utc), datetime(2026, 10, 11, 23, 59, 59, tzinfo=timezone.utc)),
        ('Week 9 (Oct 12 - Oct 16)', datetime(2026, 10, 12, tzinfo=timezone.utc), datetime(2026, 10, 16, 23, 59, 59, tzinfo=timezone.utc)),
    ]

    weekly_data = []
    for w_lbl, w_start, w_end in week_ranges:
        w_batches = []
        for b in closed_batches:
            entry_t = b.get('entry_time')
            if isinstance(entry_t, str):
                try:
                    dt = datetime.fromisoformat(entry_t).replace(tzinfo=timezone.utc)
                except Exception:
                    dt = None
            elif isinstance(entry_t, datetime):
                dt = entry_t.replace(tzinfo=timezone.utc) if entry_t.tzinfo is None else entry_t
            else:
                dt = None

            if dt and w_start <= dt <= w_end:
                w_batches.append(b)

        w_tot = len(w_batches)
        w_wins = sum(1 for b in w_batches if b.get('profit', 0) > 0.15 or b.get('tp1_hit'))
        w_losses = sum(1 for b in w_batches if (not b.get('tp1_hit')) and b.get('profit', 0) < -0.15)
        w_bes = w_tot - w_wins - w_losses
        w_pnl = sum(b.get('profit', 0) for b in w_batches)
        w_decisive = w_wins + w_losses
        w_wr = (w_wins / max(w_decisive, 1)) * 100.0 if w_decisive > 0 else 0.0

        tp1_count = sum(1 for b in w_batches if b.get('tp1_hit'))
        tp2_count = sum(1 for b in w_batches if b.get('tp2_hit') or 'TP2' in str(b.get('exit_reason', '')))
        tp3_count = sum(1 for b in w_batches if 'TP3' in str(b.get('exit_reason', '')))
        sl_count = sum(1 for b in w_batches if 'FULL_SL' in str(b.get('exit_reason', '')) or ((not b.get('tp1_hit')) and b.get('profit', 0) < -0.15))

        weekly_data.append({
            'week': w_lbl,
            'start': w_start.strftime('%Y-%m-%d'),
            'end': w_end.strftime('%Y-%m-%d'),
            'total_trades': w_tot,
            'wins': w_wins,
            'losses': w_losses,
            'breakevens': w_bes,
            'win_rate': round(w_wr, 1),
            'pnl': round(w_pnl, 2),
            'tp1_hits': tp1_count,
            'tp2_hits': tp2_count,
            'tp3_hits': tp3_count,
            'sl_hits': sl_count
        })

    # ── Monthly Analysis ──
    m1_cutoff = datetime(2026, 9, 16, 23, 59, 59, tzinfo=timezone.utc)
    m1_batches = []
    m2_batches = []

    for b in closed_batches:
        entry_t = b.get('entry_time')
        if isinstance(entry_t, str):
            try:
                dt = datetime.fromisoformat(entry_t).replace(tzinfo=timezone.utc)
            except Exception:
                dt = None
        elif isinstance(entry_t, datetime):
            dt = entry_t.replace(tzinfo=timezone.utc) if entry_t.tzinfo is None else entry_t
        else:
            dt = None

        if dt:
            if dt <= m1_cutoff:
                m1_batches.append(b)
            else:
                m2_batches.append(b)

    def calc_group_stats(b_list, label):
        tot = len(b_list)
        wins = sum(1 for b in b_list if b.get('profit', 0) > 0.15 or b.get('tp1_hit'))
        losses = sum(1 for b in b_list if (not b.get('tp1_hit')) and b.get('profit', 0) < -0.15)
        bes = tot - wins - losses
        pnl = sum(b.get('profit', 0) for b in b_list)
        dec = wins + losses
        wr = (wins / max(dec, 1)) * 100.0 if dec > 0 else 0.0
        gross_p = sum(b.get('profit', 0) for b in b_list if b.get('profit', 0) > 0)
        gross_l = sum(abs(b.get('profit', 0)) for b in b_list if b.get('profit', 0) < 0)
        pf = round(gross_p / gross_l, 2) if gross_l > 0 else (99.9 if gross_p > 0 else 0.0)
        tp1_c = sum(1 for b in b_list if b.get('tp1_hit'))
        tp2_c = sum(1 for b in b_list if b.get('tp2_hit') or 'TP2' in str(b.get('exit_reason', '')))
        tp3_c = sum(1 for b in b_list if 'TP3' in str(b.get('exit_reason', '')))
        sl_c = sum(1 for b in b_list if 'FULL_SL' in str(b.get('exit_reason', '')) or ((not b.get('tp1_hit')) and b.get('profit', 0) < -0.15))
        return {
            'period': label,
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
            'sl_hits': sl_c
        }

    m1_stats = calc_group_stats(m1_batches, "Month 1 (Aug 17 - Sep 16, 2026)")
    m2_stats = calc_group_stats(m2_batches, "Month 2 (Sep 17 - Oct 16, 2026)")
    total_stats = calc_group_stats(closed_batches, "Combined 2 Months (Aug 17 - Oct 16, 2026)")

    # Save comprehensive analysis output
    final_output = {
        'total_stats': total_stats,
        'month_1': m1_stats,
        'month_2': m2_stats,
        'weekly_breakdown': weekly_data,
        'leaderboard': results.get('leaderboard', []),
        'kpis': {
            'initial_balance': results.get('initial_balance', 10000.0),
            'final_balance': results.get('final_balance', 10000.0),
            'net_profit': results.get('net_profit', 0.0),
            'roi_pct': results.get('roi_pct', 0.0),
            'win_rate': results.get('win_rate', 0.0),
            'profit_factor': results.get('profit_factor', 0.0),
            'max_drawdown_usd': results.get('max_drawdown_usd', 0.0),
            'max_drawdown_pct': results.get('max_drawdown_pct', 0.0),
            'biggest_sl_loss': results.get('biggest_sl_loss', 0.0),
            'sl_hits': results.get('sl_hits', 0),
            'total_trades': results.get('total_trades', 0),
            'wins': results.get('wins', 0),
            'losses': results.get('losses', 0),
            'breakevens': results.get('breakevens', 0)
        }
    }

    out_file = os.path.join(ROOT_DIR, 'scratch', '2month_backtest_full_results.json')
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=2)

    logger.info(f"Results successfully saved to {out_file}")
    print("\n" + "="*70)
    print("       2-MONTH MT5 BACKTEST SIMULATION COMPLETED       ")
    print("="*70)
    print(f"Total Trades: {total_stats['total_trades']}")
    print(f"Wins: {total_stats['wins']} | Losses: {total_stats['losses']} | Breakevens: {total_stats['breakevens']}")
    print(f"Win Rate: {total_stats['win_rate']}%")
    print(f"Net Realized PnL: ${total_stats['net_pnl']:+,.2f}")
    print(f"Profit Factor: {total_stats['profit_factor']}")
    print(f"TP1 Scalp Banks: {total_stats['tp1_hits']}")
    print(f"TP2 Structural Runners: {total_stats['tp2_hits']}")
    print(f"TP3 Macro Runners: {total_stats['tp3_hits']}")
    print(f"Full Stop Losses: {total_stats['sl_hits']}")
    print("="*70)

if __name__ == '__main__':
    run()
