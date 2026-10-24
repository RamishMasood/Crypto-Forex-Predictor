"""
Walk-Forward Analysis (WFA) & Out-of-Sample Stress Testing Engine
================================================================
Institutional-grade rolling out-of-sample stress testing module.
Prevents curve-fitting and statistical illusions by dividing historical
market data into sequential rolling In-Sample (IS) calibration windows
and Blind Out-of-Sample (OOS) evaluation windows.

Mathematical Metrics:
- Walk-Forward Efficiency (WFE) = (Annualized OOS Return / Annualized IS Return) * 100
- Out-of-Sample True-PnL Win Rate
- Out-of-Sample Profit Factor & Max Drawdown
- Consistency Ratio: % of Out-of-Sample periods that delivered positive Net PnL
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
import pandas as pd
import numpy as np

# Ensure root dir on sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.engine.backtest_engine import MT5BacktestEngine, get_backtest_engine

logger = logging.getLogger("WalkForwardEngine")


class WalkForwardAnalysisEngine:
    """
    Automated Walk-Forward Analysis and Out-of-Sample Stress Testing Engine.
    Executes sequential rolling windows to eliminate data-mining bias.
    """

    def __init__(self, backtest_engine: Optional[MT5BacktestEngine] = None):
        self.bt_engine = backtest_engine or get_backtest_engine()
        self._is_running = False
        self._stop_requested = False

    def stop(self):
        """Signals graceful stop."""
        self._stop_requested = True
        if self.bt_engine:
            self.bt_engine.stop()

    @staticmethod
    def generate_rolling_windows(
        date_from: datetime,
        date_to: datetime,
        is_days: int = 60,
        oos_days: int = 30,
        step_days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Generates sequential rolling In-Sample and Out-of-Sample window definitions.
        
        Example with 6 months (180 days), is_days=60, oos_days=30, step_days=30:
        Window 1: IS [Day 0 -> Day 60],  OOS [Day 60 -> Day 90]
        Window 2: IS [Day 30 -> Day 90], OOS [Day 90 -> Day 120]
        Window 3: IS [Day 60 -> Day 120], OOS [Day 120 -> Day 150]
        Window 4: IS [Day 90 -> Day 150], OOS [Day 150 -> Day 180]
        """
        windows = []
        total_span = (date_to - date_from).days
        min_required = is_days + oos_days

        if total_span < min_required:
            # Span too short for rolling steps; return single window
            adj_is = max(14, int(total_span * 0.65))
            is_end = date_from + timedelta(days=adj_is)
            windows.append({
                'window_index': 1,
                'label': f"Window 01 (IS: {date_from.strftime('%Y-%m-%d')} to {is_end.strftime('%Y-%m-%d')}, OOS: {is_end.strftime('%Y-%m-%d')} to {date_to.strftime('%Y-%m-%d')})",
                'is_from': date_from,
                'is_to': is_end,
                'oos_from': is_end,
                'oos_to': date_to,
                'is_days': adj_is,
                'oos_days': (date_to - is_end).days
            })
            return windows

        cur_start = date_from
        w_idx = 1

        while True:
            is_start = cur_start
            is_end = is_start + timedelta(days=is_days)
            oos_start = is_end
            oos_end = oos_start + timedelta(days=oos_days)

            if oos_end > date_to:
                # Adjust last window OOS to end at date_to
                oos_end = date_to
                if (oos_end - oos_start).days < 7:
                    break

            windows.append({
                'window_index': w_idx,
                'label': f"Window {w_idx:02d} (IS: {is_start.strftime('%b %d')} - {is_end.strftime('%b %d')}, OOS: {oos_start.strftime('%b %d')} - {oos_end.strftime('%b %d')})",
                'is_from': is_start,
                'is_to': is_end,
                'oos_from': oos_start,
                'oos_to': oos_end,
                'is_days': (is_end - is_start).days,
                'oos_days': (oos_end - oos_start).days
            })

            w_idx += 1
            cur_start = cur_start + timedelta(days=step_days)

            if (cur_start + timedelta(days=min_required)) > (date_to + timedelta(days=step_days // 2)):
                break

        return windows

    def run_walk_forward_analysis(
        self,
        base_settings: Optional[Dict[str, Any]] = None,
        is_days: int = 60,
        oos_days: int = 30,
        step_days: int = 30,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes complete rolling Walk-Forward Analysis across all generated windows.
        """
        self._is_running = True
        self._stop_requested = False
        cfg = dict(base_settings or self.bt_engine.load_settings())

        date_from_str = cfg.get('date_from')
        date_to_str = cfg.get('date_to')
        now_dt = datetime.now(timezone.utc)

        try:
            d_from = datetime.fromisoformat(date_from_str).replace(tzinfo=timezone.utc) if date_from_str else (now_dt - timedelta(days=180))
        except Exception:
            d_from = now_dt - timedelta(days=180)

        try:
            d_to = datetime.fromisoformat(date_to_str).replace(tzinfo=timezone.utc) if date_to_str else now_dt
        except Exception:
            d_to = now_dt

        # Generate rolling windows
        windows = self.generate_rolling_windows(d_from, d_to, is_days=is_days, oos_days=oos_days, step_days=step_days)
        total_windows = len(windows)
        logger.info(f"WalkForwardAnalysis: Generated {total_windows} rolling windows from {d_from.date()} to {d_to.date()}")

        if progress_callback:
            progress_callback(0.05, f"Generated {total_windows} Walk-Forward rolling windows...")

        window_results = []
        all_oos_batches: List[Dict[str, Any]] = []
        is_total_profit = 0.0
        is_total_trades = 0
        is_total_days = 0

        oos_total_profit = 0.0
        oos_total_trades = 0
        oos_total_days = 0

        initial_bal = float(cfg.get('initial_balance', 10000.0))

        for w_idx, win in enumerate(windows):
            if self._stop_requested:
                logger.info("WalkForwardAnalysis halted by user request.")
                break

            prog_base = 0.05 + (0.90 * (w_idx / max(total_windows, 1)))
            if progress_callback:
                progress_callback(prog_base, f"Evaluating Window {win['window_index']}/{total_windows}: In-Sample...")

            # 1. Run In-Sample Calibration
            is_cfg = dict(cfg)
            is_cfg['date_from'] = win['is_from'].isoformat()
            is_cfg['date_to'] = win['is_to'].isoformat()
            is_res = self.bt_engine.run_backtest(is_cfg)

            is_pnl = float(is_res.get('net_profit', 0.0))
            is_wr = float(is_res.get('win_rate', 0.0))
            is_trades = int(is_res.get('total_trades', 0))
            is_pf = float(is_res.get('profit_factor', 0.0))
            is_total_profit += is_pnl
            is_total_trades += is_trades
            is_total_days += win['is_days']

            if progress_callback:
                progress_callback(prog_base + (0.45 * (1.0 / max(total_windows, 1))), f"Evaluating Window {win['window_index']}/{total_windows}: Out-of-Sample Test...")

            # 2. Run Blind Out-of-Sample Forward Test
            oos_cfg = dict(cfg)
            oos_cfg['date_from'] = win['oos_from'].isoformat()
            oos_cfg['date_to'] = win['oos_to'].isoformat()
            oos_res = self.bt_engine.run_backtest(oos_cfg)

            oos_pnl = float(oos_res.get('net_profit', 0.0))
            oos_wr = float(oos_res.get('win_rate', 0.0))
            oos_trades = int(oos_res.get('total_trades', 0))
            oos_pf = float(oos_res.get('profit_factor', 0.0))
            oos_batches = oos_res.get('closed_batches', [])

            oos_total_profit += oos_pnl
            oos_total_trades += oos_trades
            oos_total_days += win['oos_days']

            for b in oos_batches:
                b_copy = dict(b)
                b_copy['oos_window'] = win['window_index']
                all_oos_batches.append(b_copy)

            # Local Window WFE
            is_ann = (is_pnl / max(win['is_days'], 1)) * 365.0
            oos_ann = (oos_pnl / max(win['oos_days'], 1)) * 365.0
            w_wfe = round((oos_ann / is_ann) * 100.0, 1) if abs(is_ann) > 1e-4 else 0.0

            window_results.append({
                'window_index': win['window_index'],
                'label': win['label'],
                'is_period': f"{win['is_from'].strftime('%Y-%m-%d')} to {win['is_to'].strftime('%Y-%m-%d')}",
                'is_trades': is_trades,
                'is_net_pnl': round(is_pnl, 2),
                'is_win_rate': is_wr,
                'is_profit_factor': is_pf,
                'oos_period': f"{win['oos_from'].strftime('%Y-%m-%d')} to {win['oos_to'].strftime('%Y-%m-%d')}",
                'oos_trades': oos_trades,
                'oos_net_pnl': round(oos_pnl, 2),
                'oos_win_rate': oos_wr,
                'oos_profit_factor': oos_pf,
                'window_wfe_pct': w_wfe,
                'oos_profitable': bool(oos_pnl > 0)
            })

        # 3. Compute Global Walk-Forward Statistics
        profitable_oos_wins = sum(1 for w in window_results if w['oos_profitable'])
        consistency_pct = round((profitable_oos_wins / max(len(window_results), 1)) * 100.0, 1)

        # Global Annualized Return comparison
        is_ann_global = (is_total_profit / max(is_total_days, 1)) * 365.0
        oos_ann_global = (oos_total_profit / max(oos_total_days, 1)) * 365.0
        global_wfe = round((oos_ann_global / is_ann_global) * 100.0, 1) if abs(is_ann_global) > 1e-4 else 0.0

        # Global True-PnL Out-of-Sample metrics
        all_oos_batches.sort(key=lambda x: str(x.get('executed_at') or x.get('entry_time') or ''))
        gross_oos_profit = sum(float(b.get('profit', 0.0)) for b in all_oos_batches if float(b.get('profit', 0.0)) > 0)
        gross_oos_loss = sum(abs(float(b.get('profit', 0.0))) for b in all_oos_batches if float(b.get('profit', 0.0)) < 0)
        consolidated_pf = round(gross_oos_profit / max(gross_oos_loss, 1e-5), 2) if gross_oos_loss > 0 else (99.0 if gross_oos_profit > 0 else 0.0)

        oos_winning_trades = sum(1 for b in all_oos_batches if float(b.get('profit', 0.0)) > 0.05)
        oos_win_rate = round((oos_winning_trades / max(len(all_oos_batches), 1)) * 100.0, 1)

        # OOS Max Drawdown
        running_bal = initial_bal
        peak_bal = initial_bal
        max_dd_usd = 0.0
        max_dd_pct = 0.0
        oos_equity_curve = [("Start", initial_bal)]

        for b in all_oos_batches:
            p = float(b.get('profit', 0.0))
            running_bal += p
            if running_bal > peak_bal:
                peak_bal = running_bal
            dd = peak_bal - running_bal
            dd_pct = (dd / peak_bal) * 100.0 if peak_bal > 0 else 0.0
            if dd > max_dd_usd:
                max_dd_usd = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
            c_time = b.get('closed_at') or b.get('executed_at') or 'N/A'
            oos_equity_curve.append((str(c_time), round(running_bal, 2)))

        # Robustness Classification
        if global_wfe >= 60.0 and consistency_pct >= 66.0 and consolidated_pf >= 1.20:
            robustness_verdict = "INSTITUTIONALLY_ROBUST"
            verdict_desc = "Strategy edge persists robustly across unseen out-of-sample data with positive expectancy and minimal curve-fitting."
        elif global_wfe >= 35.0 and consistency_pct >= 50.0 and oos_total_profit > 0:
            robustness_verdict = "MODERATELY_ROBUST"
            verdict_desc = "Strategy shows genuine positive edge but demonstrates moderate regime sensitivity during consolidation phases."
        else:
            robustness_verdict = "OVERFITTED_HIGH_RISK"
            verdict_desc = "CRITICAL WARNING: Strategy is heavily curve-fitted or has negative expectancy. Live execution will likely suffer account drawdown."

        summary = {
            'total_windows': len(window_results),
            'profitable_oos_windows': profitable_oos_wins,
            'consistency_ratio_pct': consistency_pct,
            'is_total_trades': is_total_trades,
            'is_net_pnl': round(is_total_profit, 2),
            'oos_total_trades': len(all_oos_batches),
            'oos_net_profit': round(oos_total_profit, 2),
            'oos_roi_pct': round((oos_total_profit / initial_bal) * 100.0, 2),
            'oos_win_rate': oos_win_rate,
            'oos_profit_factor': consolidated_pf,
            'oos_max_drawdown_usd': round(max_dd_usd, 2),
            'oos_max_drawdown_pct': round(max_dd_pct, 2),
            'walk_forward_efficiency_pct': global_wfe,
            'robustness_verdict': robustness_verdict,
            'verdict_description': verdict_desc,
            'windows': window_results,
            'oos_closed_batches': all_oos_batches,
            'oos_equity_curve': oos_equity_curve
        }

        self._is_running = False
        if progress_callback:
            progress_callback(1.0, f"Walk-Forward Analysis complete. Verdict: {robustness_verdict} (WFE: {global_wfe}%)")

        return summary
