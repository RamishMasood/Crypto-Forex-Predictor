"""
Interactive Streamlit Terminal for Multi-Exchange Crypto & Forex Predictor
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

from src.engine.orchestrator import PredictorOrchestrator
from src.data.forex_feeds import FOREX_PAIRS_MAP

st.set_page_config(
    page_title="Crypto & Forex Quant Predictor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Dark Theme Styling
st.markdown("""
<style>
    .reportview-container {
        background: #0e1117;
    }
    .metric-card {
        background-color: #1a1e29;
        border-radius: 10px;
        padding: 16px;
        border: 1px solid #2d3139;
        margin-bottom: 12px;
    }
    .buy-badge {
        background-color: #00c853;
        color: #ffffff;
        padding: 6px 14px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 1.1rem;
    }
    .sell-badge {
        background-color: #d50000;
        color: #ffffff;
        padding: 6px 14px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 1.1rem;
    }
    .neutral-badge {
        background-color: #ffd600;
        color: #111111;
        padding: 6px 14px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_orchestrator():
    return PredictorOrchestrator()

orchestrator = get_orchestrator()

# --- SIDEBAR CONTROLS ---
st.sidebar.title("⚡ Quant Signal Terminal")
st.sidebar.markdown("**Institutional Multi-Exchange Engine**")

asset_type = st.sidebar.radio("Asset Class", ["Cryptocurrency", "Forex & Commodities"])

if asset_type == "Cryptocurrency":
    crypto_presets = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "NEAR/USDT"]
    symbol = st.sidebar.selectbox("Symbol", crypto_presets, index=0)
    custom_symbol = st.sidebar.text_input("Or Custom Pair (e.g. SUI/USDT):", "")
    if custom_symbol.strip():
        symbol = custom_symbol.strip().upper()
    preferred_exchange = st.sidebar.selectbox("Primary Exchange", ["binance", "bybit", "coinbase", "kucoin", "gateio"], index=0)
    asset_type_code = 'crypto'
else:
    forex_presets = list(FOREX_PAIRS_MAP.keys())
    symbol = st.sidebar.selectbox("Pair / Asset", forex_presets, index=0)
    custom_symbol = st.sidebar.text_input("Or Custom Ticker (e.g. EURUSD=X):", "")
    if custom_symbol.strip():
        symbol = custom_symbol.strip()
    preferred_exchange = 'interbank'
    asset_type_code = 'forex'

timeframe = st.sidebar.selectbox("Timeframe", ["5m", "15m", "30m", "1h", "4h", "1d"], index=3)

st.sidebar.markdown("---")
st.sidebar.subheader("💼 Risk & Portfolio Sizing")
account_size = st.sidebar.number_input("Account Balance (USD)", min_value=100.0, value=10000.0, step=500.0)
risk_pct = st.sidebar.slider("Risk Per Trade (%)", min_value=0.25, max_value=5.0, value=1.5, step=0.25)

run_btn = st.sidebar.button("🚀 Analyze & Predict Live", type="primary", use_container_width=True)

# --- MAIN EXECUTION ---
with st.spinner(f"Querying live public APIs for {symbol} on {timeframe}..."):
    try:
        res = orchestrator.run_prediction(
            symbol=symbol,
            asset_type=asset_type_code,
            timeframe=timeframe,
            preferred_exchange=preferred_exchange,
            account_size_usd=account_size,
            risk_per_trade_pct=risk_pct
        )
        success = True
    except Exception as e:
        st.error(f"Error fetching live data: {e}")
        success = False

