"""
Unified CLI for Real Crypto, Forex, and Futures Predictor
Supports both spot and perpetual futures market modes.
"""

import argparse, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.engine.orchestrator import PredictorOrchestrator

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    USE_RICH = True
    console = Console()
except ImportError:
    USE_RICH = False


def print_result_rich(res):
    meta  = res['metadata']
    mkt   = res['market_data']
    conf  = res['confluence']
    setup = res['trade_setup']
    ml    = res['ml_prediction']
    smc   = res['smc_analysis']
    arb   = res['arbitrage']
    ind   = res['indicators_summary']
    fut_d = res['futures_data']
    fut_s = res['futures_signals']

    action = conf['action']
    is_futures = meta['market_mode'] == 'futures'
    mode_tag   = "[PERP FUTURES]" if is_futures else "[SPOT]"

    # Header
    console.print()
    header = Text()
    header.append(f" {meta['symbol']} {mode_tag} ({meta['asset_type'].upper()}) ", style="bold white on blue")
    header.append(f"  Price: ${mkt['current_price']:,.4f}  |  {meta['exchange'].upper()}  |  TF: {meta['timeframe']}\n\n")
    action_style = "bold white on green" if "BUY" in action else ("bold white on red" if "SELL" in action else "bold black on yellow")
    header.append(f" {action} ", style=action_style)
    header.append(f"   Confluence: {conf['confluence_score']:+.1f}/100   Conviction: {conf['quality_index_pct']}%\n")
    console.print(Panel(header, title="[bold cyan]QUANT PREDICTION ENGINE -- SPOT + FUTURES[/bold cyan]", expand=False))

    # AlphaSniper Intelligence Panel
    alpha = res.get('alpha_sniper', {})
    if alpha:
        t_sniper = Table(title="[bold green]AlphaSniper(TM) Proprietary Conviction Filter[/bold green]", expand=False)
        t_sniper.add_column("Parameter", style="cyan")
        t_sniper.add_column("Value", style="bold white")
        t_sniper.add_column("Edge / Analysis", style="dim")
        t_sniper.add_row("Sniper Grade Tier", alpha.get('sniper_badge', 'N/A'), f"Confirmations: {alpha.get('active_confirmations', 0)}/{alpha.get('total_evaluated_layers', 0)} layers")
        t_sniper.add_row("Calibrated Win Probability", f"{alpha.get('calibrated_win_probability_pct', 50):.1f}%", "Bayesian posterior probability (Target: 80-97%)")
        t_sniper.add_row("Trade Expectancy", f"+{alpha.get('trade_expectancy_r', 0):.2f} R", "Mathematical expected edge per trade")
        t_sniper.add_row("AlphaRegime(TM)", alpha.get('alpha_regime', 'N/A'), "4-State Volatility & Memory Classifier")
        t_sniper.add_row("Kaufman Efficiency (KER)", str(alpha.get('kaufman_er', 0.3)), ">0.38 Strong Trend | <0.20 Noise")
        t_sniper.add_row("Chande Momentum (CMO)", f"{alpha.get('cmo_14', 0):+.1f}", ">+50 Bull Breakout | <-50 Bear Breakdown")
        t_sniper.add_row("Hurst Exponent (H)", str(alpha.get('hurst_exponent', 0.5)), "H>0.55 Trending | H<0.45 Mean-Reverting")
        t_sniper.add_row("Choppiness Index", str(alpha.get('choppiness_index', 50)), "<38.2 Trending | >61.8 Choppy consolidation")
        t_sniper.add_row("Institutional Absorption (IAI)", f"{alpha.get('iai_status', 'N/A')} ({alpha.get('iai_score', 0):+.0f})", "Iceberg order & delta wick absorption")
        t_sniper.add_row("Wyckoff Phase", alpha.get('wyckoff_phase', 'N/A'), "Accumulation / Distribution cycle")
        console.print(t_sniper)

    # Futures live metrics table
    if is_futures and fut_d:
        ticker_f = fut_d.get('ticker', {}) or {}
        fr_val   = (ticker_f.get('funding_rate', 0) or 0) * 100
        oi_val   = ticker_f.get('open_interest', 0) or 0
        basis    = fut_d.get('basis', {})
        ls_data  = fut_d.get('long_short_ratio', {})

        t_fut = Table(title="[bold magenta]Live Futures Derivatives Data[/bold magenta]", expand=False)
        t_fut.add_column("Metric", style="cyan")
        t_fut.add_column("Value", style="bold white")
        t_fut.add_column("Context", style="dim")

        t_fut.add_row("Mark Price", f"${ticker_f.get('mark_price', mkt['current_price']):,.4f}", "Perpetual mark")
        t_fut.add_row("Index Price", f"${ticker_f.get('index_price', mkt['current_price']):,.4f}", "Spot reference")
        t_fut.add_row("Current Funding Rate", f"{fr_val:+.5f}%", f"Annualized: {fr_val*3*365:+.1f}%")
        t_fut.add_row("Open Interest", f"{oi_val:,.0f}", "Total open contracts")
        t_fut.add_row("Spot-Futures Basis", f"{basis.get('basis_pct', 0):+.4f}%", basis.get('regime', ''))
        t_fut.add_row("Longs / Shorts", f"{ls_data.get('long_pct', 50):.1f}% / {ls_data.get('short_pct', 50):.1f}%", ls_data.get('bias', ''))

        console.print(t_fut)

        # Squeeze alert
        if fut_s:
            sq = fut_s.get('squeeze_analysis', {})
            sq_type = sq.get('squeeze_type', 'NONE')
            if 'SETUP' in sq_type:
                style = "bold green" if 'SHORT_SQUEEZE' in sq_type else "bold red"
                console.print(f"\n[{style}][!] SQUEEZE ALERT: {sq_type} DETECTED — {sq.get('reasons', [''])[0]}[/{style}]\n")

    # Confluence breakdown
    t_layers = Table(title=f"[bold yellow]{'9' if is_futures else '5'}-Layer Confluence Breakdown[/bold yellow]", expand=False)
    t_layers.add_column("Layer", style="cyan")
    t_layers.add_column("Score", justify="center")
    t_layers.add_column("Key Metrics", style="magenta")

    scores = conf['layer_scores']
    t_layers.add_row("1. Multi-Factor Trend",  str(scores['trend_momentum']),       f"SuperTrend: {ind['supertrend_dir']} | ADX: {ind['adx_14']}")
    t_layers.add_row("2. Smart Money (SMC)",   str(scores['smart_money_smc']),       f"Structure: {smc['structure']['structure']} | FVGs: {smc['open_fvgs_count']} | OBs: {smc['order_blocks_count']}")
    t_layers.add_row("3. Mean Reversion",       str(scores['mean_reversion_stat']),  f"RSI: {ind['rsi_14']} | Stoch: {ind['stoch_rsi_k']:.1f} | Squeeze: {ind['bb_squeeze']}")
    t_layers.add_row("4. Machine Learning",     str(scores['machine_learning']),     f"P(Long): {ml['p_bullish']*100:.1f}% | P(Short): {ml['p_bearish']*100:.1f}% | Conf: {ml['confidence_pct']}%")
    t_layers.add_row("5. Order Book Pressure",  str(scores['orderbook_pressure']),   f"Bias: {mkt['orderbook'].get('pressure_bias', 'N/A')}")

    if is_futures and fut_s:
        t_layers.add_row("F1. Funding Rate Regime",   str(scores.get('f1_funding_rate', 0)),      fut_s['funding_analysis']['regime'])
        t_layers.add_row("F2. Open Interest Flow",    str(scores.get('f2_open_interest', 0)),     fut_s['oi_analysis']['oi_flow'])
        t_layers.add_row("F3. Squeeze Detection",     str(scores.get('f3_squeeze_detection', 0)), fut_s['squeeze_analysis']['squeeze_type'])
        t_layers.add_row("F4. Basis Premium",         str(scores.get('f4_basis_premium', 0)),     fut_s['basis_analysis']['regime'])
        t_layers.add_row("F5. CVD Delta Flow",        str(scores.get('f5_cvd_delta_flow', 0)),    fut_s['cvd_analysis']['regime'])
        t_layers.add_row("F6. Institutional VWAP",    str(scores.get('f6_vwap_bands', 0)),        f"{fut_s['vwap_analysis']['status']} (${fut_s['vwap_analysis']['vwap']:,.2f})")
        t_layers.add_row("F7. Liquidation Magnet",    str(scores.get('f7_liquidation_magnets', 0)), f"Nearest: {fut_s['liq_analysis']['nearest_magnet']['type']} ({fut_s['liq_analysis']['dist_to_magnet_pct']:+.2f}%)")
        t_layers.add_row("F8. Scalp Micro Flow",      str(scores.get('f8_scalp_micro_flow', 0)),  fut_s['scalp_analysis']['scalp_setup'])
    console.print(t_layers)

    # Liquidation Clusters Table (Futures only)
    if is_futures and fut_s and fut_s.get('liq_analysis', {}).get('clusters'):
        t_liq = Table(title="[bold red]Institutional Liquidation Clusters (Heatmap Map)[/bold red]", expand=False)
        t_liq.add_column("Tier", style="cyan")
        t_liq.add_column("Type", style="bold white")
        t_liq.add_column("Price Level", justify="right", style="bold yellow")
        t_liq.add_column("Order Type", style="dim")
        for cl in fut_s['liq_analysis']['clusters'][:6]:
            t_liq.add_row(cl['leverage'], cl['type'], f"${cl['price']:,.2f}", cl['side'])
        console.print(t_liq)

    # Trade setup
    if setup['status'] == 'ACTIVE_SETUP':
        t_setup = Table(title="[bold green]Institutional Trade Setup[/bold green]", expand=False)
        t_setup.add_column("Parameter", style="cyan")
        t_setup.add_column("Value", style="bold white")
        t_setup.add_column("Notes", style="dim")
        t_setup.add_row("Action",             setup['action'],                        "Directional bias")
        t_setup.add_row("Entry",              f"${setup['recommended_entry']:,.4f}",  "Market / Limit zone")
        t_setup.add_row("Stop Loss",          f"${setup['stop_loss']:,.4f}",          f"-{setup['sl_distance_pct']}%")
        t_setup.add_row("Invalidation Mark",  f"${setup.get('invalidation_level', setup['stop_loss']):,.4f}", "Setup void if breached")
        t_setup.add_row("TP1 (1:1.5 R:R)",   f"${setup['tp1']:,.4f}",               f"+{setup['tp1_gain_pct']}%")
        t_setup.add_row("TP2 (1:2.5 R:R)",   f"${setup['tp2']:,.4f}",               f"+{setup['tp2_gain_pct']}%")
        t_setup.add_row("TP3 (1:4.0 Runner)", f"${setup['tp3']:,.4f}",              f"+{setup['tp3_gain_pct']}%")
        t_setup.add_row("Risk Capital",       f"${setup['risk_amount_usd']:,.2f}",    "Dollar risk per trade")
        t_setup.add_row("Expected PnL",       f"+${setup.get('expected_pnl_usd', 0):,.2f}", f"+{setup.get('expectancy_r', 0):.2f} R expectancy")
        t_setup.add_row("Position Size",      f"${setup['suggested_position_usd']:,.2f}", f"{setup['suggested_units']:.4f} units")
        t_setup.add_row("Half-Kelly",         f"{setup['half_kelly_pct']}% of portfolio", "Conservative allocation")
        console.print(t_setup)
    else:
        console.print("\n[yellow][!] No active trade setup — market neutral / consolidation.[/yellow]\n")

    # Multi-exchange prices
    if meta['asset_type'] == 'crypto':
        t_arb = Table(title="[bold blue]Multi-Exchange Live Prices[/bold blue]", expand=False)
        t_arb.add_column("Exchange", style="cyan"); t_arb.add_column("Price", justify="right"); t_arb.add_column("Status")
        for ex, info in mkt.get('multi_exchange_prices', {}).items():
            p = info.get('price')
            t_arb.add_row(ex.upper(), f"${p:,.2f}" if p else "N/A", info.get('status', 'N/A'))
        console.print(t_arb)
        if arb.get('arbitrage_available'):
            console.print(f"[bold green][ARBITRAGE] Buy {arb['cheapest_exchange'].upper()} (${arb['cheapest_price']:,.2f}) -> Sell {arb['highest_exchange'].upper()} (${arb['highest_price']:,.2f}) | Net: {arb['net_spread_pct']:.3f}%[/bold green]\n")

    # Signal checklist
    console.print("\n[bold]Signal Checklist:[/bold]")
    for r in conf['reasons']:
        if "(+" in r or "Bullish" in r:
            console.print(f"  [green][+] {r}[/green]")
        elif "(-" in r or "Bearish" in r or "LONG SQUEEZE" in r:
            console.print(f"  [red][-] {r}[/red]")
        else:
            console.print(f"  [dim][*] {r}[/dim]")
    console.print()


