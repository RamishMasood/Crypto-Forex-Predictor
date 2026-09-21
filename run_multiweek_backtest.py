import json
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from src.engine.backtest_engine import MT5BacktestEngine

def run_test(d_from: str, d_to: str, label: str):
    print(f"\n=======================================================")
    print(f"Running Test for {label}: {d_from} -> {d_to}")
    print(f"=======================================================")
    
    engine = MT5BacktestEngine()
    state = json.load(open('.backtest_engine_state.json'))
    cfg = state.get('settings_used', {})
    cfg['date_from'] = d_from
    cfg['date_to'] = d_to
    
    res = engine.run_backtest(cfg)
    
    net_pnl = res.get('net_profit', 0.0)
    win_rate = res.get('win_rate', 0.0)
    total_trades = res.get('total_trades', 0)
    
    print(f"Result [{label}]: Net Profit = ${net_pnl:.2f} | Win Rate = {win_rate:.1f}% | Total Trades = {total_trades}")
    
    trades = res.get('closed_batches', [])
    s_pnl = defaultdict(float)
    s_cnt = defaultdict(lambda: {'w': 0, 'l': 0, 'be': 0})
    
    for t in trades:
        s = t.get('strategy_used', 'UNKNOWN')
        p = t.get('profit', 0.0)
        st = t.get('status', '')
        s_pnl[s] += p
        if st == 'WIN':
            s_cnt[s]['w'] += 1
        elif st == 'LOSS':
            s_cnt[s]['l'] += 1
        else:
            s_cnt[s]['be'] += 1
            
    print(f"Strategy Performance ({len(s_pnl)} active strategies):")
    negative_count = 0
    for s, p in sorted(s_pnl.items(), key=lambda x: x[1]):
        c = s_cnt[s]
        status_flag = "LOSS" if p < 0 else "PROFIT"
        if p < 0:
            negative_count += 1
            # find which symbols / TFs caused the losses
            loss_details = [f"{t.get('symbol')} {t.get('timeframe')} (${t.get('profit', 0):.2f})" for t in trades if t.get('strategy_used') == s and t.get('profit', 0) < 0]
            print(f"  {s:22}: PnL = ${p:7.2f} [{status_flag:6}] | W:{c['w']:3} L:{c['l']:3} BE:{c['be']:3} | Losers: {', '.join(loss_details[:5])}")
        else:
            print(f"  {s:22}: PnL = ${p:7.2f} [{status_flag:6}] | W:{c['w']:3} L:{c['l']:3} BE:{c['be']:3}")
        
    print(f"Summary for {label}: Negative Strategies = {negative_count}")
    return res, s_pnl

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'week4'
    if mode == 'week1':
        run_test('2026-08-24', '2026-08-31', 'Week 1 (Aug 24 - Aug 31)')
    elif mode == 'week2':
        run_test('2026-08-31', '2026-09-07', 'Week 2 (Aug 31 - Sept 07)')
    elif mode == 'week3':
        run_test('2026-09-07', '2026-09-14', 'Week 3 (Sept 07 - Sept 14)')
    elif mode == 'week4':
        run_test('2026-09-14', '2026-09-21', 'Week 4 (Sept 14 - 21)')
    elif mode == 'month':
        run_test('2026-08-24', '2026-09-21', 'Full 1 Month (Aug 24 - Sept 21)')
    elif mode == 'all':
        run_test('2026-08-24', '2026-08-31', 'Week 1 (Aug 24 - Aug 31)')
        run_test('2026-08-31', '2026-09-07', 'Week 2 (Aug 31 - Sept 07)')
        run_test('2026-09-07', '2026-09-14', 'Week 3 (Sept 07 - Sept 14)')
        run_test('2026-09-14', '2026-09-21', 'Week 4 (Sept 14 - 21)')
        run_test('2026-08-24', '2026-09-21', 'Full 1 Month (Aug 24 - Sept 21)')
