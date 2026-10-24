"""
Automated 6-to-12 Month Walk-Forward Analysis (WFA) CLI Stress Test Runner
==========================================================================
Usage:
    python run_walk_forward_stress_test.py [--months 6] [--is-days 60] [--oos-days 30]
"""

import os
import sys
import argparse
from datetime import datetime, timezone, timedelta

# Ensure root dir on sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.engine.walk_forward_engine import WalkForwardAnalysisEngine
from src.engine.backtest_engine import MT5BacktestEngine


def main():
    parser = argparse.ArgumentParser(description="Automated Institutional Walk-Forward Analysis Stress Test")
    parser.add_argument("--months", type=int, default=6, help="Total historical span in months (default: 6)")
    parser.add_argument("--is-days", type=int, default=60, help="In-sample training window in days (default: 60)")
    parser.add_argument("--oos-days", type=int, default=30, help="Out-of-sample forward test window in days (default: 30)")
    parser.add_argument("--step-days", type=int, default=30, help="Rolling step size in days (default: 30)")
    parser.add_argument("--symbols", nargs="+", default=["BTC/USD", "EUR/USD", "XAU/USD"], help="Symbols to backtest")
    args = parser.parse_args()

    print("=" * 80)
    print("   AUTOMATED INSTITUTIONAL WALK-FORWARD STRESS TEST (OUT-OF-SAMPLE AUDIT)   ")
    print("=" * 80)
    print(f"Historical Span: {args.months} months")
    print(f"Rolling Parameters: In-Sample: {args.is_days}d | Out-of-Sample: {args.oos_days}d | Step: {args.step_days}d")
    print(f"Symbols: {args.symbols}")
    print("=" * 80)

    now_dt = datetime.now(timezone.utc)
    start_dt = now_dt - timedelta(days=args.months * 30)

    engine = MT5BacktestEngine()
    settings = engine.load_settings()
    settings['selected_symbols'] = args.symbols
    settings['date_from'] = start_dt.isoformat()
    settings['date_to'] = now_dt.isoformat()

    wfa = WalkForwardAnalysisEngine(backtest_engine=engine)

    def on_prog(pct, msg):
        bar_len = 30
        filled = int(round(bar_len * pct))
        bar = '█' * filled + '░' * (bar_len - filled)
        print(f"\r[{bar}] {pct * 100:.1f}% - {msg[:60]:<60}", end='', flush=True)

    print("\nStarting Walk-Forward Execution across rolling windows...\n")
    results = wfa.run_walk_forward_analysis(
        base_settings=settings,
        is_days=args.is_days,
        oos_days=args.oos_days,
        step_days=args.step_days,
        progress_callback=on_prog
    )
    print("\n\n" + "=" * 80)
    print("   WALK-FORWARD ANALYSIS FORENSIC SCORECARD   ")
    print("=" * 80)
    print(f"Total Rolling Windows:            {results['total_windows']}")
    print(f"Profitable Out-of-Sample Windows: {results['profitable_oos_windows']} / {results['total_windows']} ({results['consistency_ratio_pct']}%)")
    print(f"Walk-Forward Efficiency (WFE):    {results['walk_forward_efficiency_pct']}%")
    print(f"Consolidated OOS Net Profit:      ${results['oos_net_profit']:+,.2f} ({results['oos_roi_pct']:+,.1f}% ROI)")
    print(f"Consolidated OOS Win Rate:        {results['oos_win_rate']}% (True-PnL)")
    print(f"Consolidated OOS Profit Factor:   {results['oos_profit_factor']}")
    print(f"Out-of-Sample Max Drawdown:       -${results['oos_max_drawdown_usd']:,.2f} ({results['oos_max_drawdown_pct']:.1f}%)")
    print(f"Robustness Verdict:               {results['robustness_verdict']}")
    print(f"Summary Description:              {results['verdict_description']}")
    print("=" * 80)

    print("\nWindow Breakdown:")
    for w in results['windows']:
        status_icon = "✅" if w['oos_profitable'] else "❌"
        print(f"  {status_icon} Window {w['window_index']:02d}: IS PnL: ${w['is_net_pnl']:+8.2f} (WR: {w['is_win_rate']:4.1f}%) | OOS PnL: ${w['oos_net_pnl']:+8.2f} (WR: {w['oos_win_rate']:4.1f}%, PF: {w['oos_profit_factor']:4.2f}) | WFE: {w['window_wfe_pct']:5.1f}%")
    print("=" * 80)


if __name__ == "__main__":
    main()