def main():
    parser = argparse.ArgumentParser(description="Quant Multi-Exchange Crypto & Forex Predictor")
    parser.add_argument('--symbol',       type=str,   default='BTC/USDT',  help='Symbol e.g. BTC/USDT, EUR/USD, XAU/USD')
    parser.add_argument('--asset-type',   type=str,   default='crypto',    choices=['crypto', 'forex'])
    parser.add_argument('--market-mode',  type=str,   default='spot',      choices=['spot', 'futures'])
    parser.add_argument('--timeframe',    type=str,   default='1h',        choices=['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d'])
    parser.add_argument('--exchange',     type=str,   default='binance')
    parser.add_argument('--balance',      type=float, default=10000.0)
    parser.add_argument('--risk',         type=float, default=1.5)
    parser.add_argument('--screen',       action='store_true', help='Screen top assets across spot and futures')
    parser.add_argument('--screen-mode',  type=str,   default='both',      choices=['spot', 'futures', 'both'])

    args = parser.parse_args()
    orchestrator = PredictorOrchestrator()

    if args.screen:
        print(f"\n[*] Screening top assets (mode: {args.screen_mode.upper()})...\n")
        targets = [
            ('BTC/USDT', 'crypto'), ('ETH/USDT', 'crypto'),
            ('SOL/USDT', 'crypto'), ('EUR/USD', 'forex'),
            ('GBP/USD', 'forex'),   ('XAU/USD', 'forex')
        ]
        modes = []
        if args.screen_mode in ('spot', 'both'):   modes.append('spot')
        if args.screen_mode in ('futures', 'both'): modes.append('futures')

        for mode in modes:
            print(f"\n{'='*70}")
            print(f"  MODE: {mode.upper()}")
            print(f"{'='*70}")
            for sym, atype in targets:
                if atype == 'forex' and mode == 'futures':
                    continue
                try:
                    res = orchestrator.run_prediction(
                        symbol=sym, asset_type=atype, market_mode=mode,
                        timeframe=args.timeframe, preferred_exchange=args.exchange,
                        account_size_usd=args.balance, risk_per_trade_pct=args.risk
                    )
                    action = res['confluence']['action']
                    score  = res['confluence']['confluence_score']
                    price  = res['market_data']['current_price']
                    fr_str = ""
                    if mode == 'futures' and res['futures_data']:
                        fr = (res['futures_data']['ticker'].get('funding_rate', 0) or 0) * 100
                        sq = res['futures_signals']['squeeze_analysis']['squeeze_type'] if res['futures_signals'] else 'NONE'
                        fr_str = f" | FR: {fr:+.4f}% | SQ: {sq}"
                    print(f"[{sym:<9}] {mode.upper():<7} | {action:<11} | Score: {score:>+5.1f} | ${price:<13,.4f}{fr_str}")
                except Exception as e:
                    print(f"[{sym:<9}] Error: {e}")
        print("\n[*] Screening complete.\n")
        return

    # Single prediction
    print(f"\nFetching live data for {args.symbol} [{args.market_mode.upper()}]...")
    res = orchestrator.run_prediction(
        symbol=args.symbol,
        asset_type=args.asset_type,
        market_mode=args.market_mode,
        timeframe=args.timeframe,
        preferred_exchange=args.exchange,
        account_size_usd=args.balance,
        risk_per_trade_pct=args.risk
    )
    if USE_RICH:
        print_result_rich(res)
    else:
        import pprint
        pprint.pprint(res['confluence'])
        pprint.pprint(res['trade_setup'])


if __name__ == '__main__':
    main()