if success:
    meta = res['metadata']
    mkt = res['market_data']
    conf = res['confluence']
    setup = res['trade_setup']
    ml = res['ml_prediction']
    smc = res['smc_analysis']
    arb = res['arbitrage']
    ind = res['indicators_summary']
    df_chart = res['df_chart']

    curr_p = mkt['current_price']
    action = conf['action']
    badge_class = "buy-badge" if "BUY" in action else ("sell-badge" if "SELL" in action else "neutral-badge")

    # Header Row
    col_hdr1, col_hdr2, col_hdr3, col_hdr4 = st.columns([3, 2, 2, 3])
    with col_hdr1:
        st.title(f"{symbol}")
        st.caption(f"Timeframe: {timeframe} | Feed: {meta['exchange'].upper()} | {meta['timestamp'][:19]}")
    with col_hdr2:
        st.metric("Live Market Price", f"${curr_p:,.4f}" if curr_p > 1 else f"${curr_p:,.6f}")
    with col_hdr3:
        chg = mkt['ticker'].get('change_24h_pct', 0.0) if mkt['ticker'] else 0.0
        st.metric("24h Change", f"{chg:+.2f}%", delta=f"{chg:+.2f}%")
    with col_hdr4:
        st.markdown(f"<div style='text-align: right; padding-top: 15px;'><span class='{badge_class}'>{action}</span></div>", unsafe_allow_html=True)
        st.markdown(f"<div style='text-align: right; font-size: 0.9rem; color: #aaa; margin-top: 6px;'>Confluence Score: <b>{conf['confluence_score']} / 100</b></div>", unsafe_allow_html=True)

    # Active Sessions if Forex
    if mkt.get('forex_sessions'):
        sess = mkt['forex_sessions']
        active_str = ", ".join(sess['active_sessions']) if sess['active_sessions'] else "Market Closed / Quiet"
        overlap_txt = "🔥 Major London-NY Overlap (Peak Liquidity)" if sess['is_major_overlap'] else ""
        st.info(f"🌐 **Forex Sessions Active:** {active_str} {overlap_txt}")

    st.markdown("---")

    # 3-Column Key Summary Dashboard
    c1, c2, c3 = st.columns([1, 1, 1])

    with c1:
        st.markdown("### 🎯 Confluence Verdict")
        st.write(f"**Action:** `{action}`")
        st.write(f"**Market Sentiment:** `{conf['sentiment']}`")
        st.write(f"**Quality / Conviction Index:** `{conf['quality_index_pct']}%`")
        
        # Progress indicator for score
        score_norm = (conf['confluence_score'] + 100.0) / 200.0
        st.progress(float(score_norm), text=f"Bearish ◀ Score: {conf['confluence_score']} ▶ Bullish")

    with c2:
        st.markdown("### 🤖 Machine Learning Model")
        st.write(f"**Predicted Direction:** `{ml['predicted_direction']}`")
        st.write(f"**P(Bullish):** `{ml['p_bullish']*100:.1f}%` | **P(Bearish):** `{ml['p_bearish']*100:.1f}%`")
        st.write(f"**Confidence:** `{ml['confidence_pct']}%` | **CV Accuracy:** `{ml['cv_accuracy_pct']}%`")
        st.write(f"**Expected Price Move:** `{ml['expected_return_pct']:+.2f}%`")

    with c3:
        st.markdown("### 🏛️ Smart Money Concepts")
        st.write(f"**Market Structure:** `{smc['structure']['structure']}`")
        st.write(f"**Liquidity Sweep:** `{smc['structure']['liquidity_sweep']}`")
        st.write(f"**Active Unmitigated FVGs:** `{smc['open_fvgs_count']}`")
        st.write(f"**Key Order Blocks (OB):** `{smc['order_blocks_count']}`")

    # Chart Section
    st.markdown("---")
    st.subheader(f"📊 Quantitative Chart ({timeframe}) with SMC Zones & Indicators")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7), gridspec_kw={'height_ratios': [3, 1]}, facecolor='#0e1117')
    ax1.set_facecolor('#131722')
    ax2.set_facecolor('#131722')

    n_show = min(75, len(df_chart))
    plot_df = df_chart.iloc[-n_show:].reset_index(drop=True)
    x_indices = np.arange(len(plot_df))

    # Plot Candlesticks
    for idx, row in plot_df.iterrows():
        color = '#00c853' if row['close'] >= row['open'] else '#d50000'
        # Wick
        ax1.plot([idx, idx], [row['low'], row['high']], color=color, linewidth=1.2)
        # Body
        body_bottom = min(row['open'], row['close'])
        body_height = max(abs(row['close'] - row['open']), (row['high'] - row['low']) * 0.05)
        ax1.add_patch(plt.Rectangle((idx - 0.35, body_bottom), 0.7, body_height, color=color, alpha=0.9))

    # Plot EMAs
    ax1.plot(x_indices, plot_df['ema_20'], color='#29b6f6', label='EMA 20', linewidth=1.3)
    ax1.plot(x_indices, plot_df['ema_50'], color='#ab47bc', label='EMA 50', linewidth=1.3)
    if 'ema_200' in plot_df.columns:
        ax1.plot(x_indices, plot_df['ema_200'], color='#ffa726', label='EMA 200', linewidth=1.5, linestyle='--')

    # Plot Supertrend
    if 'supertrend' in plot_df.columns:
        st_colors = ['#00e676' if d == 1 else '#ff1744' for d in plot_df['supertrend_dir']]
        ax1.scatter(x_indices, plot_df['supertrend'], c=st_colors, s=12, label='SuperTrend', zorder=4)

    # Highlight SMC Fair Value Gaps (FVG)
    for fvg in smc.get('active_fvgs', []):
        fvg_color = '#00e676' if fvg['type'] == 'BULLISH_FVG' else '#ff1744'
        ax1.axhspan(fvg['bottom'], fvg['top'], color=fvg_color, alpha=0.15, label='Active FVG' if fvg == smc['active_fvgs'][0] else "")

    ax1.set_ylabel("Price (USD)", color='#d1d4dc')
    ax1.tick_params(colors='#d1d4dc')
    ax1.grid(True, color='#2a2e39', linestyle=':', alpha=0.6)
    ax1.legend(loc='upper left', facecolor='#1e222d', edgecolor='#363a45', labelcolor='#d1d4dc', fontsize=9)

    # Plot RSI on lower subpanel
    ax2.plot(x_indices, plot_df['rsi_14'], color='#ba68c8', label='RSI 14', linewidth=1.5)
    ax2.axhline(70, color='#ef5350', linestyle='--', alpha=0.7)
    ax2.axhline(30, color='#66bb6a', linestyle='--', alpha=0.7)
    ax2.set_ylim(10, 90)
    ax2.set_ylabel("RSI (14)", color='#d1d4dc')
    ax2.tick_params(colors='#d1d4dc')
    ax2.grid(True, color='#2a2e39', linestyle=':', alpha=0.6)

    # Set sample date labels
    step = max(1, len(plot_df) // 8)
    ticks = x_indices[::step]
    labels = [pd.to_datetime(plot_df['timestamp'].iloc[i]).strftime('%m/%d %H:%M') for i in ticks]
    ax2.set_xticks(ticks)
    ax2.set_xticklabels(labels, rotation=25, color='#d1d4dc', fontsize=8)

    plt.tight_layout()
    st.pyplot(fig)

    # Trade Setup Section
    st.markdown("---")
    st.subheader("🛡️ Institutional Trade Setup & Risk Management")

    if setup['status'] == 'ACTIVE_SETUP':
        s_col1, s_col2, s_col3, s_col4 = st.columns(4)
        with s_col1:
            st.metric("Recommended Entry", f"${setup['recommended_entry']:,.4f}")
            st.metric("Position Units", f"{setup['suggested_units']:.4f}")
        with s_col2:
            st.metric("Stop Loss (SL)", f"${setup['stop_loss']:,.4f}", delta=f"-{setup['sl_distance_pct']}%", delta_color="inverse")
            st.metric("Risk Capital (USD)", f"${setup['risk_amount_usd']:,.2f} ({risk_pct}%)")
        with s_col3:
            st.metric("Target TP1 (1:1.5 R:R)", f"${setup['tp1']:,.4f}", delta=f"+{setup['tp1_gain_pct']}%")
            st.metric("Target TP2 (1:2.5 R:R)", f"${setup['tp2']:,.4f}", delta=f"+{setup['tp2_gain_pct']}%")
        with s_col4:
            st.metric("Target TP3 (1:4.0 Runner)", f"${setup['tp3']:,.4f}", delta=f"+{setup['tp3_gain_pct']}%")
            st.metric("Half-Kelly Allocation", f"{setup['half_kelly_pct']}% of portfolio")
    else:
        st.info("No directional trade triggered (Market in consolidation / neutral regime). Capital preservation recommended.")

    # Confluence Reasons and Multi-Exchange Arbitrage
    col_reasons, col_arb = st.columns([1, 1])

    with col_reasons:
        st.markdown("### 📋 Confluence Scoring Breakdown")
        for r in conf['reasons']:
            if "(+" in r or "Bullish" in r:
                st.markdown(f"- 🟢 {r}")
            elif "(-" in r or "Bearish" in r:
                st.markdown(f"- 🔴 {r}")
            else:
                st.markdown(f"- ⚪ {r}")

    with col_arb:
        if asset_type_code == 'crypto':
            st.markdown("### 🌐 Multi-Exchange Price & Arbitrage")
            ex_data = mkt.get('multi_exchange_prices', {})
            ex_rows = []
            for ex, val in ex_data.items():
                p = val.get('price')
                p_str = f"${p:,.2f}" if p else "N/A"
                ex_rows.append({'Exchange': ex.upper(), 'Price': p_str, 'Status': val.get('status')})
            st.dataframe(pd.DataFrame(ex_rows), use_container_width=True)

            if arb.get('arbitrage_available'):
                st.success(f"🚀 Arbitrage Opportunity: Buy {arb['cheapest_exchange'].upper()} @ ${arb['cheapest_price']} -> Sell {arb['highest_exchange'].upper()} @ ${arb['highest_price']} (Net Spread: {arb['net_spread_pct']:.2f}%)")
            else:
                st.caption("Spread between exchanges is within normal tight market-making ranges.")
        else:
            st.markdown("### 🌐 Interbank Forex Liquidity")
            st.write("Quotes sourced from official ECB reference benchmarks and interbank aggregators.")
            st.write(f"Pair: `{symbol}` | Yahoo Ticker: `{meta['symbol']}`")
            st.write(f"High: `{mkt['ticker'].get('high')}` | Low: `{mkt['ticker'].get('low')}`")

st.markdown("---")
st.caption("Quantitative Multi-Exchange Predictor | Real-Time Public APIs | Strictly For Educational & Quantitative Research Use")
