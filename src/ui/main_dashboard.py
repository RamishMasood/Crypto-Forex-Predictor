"""
Unified Professional Trading Terminal
Dark-mode Streamlit dashboard with:
  - Spot / Futures toggle
  - Crypto / Forex / Commodities selector
  - Live candlestick chart with EMA Ribbon, SuperTrend, FVG zones
  - Derivatives panel: Funding Rate gauge, OI chart, Basis spread, L/S Ratio
  - 9-Layer confluence score (Futures) or 5-Layer (Spot)
  - Full institutional Trade Setup card
  - Multi-exchange price comparison table + Arbitrage alert
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from src.engine.orchestrator import PredictorOrchestrator
from src.data.forex_feeds import FOREX_PAIRS_MAP

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Quant Terminal | Spot & Futures",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# GLOBAL DARK THEME CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    html, body, [class*="css"] { background-color: #0d1117 !important; color: #c9d1d9; }
    .block-container { padding: 1.2rem 2rem; }
    .stSidebar { background-color: #161b22 !important; }
    .stSidebar .css-1d391kg { background-color: #161b22; }

    .metric-card {
        background: linear-gradient(135deg, #161b22, #1e2633);
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 10px;
    }
    .signal-box {
        border-radius: 10px;
        padding: 10px 20px;
        font-size: 1.3rem;
        font-weight: 800;
        text-align: center;
        letter-spacing: 0.04em;
    }
    .strong-buy  { background: #00c853; color: #000; }
    .buy         { background: #69f0ae; color: #000; }
    .neutral     { background: #ffd600; color: #000; }
    .sell        { background: #ff5252; color: #fff; }
    .strong-sell { background: #b71c1c; color: #fff; }

    .futures-badge {
        background: linear-gradient(90deg, #7c3aed, #4f46e5);
        color: #fff;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.06em;
    }
    .spot-badge {
        background: linear-gradient(90deg, #0ea5e9, #06b6d4);
        color: #fff;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.06em;
    }
    .layer-row-bull { color: #69f0ae; font-weight: 600; }
    .layer-row-bear { color: #ff5252; font-weight: 600; }
    .layer-row-neut { color: #8b949e; }

    div[data-testid="stMetricValue"] { font-size: 1.4rem !important; font-weight: 700; }
    div[data-testid="stMetricLabel"] { color: #8b949e; font-size: 0.75rem; }
    .stProgress .st-bo { background-color: #30363d; }
    hr { border-color: #30363d; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CACHED ORCHESTRATOR
# ─────────────────────────────────────────────
@st.cache_resource
def get_orchestrator():
    return PredictorOrchestrator()

orchestrator = get_orchestrator()

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Quant Terminal")
    st.markdown("*Institutional Multi-Exchange Engine*")
    st.divider()

    # Market mode toggle
    market_mode = st.radio(
        "Market Mode",
        ["Spot", "Futures (Perpetual)"],
        horizontal=True
    )
    is_futures_mode = (market_mode == "Futures (Perpetual)")

    st.divider()

    # Asset class
    asset_class = st.radio("Asset Class", ["Cryptocurrency", "Forex & Commodities"])

    if asset_class == "Cryptocurrency":
        crypto_presets = [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
            "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
            "LINK/USDT", "NEAR/USDT", "APT/USDT", "SUI/USDT"
        ]
        symbol = st.selectbox("Symbol", crypto_presets)
        custom = st.text_input("Custom Pair:", placeholder="e.g. PEPE/USDT")
        if custom.strip():
            symbol = custom.strip().upper()
        if is_futures_mode:
            preferred_exchange = 'bybit'
        else:
            preferred_exchange = st.selectbox("Exchange", ["binance", "bybit", "coinbase", "kucoin", "gateio"])
        asset_type_code = 'crypto'
    else:
        is_futures_mode = False   # Forex has no perpetual futures mode here
        symbol = st.selectbox("Pair / Asset", list(FOREX_PAIRS_MAP.keys()))
        custom = st.text_input("Custom Ticker:", placeholder="e.g. USDJPY=X")
        if custom.strip():
            symbol = custom.strip()
        preferred_exchange = 'interbank'
        asset_type_code = 'forex'

    timeframe = st.selectbox("Timeframe", ["5m", "15m", "30m", "1h", "4h", "1d"], index=3)

    st.divider()
    st.subheader("Risk Management")
    account_size = st.number_input("Account Balance (USD)", min_value=100.0, value=10000.0, step=500.0)
    risk_pct = st.slider("Risk Per Trade (%)", 0.25, 5.0, 1.5, 0.25)

    st.divider()
    analyze_btn = st.button("ANALYZE LIVE", type="primary", use_container_width=True)

    st.markdown("""
    <div style='margin-top:20px; font-size:0.7rem; color:#484f58; text-align:center;'>
    Real data from Binance · Bybit · Coinbase<br>KuCoin · Gate.io · Yahoo Finance<br>
    Zero private API keys required.
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HELPER: Signal badge HTML
# ─────────────────────────────────────────────
def action_badge(action: str) -> str:
    cls_map = {
        'STRONG BUY':  'strong-buy',
        'BUY':         'buy',
        'NEUTRAL':     'neutral',
        'SELL':        'sell',
        'STRONG SELL': 'strong-sell'
    }
    cls = cls_map.get(action, 'neutral')
    return f'<div class="signal-box {cls}">{action}</div>'

# ─────────────────────────────────────────────
# HELPER: Candlestick + Indicator Chart
# ─────────────────────────────────────────────
def render_chart(df_chart: pd.DataFrame, smc_data: dict, title: str):
    n_show = min(80, len(df_chart))
    pf = df_chart.iloc[-n_show:].reset_index(drop=True)
    xi = np.arange(len(pf))

    fig = plt.figure(figsize=(14, 8), facecolor='#0d1117')
    gs = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.08)
    ax1 = fig.add_subplot(gs[0]); ax1.set_facecolor('#161b22')
    ax2 = fig.add_subplot(gs[1], sharex=ax1); ax2.set_facecolor('#161b22')
    ax3 = fig.add_subplot(gs[2], sharex=ax1); ax3.set_facecolor('#161b22')

    # ── Candlesticks ──
    for idx, row in pf.iterrows():
        col = '#26a641' if row['close'] >= row['open'] else '#da3633'
        ax1.plot([idx, idx], [row['low'], row['high']], color=col, lw=1.2, zorder=2)
        bot = min(row['open'], row['close'])
        ht  = max(abs(row['close'] - row['open']), (row['high']-row['low'])*0.04)
        ax1.add_patch(plt.Rectangle((idx-0.38, bot), 0.76, ht, color=col, alpha=0.92, zorder=3))

    # ── EMAs ──
    ax1.plot(xi, pf['ema_20'],  color='#38bdf8', lw=1.4, label='EMA 20',  zorder=4)
    ax1.plot(xi, pf['ema_50'],  color='#c084fc', lw=1.4, label='EMA 50',  zorder=4)
    if 'ema_200' in pf.columns:
        ax1.plot(xi, pf['ema_200'], color='#fb923c', lw=1.6, linestyle='--', label='EMA 200', zorder=4)

    # ── SuperTrend dots ──
    if 'supertrend' in pf.columns:
        st_c = ['#00e676' if d == 1 else '#ff1744' for d in pf['supertrend_dir']]
        ax1.scatter(xi, pf['supertrend'], c=st_c, s=14, zorder=5, label='SuperTrend')

    # ── FVG shading ──
    active_fvgs = smc_data.get('active_fvgs', [])
    for fvg in active_fvgs:
        fc = 'rgba(0,230,118,0.12)' if fvg['type'] == 'BULLISH_FVG' else 'rgba(255,23,68,0.12)'
        matplotlib_alpha = 0.13
        color = '#00e676' if fvg['type'] == 'BULLISH_FVG' else '#ff1744'
        ax1.axhspan(fvg['bottom'], fvg['top'], color=color, alpha=matplotlib_alpha)

    ax1.set_ylabel("Price", color='#8b949e', fontsize=9)
    ax1.tick_params(colors='#8b949e', labelsize=8)
    ax1.grid(True, color='#21262d', lw=0.6, linestyle=':')
    ax1.spines[:].set_color('#21262d')
    leg = ax1.legend(loc='upper left', facecolor='#161b22', edgecolor='#30363d',
                     labelcolor='#c9d1d9', fontsize=8, framealpha=0.8)
    ax1.set_title(title, color='#c9d1d9', fontsize=11, pad=8)

    # ── RSI panel ──
    ax2.plot(xi, pf['rsi_14'], color='#a78bfa', lw=1.5, label='RSI 14')
    ax2.axhline(70, color='#ff5252', lw=0.8, ls='--', alpha=0.7)
    ax2.axhline(30, color='#69f0ae', lw=0.8, ls='--', alpha=0.7)
    ax2.fill_between(xi, pf['rsi_14'], 70, where=(pf['rsi_14'] > 70), alpha=0.15, color='#ff5252')
    ax2.fill_between(xi, pf['rsi_14'], 30, where=(pf['rsi_14'] < 30), alpha=0.15, color='#69f0ae')
    ax2.set_ylim(10, 90); ax2.set_ylabel("RSI", color='#8b949e', fontsize=8)
    ax2.tick_params(colors='#8b949e', labelsize=7)
    ax2.grid(True, color='#21262d', lw=0.5, linestyle=':')
    ax2.spines[:].set_color('#21262d')

    # ── MACD panel ──
    if 'macd_hist' in pf.columns:
        hist_colors = ['#26a641' if v >= 0 else '#da3633' for v in pf['macd_hist']]
        ax3.bar(xi, pf['macd_hist'], color=hist_colors, width=0.7, alpha=0.85, label='MACD Hist')
        ax3.plot(xi, pf['macd_line'],   color='#38bdf8', lw=1.2, label='MACD')
        ax3.plot(xi, pf['macd_signal'], color='#fb923c', lw=1.2, linestyle='--', label='Signal')
        ax3.axhline(0, color='#30363d', lw=0.8)
    ax3.set_ylabel("MACD", color='#8b949e', fontsize=8)
    ax3.tick_params(colors='#8b949e', labelsize=7)
    ax3.grid(True, color='#21262d', lw=0.5, linestyle=':')
    ax3.spines[:].set_color('#21262d')

    # X axis labels
    step = max(1, len(pf) // 8)
    ticks = xi[::step]
    lbls  = [pd.to_datetime(pf['timestamp'].iloc[i]).strftime('%m/%d %H:%M') for i in ticks]
    ax3.set_xticks(ticks); ax3.set_xticklabels(lbls, rotation=25, color='#8b949e', fontsize=7)
    plt.setp(ax1.get_xticklabels(), visible=False)
    plt.setp(ax2.get_xticklabels(), visible=False)

    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────
# HELPER: Futures Derivatives Panel
# ─────────────────────────────────────────────
def render_futures_panel(futures_data: dict, futures_signals: dict):
    fh  = futures_data.get('funding_history', pd.DataFrame())
    oih = futures_data.get('oi_history', pd.DataFrame())

    fig, axes = plt.subplots(1, 2, figsize=(13, 3.2), facecolor='#0d1117')

    # ── Funding Rate History ──
    ax_f = axes[0]; ax_f.set_facecolor('#161b22')
    if not fh.empty and len(fh) > 1:
        fr_pct = fh['funding_rate_pct'].values[-48:]
        xi_f   = np.arange(len(fr_pct))
        colors_f = ['#26a641' if v >= 0 else '#da3633' for v in fr_pct]
        ax_f.bar(xi_f, fr_pct, color=colors_f, alpha=0.85, width=0.8)
        ax_f.axhline(0, color='#8b949e', lw=0.8)
        ax_f.axhline(0.05,  color='#da3633', lw=1.0, ls='--', alpha=0.7)
        ax_f.axhline(-0.04, color='#26a641', lw=1.0, ls='--', alpha=0.7)
    ax_f.set_title("Funding Rate History (%)", color='#c9d1d9', fontsize=9)
    ax_f.set_ylabel("Funding %", color='#8b949e', fontsize=8)
    ax_f.tick_params(colors='#8b949e', labelsize=7)
    ax_f.grid(True, color='#21262d', lw=0.4, linestyle=':')
    ax_f.spines[:].set_color('#21262d')

    # ── Open Interest History ──
    ax_o = axes[1]; ax_o.set_facecolor('#161b22')
    if not oih.empty and len(oih) > 1:
        xi_o = np.arange(len(oih))
        ax_o.fill_between(xi_o, oih['open_interest'].values, alpha=0.4, color='#7c3aed')
        ax_o.plot(xi_o, oih['open_interest'].values, color='#a78bfa', lw=1.5)
    ax_o.set_title("Open Interest History", color='#c9d1d9', fontsize=9)
    ax_o.set_ylabel("OI (Contracts)", color='#8b949e', fontsize=8)
    ax_o.tick_params(colors='#8b949e', labelsize=7)
    ax_o.grid(True, color='#21262d', lw=0.4, linestyle=':')
    ax_o.spines[:].set_color('#21262d')

    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────
# MAIN APP LOGIC
# ─────────────────────────────────────────────
def run():
    st.markdown(f"""
    <div style='display:flex; align-items:center; gap:12px; margin-bottom:4px;'>
        <h2 style='margin:0; color:#c9d1d9;'>Quantitative Signal Terminal</h2>
        <span class='{"futures-badge" if is_futures_mode else "spot-badge"}'>
            {"PERP FUTURES" if is_futures_mode else "SPOT"}
        </span>
    </div>
    <div style='color:#8b949e; font-size:0.85rem; margin-bottom:16px;'>
        Live multi-exchange institutional predictor · {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    </div>
    """, unsafe_allow_html=True)

    # Run analysis
    with st.spinner(f"Fetching live data for {symbol} ({market_mode}) on {timeframe}..."):
        try:
            res = orchestrator.run_prediction(
                symbol=symbol,
                asset_type=asset_type_code,
                market_mode='futures' if is_futures_mode else 'spot',
                timeframe=timeframe,
                preferred_exchange=preferred_exchange,
                account_size_usd=account_size,
                risk_per_trade_pct=risk_pct
            )
            success = True
            err_msg = ""
        except Exception as e:
            success = False
            err_msg = str(e)

    if not success:
        st.error(f"Error fetching live data: {err_msg}")
        st.stop()

    # Unpack
    meta   = res['metadata']
    mkt    = res['market_data']
    conf   = res['confluence']
    setup  = res['trade_setup']
    ml     = res['ml_prediction']
    smc    = res['smc_analysis']
    arb    = res['arbitrage']
    ind    = res['indicators_summary']
    df_c   = res['df_chart']
    fut_d  = res['futures_data']
    fut_s  = res['futures_signals']

    curr_p = mkt['current_price']
    action = conf['action']
    chg    = mkt['ticker'].get('change_24h_pct', 0.0) if mkt['ticker'] else 0.0

    # ── TOP METRICS STRIP ──
    col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1.5, 1.5, 2])
    with col1:
        badge_html = action_badge(action)
        st.markdown(badge_html, unsafe_allow_html=True)
    with col2:
        st.metric("Live Price", f"${curr_p:,.4f}" if curr_p > 1 else f"${curr_p:.6f}", delta=f"{chg:+.2f}%")
    with col3:
        score_val = conf['confluence_score']
        score_color = "green" if score_val > 0 else ("red" if score_val < 0 else "gray")
        st.metric("Confluence Score", f"{score_val:+.1f}/100")
    with col4:
        st.metric("Conviction", f"{conf['quality_index_pct']}%")
    with col5:
        if is_futures_mode and fut_d:
            ticker_f = fut_d.get('ticker', {})
            fr = (ticker_f.get('funding_rate', 0.0) or 0.0) * 100.0
            fr_color = "inverse" if fr > 0.04 else ("normal" if fr < -0.03 else "off")
            st.metric("Funding Rate", f"{fr:+.5f}%", delta="8h", delta_color=fr_color)
        else:
            vol = mkt['ticker'].get('volume', 0.0) if mkt['ticker'] else 0.0
            st.metric("Volume 24h", f"{vol:,.1f}")

    # Forex session info
    if mkt.get('forex_sessions'):
        sess = mkt['forex_sessions']
        active = ", ".join(sess['active_sessions']) if sess['active_sessions'] else "Quiet"
        overlap = " | Major London-NY Overlap (Peak Liquidity)" if sess['is_major_overlap'] else ""
        st.info(f"Active Sessions: **{active}**{overlap}")

    st.divider()

    # ── FUTURES DERIVATIVES PANEL ──
    if is_futures_mode and fut_d and fut_s:
        st.subheader("Derivatives Dashboard — Live Futures Metrics")

        fc1, fc2, fc3, fc4 = st.columns(4)
        ticker_f = fut_d.get('ticker', {}) or {}
        fr_val  = (ticker_f.get('funding_rate', 0) or 0) * 100
        oi_val  = ticker_f.get('open_interest', 0) or 0
        basis_d = fut_d.get('basis', {})
        ls_data = fut_d.get('long_short_ratio', {})

        with fc1:
            st.metric("Mark Price", f"${ticker_f.get('mark_price', curr_p):,.2f}")
            st.metric("Index Price", f"${ticker_f.get('index_price', curr_p):,.2f}")
        with fc2:
            st.metric("Current Funding Rate", f"{fr_val:+.5f}%")
            annualized = fr_val * 3 * 365
            st.metric("Annualized Funding", f"{annualized:+.1f}%")
        with fc3:
            st.metric("Open Interest", f"{oi_val:,.0f} BTC" if 'BTC' in symbol.upper() else f"{oi_val:,.0f}")
            st.metric("Basis (Spot-Futures)", f"{basis_d.get('basis_pct', 0):+.4f}%")
        with fc4:
            st.metric("Longs", f"{ls_data.get('long_pct', 50):.1f}%")
            st.metric("Shorts", f"{ls_data.get('short_pct', 50):.1f}%")

        # Futures charts
        fut_fig = render_futures_panel(fut_d, fut_s)
        st.pyplot(fut_fig)
        plt.close(fut_fig)

        # Futures signal summary
        sq = fut_s.get('squeeze_analysis', {})
        squeeze_type = sq.get('squeeze_type', 'NONE')
        if 'SQUEEZE_SETUP' in squeeze_type:
            sq_color = "success" if 'SHORT_SQUEEZE' in squeeze_type else "error"
            sq_msg = (f"SHORT SQUEEZE SETUP ({sq.get('short_squeeze_signals', 0)}/4 signals) — Bears over-crowded at {sq.get('short_pct', 0):.1f}%. Explosive long rally risk!"
                      if 'SHORT_SQUEEZE' in squeeze_type else
                      f"LONG SQUEEZE SETUP ({sq.get('long_squeeze_signals', 0)}/4 signals) — Longs over-crowded at {sq.get('long_pct', 0):.1f}%. Liquidation cascade risk!")
            if sq_color == 'success':
                st.success(f"F3 SQUEEZE ALERT: {sq_msg}")
            else:
                st.error(f"F3 SQUEEZE ALERT: {sq_msg}")

        fr_analysis = fut_s.get('funding_analysis', {})
        regime = fr_analysis.get('regime', 'NEUTRAL')
        if 'EXTREME' in regime:
            st.warning(f"F1 FUNDING ALERT: {regime.replace('_', ' ')} — {fr_analysis.get('reasons', [''])[0]}")

        st.divider()

    # ── MAIN CHART ──
    st.subheader(f"Live Chart — {symbol} / {timeframe}")
    chart_title = f"{symbol}  [{meta['exchange'].upper()}]  {timeframe}  ({'PERP FUTURES' if is_futures_mode else 'SPOT'})"
    fig = render_chart(df_c, smc, chart_title)
    st.pyplot(fig)
    plt.close(fig)

    st.divider()

    # ── 3-PANEL ANALYSIS ROW ──
    a1, a2, a3 = st.columns(3)

    with a1:
        st.markdown("### Confluence Breakdown")
        layers = conf['layer_scores']
        for name, val in layers.items():
            label = name.replace('_', ' ').title()
            color = "#69f0ae" if val > 0 else ("#ff5252" if val < 0 else "#8b949e")
            bar_width = int(min(100, abs(val) * 1.5))
            bar_color = color
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;margin-bottom:6px;'>"
                f"<span style='color:#c9d1d9;font-size:0.82rem;'>{label}</span>"
                f"<span style='color:{color};font-weight:700;font-size:0.9rem;'>{val:+.1f}</span>"
                f"</div>"
                f"<div style='background:#21262d;border-radius:4px;height:6px;margin-bottom:10px;'>"
                f"<div style='background:{bar_color};width:{bar_width}%;height:6px;border-radius:4px;'></div>"
                f"</div>",
                unsafe_allow_html=True
            )

        # Confluence gauge
        norm = (conf['confluence_score'] + 100.0) / 200.0
        st.progress(float(norm), text=f"Bearish  Score: {conf['confluence_score']:+.1f}  Bullish")

    with a2:
        st.markdown("### ML Prediction")
        st.metric("Direction", ml['predicted_direction'])
        p_b = ml['p_bullish'] * 100
        p_s = ml['p_bearish'] * 100
        p_n = ml['p_neutral'] * 100
        st.markdown(
            f"<div style='margin-bottom:10px;'>"
            f"<div style='color:#69f0ae;font-size:0.88rem;'>Bullish: <b>{p_b:.1f}%</b></div>"
            f"<div style='background:#21262d;height:8px;border-radius:4px;margin:4px 0 8px;'>"
            f"<div style='background:#69f0ae;width:{p_b}%;height:8px;border-radius:4px;'></div></div>"
            f"<div style='color:#ff5252;font-size:0.88rem;'>Bearish: <b>{p_s:.1f}%</b></div>"
            f"<div style='background:#21262d;height:8px;border-radius:4px;margin:4px 0 8px;'>"
            f"<div style='background:#ff5252;width:{p_s}%;height:8px;border-radius:4px;'></div></div>"
            f"<div style='color:#8b949e;font-size:0.88rem;'>Neutral: <b>{p_n:.1f}%</b></div>"
            f"<div style='background:#21262d;height:8px;border-radius:4px;margin:4px 0 8px;'>"
            f"<div style='background:#8b949e;width:{p_n}%;height:8px;border-radius:4px;'></div></div>"
            f"</div>",
            unsafe_allow_html=True
        )
        st.metric("Model Confidence", f"{ml['confidence_pct']}%")
        st.metric("CV Accuracy (Walk-Forward)", f"{ml['cv_accuracy_pct']}%")
        st.metric("Expected Move", f"{ml['expected_return_pct']:+.2f}%")

    with a3:
        st.markdown("### Smart Money (SMC)")
        st.metric("Market Structure", smc['structure']['structure'])
        st.metric("Liquidity Sweep", smc['structure'].get('liquidity_sweep', 'NONE'))
        st.metric("Unmitigated FVGs", smc['open_fvgs_count'])
        st.metric("Order Blocks (OB)", smc['order_blocks_count'])

        if smc['open_fvgs_count'] > 0:
            st.markdown("**Active FVG Zones:**")
            for fvg in smc.get('active_fvgs', []):
                color = "green" if fvg['type'] == 'BULLISH_FVG' else "red"
                st.markdown(f"<span style='color:{'#69f0ae' if color=='green' else '#ff5252'};font-size:0.8rem;'>"
                            f"{fvg['type'].replace('_', ' ')}: ${fvg['bottom']:,.2f} — ${fvg['top']:,.2f} ({fvg['size_pct']:.2f}%)"
                            f"</span>", unsafe_allow_html=True)

    st.divider()

    # ── TRADE SETUP CARD ──
    st.subheader("Institutional Trade Setup")
    if setup['status'] == 'ACTIVE_SETUP':
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            st.metric("Entry Zone", f"${setup['recommended_entry']:,.4f}")
            st.metric("Action", setup['action'])
        with sc2:
            st.metric("Stop Loss", f"${setup['stop_loss']:,.4f}", delta=f"-{setup['sl_distance_pct']}%", delta_color="inverse")
            st.metric("Risk Capital", f"${setup['risk_amount_usd']:,.2f}")
        with sc3:
            st.metric("TP1 (1:1.5 R:R)", f"${setup['tp1']:,.4f}", delta=f"+{setup['tp1_gain_pct']}%")
            st.metric("TP2 (1:2.5 R:R)", f"${setup['tp2']:,.4f}", delta=f"+{setup['tp2_gain_pct']}%")
        with sc4:
            st.metric("TP3 (1:4.0 Runner)", f"${setup['tp3']:,.4f}", delta=f"+{setup['tp3_gain_pct']}%")
            st.metric("Half-Kelly Size", f"{setup['half_kelly_pct']}% of portfolio")
    else:
        st.info("No active trade setup — market in consolidation / neutral zone. Capital preservation mode.")

    # ── MULTI-EXCHANGE TABLE + ARBITRAGE ──
    if asset_type_code == 'crypto':
        st.divider()
        ec1, ec2 = st.columns([1.2, 1])
        with ec1:
            st.markdown("### Multi-Exchange Live Prices")
            ex_rows = []
            for ex, val in mkt.get('multi_exchange_prices', {}).items():
                p = val.get('price')
                p_str = f"${p:,.2f}" if p else "N/A"
                chg_s = f"{val.get('change_24h', 0.0):+.2f}%" if val.get('change_24h') is not None else "—"
                vol_s = f"{val.get('volume', 0):,.0f}" if val.get('volume') else "—"
                ex_rows.append({'Exchange': ex.upper(), 'Price': p_str, '24h Change': chg_s, 'Volume': vol_s, 'Status': val.get('status')})
            df_ex = pd.DataFrame(ex_rows)
            st.dataframe(df_ex, use_container_width=True, hide_index=True)

        with ec2:
            st.markdown("### Arbitrage Scanner")
            if arb.get('arbitrage_available'):
                st.success(
                    f"ARBITRAGE DETECTED\n\n"
                    f"Buy: **{arb['cheapest_exchange'].upper()}** @ ${arb['cheapest_price']:,.2f}\n\n"
                    f"Sell: **{arb['highest_exchange'].upper()}** @ ${arb['highest_price']:,.2f}\n\n"
                    f"Gross Spread: **{arb['gross_spread_pct']:.3f}%** | Net: **{arb['net_spread_pct']:.3f}%** | Rating: **{arb['opportunity_rating']}**"
                )
            else:
                st.info("Prices within normal market-making spread range.\nNo net-profitable arbitrage opportunity currently.")

    # ── SIGNAL CHECKLIST ──
    st.divider()
    st.subheader("Signal Checklist & Rationale")
    reasons = conf['reasons']
    cr1, cr2 = st.columns(2)
    half = len(reasons) // 2
    for i, r in enumerate(reasons):
        col = cr1 if i < half else cr2
        if "(+" in r or "Bullish" in r or "SQUEEZE SETUP" in r and "SHORT" in r:
            col.markdown(f"<div class='layer-row-bull'>[+] {r}</div>", unsafe_allow_html=True)
        elif "(-" in r or "Bearish" in r or "LONG SQUEEZE" in r:
            col.markdown(f"<div class='layer-row-bear'>[-] {r}</div>", unsafe_allow_html=True)
        else:
            col.markdown(f"<div class='layer-row-neut'>[*] {r}</div>", unsafe_allow_html=True)

    st.divider()
    st.caption("Quant Terminal | Real-Time Public APIs (Zero Private Keys) | Educational & Research Use Only")


run()
