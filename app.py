"""
Quant Terminal - Unified Spot & Futures Predictor
Streamlit dashboard - auto-loads on page open (no button press needed on first load)
"""
import os
import sys
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

st.set_page_config(
    page_title="Quant Terminal | Spot & Futures",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ── CSS ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.block-container { padding:1rem 2rem 2rem; }
.big-badge {
    display:inline-block; padding:8px 28px; border-radius:10px;
    font-size:1.5rem; font-weight:900; letter-spacing:.06em;
    text-align:center; width:100%;
}
.sbuy  { background:#00c853; color:#000; }
.buy   { background:#69f0ae; color:#000; }
.neut  { background:#ffd600; color:#111; }
.sell  { background:#ff5252; color:#fff; }
.ssell { background:#b71c1c; color:#fff; }
.layer-bull { color:#00b300; font-size:.85rem; padding:2px 0; }
.layer-bear { color:#cc0000; font-size:.85rem; padding:2px 0; }
.layer-neut { color:#666; font-size:.85rem; padding:2px 0; }
</style>
""", unsafe_allow_html=True)

# ── SIDEBAR ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Quant Terminal")
    st.caption("Multi-Exchange Signal Engine")
    st.divider()

    market_mode_label = st.radio("Market Mode", ["Spot", "Futures (Perpetual)"], horizontal=True)
    is_futures = (market_mode_label == "Futures (Perpetual)")

    st.divider()
    asset_class = st.radio("Asset Class", ["Cryptocurrency", "Forex & Commodities"])

    CRYPTO_PAIRS = ["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT","XRP/USDT",
                    "DOGE/USDT","ADA/USDT","AVAX/USDT","LINK/USDT"]

    FOREX_PAIRS = ["EUR/USD","GBP/USD","USD/JPY","AUD/USD","XAU/USD","XAG/USD"]

    if asset_class == "Cryptocurrency":
        symbol = st.selectbox("Symbol", CRYPTO_PAIRS)
        custom = st.text_input("Custom pair:", placeholder="e.g. PEPE/USDT")
        if custom.strip():
            symbol = custom.strip().upper()
        exchange = "bybit" if is_futures else st.selectbox(
            "Exchange", ["binance","bybit","coinbase","kucoin","gateio"])
        asset_code = "crypto"
    else:
        is_futures = False
        symbol = st.selectbox("Pair", FOREX_PAIRS)
        exchange = "interbank"
        asset_code = "forex"

    timeframe = st.selectbox("Timeframe", ["3m","5m","15m","30m","1h","4h","1d"], index=1)

    st.divider()
    st.subheader("Risk")
    account = st.number_input("Balance (USD)", min_value=100.0, value=10000.0, step=500.0)
    risk_pct = st.slider("Risk % per trade", 0.25, 5.0, 1.5, 0.25)

    st.divider()
    run_btn = st.button("🔄 ANALYZE LIVE", type="primary", use_container_width=True)

# ── HELPERS ────────────────────────────────────────────────────────────────
def action_html(action):
    cls = {"STRONG BUY":"sbuy","BUY":"buy","NEUTRAL":"neut",
           "SELL":"sell","STRONG SELL":"ssell"}.get(action,"neut")
    return f'<div class="big-badge {cls}">{action}</div>'

def render_chart(df, smc):
    n   = min(80, len(df))
    pf  = df.iloc[-n:].reset_index(drop=True)
    x   = np.arange(len(pf))
    bg  = '#0e1117'
    pan = '#1a1d24'

    fig = plt.figure(figsize=(14,8), facecolor=bg)
    gs  = gridspec.GridSpec(3,1,height_ratios=[3,1,1],hspace=.06)
    ax1 = fig.add_subplot(gs[0]); ax1.set_facecolor(pan)
    ax2 = fig.add_subplot(gs[1],sharex=ax1); ax2.set_facecolor(pan)
    ax3 = fig.add_subplot(gs[2],sharex=ax1); ax3.set_facecolor(pan)

    for i,row in pf.iterrows():
        c = '#26a641' if row['close']>=row['open'] else '#da3633'
        ax1.plot([i,i],[row['low'],row['high']],color=c,lw=1.2,zorder=2)
        b = min(row['open'],row['close'])
        h = max(abs(row['close']-row['open']),(row['high']-row['low'])*.04)
        ax1.add_patch(plt.Rectangle((i-.38,b),.76,h,color=c,alpha=.9,zorder=3))

    ax1.plot(x,pf['ema_20'],'#38bdf8',lw=1.3,label='EMA20')
    ax1.plot(x,pf['ema_50'],'#c084fc',lw=1.3,label='EMA50')
    if 'ema_200' in pf.columns:
        ax1.plot(x,pf['ema_200'],'#fb923c',lw=1.5,ls='--',label='EMA200')
    if 'vwap' in pf.columns:
        ax1.plot(x, pf['vwap'], '#facc15', lw=1.5, label='VWAP')
        if 'vwap_upper_2' in pf.columns:
            ax1.plot(x, pf['vwap_upper_2'], '#facc15', lw=0.8, ls=':', alpha=0.7)
            ax1.plot(x, pf['vwap_lower_2'], '#facc15', lw=0.8, ls=':', alpha=0.7)
    if 'supertrend' in pf.columns:
        sc=['#00e676' if d==1 else '#ff1744' for d in pf['supertrend_dir']]
        ax1.scatter(x,pf['supertrend'],c=sc,s=12,zorder=5)
    for fvg in smc.get('active_fvgs',[]):
        col='#00e676' if 'BULLISH' in fvg['type'] else '#ff1744'
        ax1.axhspan(fvg['bottom'],fvg['top'],color=col,alpha=.1)

    ax1.set_facecolor(pan); ax1.tick_params(colors='#aaa',labelsize=8)
    ax1.set_ylabel("Price",color='#aaa',fontsize=9)
    ax1.grid(True,color='#2a2d35',lw=.6,ls=':')
    for sp in ax1.spines.values(): sp.set_color('#2a2d35')
    ax1.legend(loc='upper left',facecolor=pan,edgecolor='#333',labelcolor='#ccc',fontsize=8)

    ax2.plot(x,pf['rsi_14'],'#a78bfa',lw=1.4)
    ax2.axhline(70,color='#ff5252',lw=.8,ls='--',alpha=.7)
    ax2.axhline(30,color='#69f0ae',lw=.8,ls='--',alpha=.7)
    ax2.fill_between(x,pf['rsi_14'],70,where=(pf['rsi_14']>70),alpha=.12,color='#ff5252')
    ax2.fill_between(x,pf['rsi_14'],30,where=(pf['rsi_14']<30),alpha=.12,color='#69f0ae')
    ax2.set_ylim(10,90); ax2.set_ylabel("RSI",color='#aaa',fontsize=8)
    ax2.tick_params(colors='#aaa',labelsize=7)
    ax2.grid(True,color='#2a2d35',lw=.5,ls=':')
    for sp in ax2.spines.values(): sp.set_color('#2a2d35')
    plt.setp(ax1.get_xticklabels(),visible=False)
    plt.setp(ax2.get_xticklabels(),visible=False)

    if 'macd_hist' in pf.columns:
        mc=['#26a641' if v>=0 else '#da3633' for v in pf['macd_hist']]
        ax3.bar(x,pf['macd_hist'],color=mc,width=.7,alpha=.85)
        ax3.plot(x,pf['macd_line'],'#38bdf8',lw=1.2)
        ax3.plot(x,pf['macd_signal'],'#fb923c',lw=1.2,ls='--')
        ax3.axhline(0,color='#333',lw=.8)
    ax3.set_ylabel("MACD",color='#aaa',fontsize=8)
    ax3.tick_params(colors='#aaa',labelsize=7)
    ax3.grid(True,color='#2a2d35',lw=.5,ls=':')
    for sp in ax3.spines.values(): sp.set_color('#2a2d35')

    step=max(1,len(pf)//8)
    ticks=x[::step]
    lbls=[pd.to_datetime(pf['timestamp'].iloc[i]).strftime('%m/%d %H:%M') for i in ticks]
    ax3.set_xticks(ticks); ax3.set_xticklabels(lbls,rotation=25,color='#aaa',fontsize=7)
    plt.tight_layout()
    return fig

def render_deriv(fut_d, df_indicators):
    fh  = fut_d.get('funding_history', pd.DataFrame())
    oih = fut_d.get('oi_history', pd.DataFrame())
    bg  = '#0e1117'; pan = '#1a1d24'

    fig, (ax_f, ax_o, ax_c) = plt.subplots(1,3,figsize=(15,3.2),facecolor=bg)
    ax_f.set_facecolor(pan); ax_o.set_facecolor(pan); ax_c.set_facecolor(pan)

    if not fh.empty and len(fh)>1:
        vals=fh['funding_rate_pct'].values[-48:]
        xi=np.arange(len(vals))
        cols=['#26a641' if v>=0 else '#da3633' for v in vals]
        ax_f.bar(xi,vals,color=cols,alpha=.85,width=.8)
        ax_f.axhline(0,color='#888',lw=.8)
        ax_f.axhline(.05,color='#da3633',lw=1.0,ls='--',alpha=.7)
        ax_f.axhline(-.04,color='#26a641',lw=1.0,ls='--',alpha=.7)
    ax_f.set_title("Funding Rate History (%)",color='#ccc',fontsize=9)
    ax_f.set_ylabel("Funding %",color='#aaa',fontsize=8)
    ax_f.tick_params(colors='#aaa',labelsize=7)
    ax_f.grid(True,color='#2a2d35',lw=.4,ls=':')
    for sp in ax_f.spines.values(): sp.set_color('#2a2d35')

    if not oih.empty and len(oih)>1:
        xi=np.arange(len(oih))
        ax_o.fill_between(xi,oih['open_interest'].values,alpha=.35,color='#7c3aed')
        ax_o.plot(xi,oih['open_interest'].values,'#a78bfa',lw=1.5)
    ax_o.set_title("Open Interest History",color='#ccc',fontsize=9)
    ax_o.set_ylabel("OI (Contracts)",color='#aaa',fontsize=8)
    ax_o.tick_params(colors='#aaa',labelsize=7)
    ax_o.grid(True,color='#2a2d35',lw=.4,ls=':')
    for sp in ax_o.spines.values(): sp.set_color('#2a2d35')

    if 'cvd' in df_indicators.columns and len(df_indicators) > 1:
        n = min(48, len(df_indicators))
        cvd_sub = df_indicators['cvd'].iloc[-n:].values
        xi_c = np.arange(len(cvd_sub))
        cvd_col = '#38bdf8' if cvd_sub[-1] >= cvd_sub[0] else '#f87171'
        ax_c.fill_between(xi_c, cvd_sub, alpha=0.3, color=cvd_col)
        ax_c.plot(xi_c, cvd_sub, color=cvd_col, lw=1.5)
    ax_c.set_title("CVD (Cumulative Volume Delta)", color='#ccc', fontsize=9)
    ax_c.set_ylabel("Delta", color='#aaa', fontsize=8)
    ax_c.tick_params(colors='#aaa', labelsize=7)
    ax_c.grid(True, color='#2a2d35', lw=.4, ls=':')
    for sp in ax_c.spines.values(): sp.set_color('#2a2d35')

    plt.tight_layout()
    return fig

# ── RUN ENGINE ────────────────────────────────────────────────────────────
# Cache key so we only re-run when inputs actually change
cache_key = f"{symbol}|{asset_code}|{market_mode_label}|{timeframe}|{exchange}|{account}|{risk_pct}"

if "result" not in st.session_state:
    st.session_state.result = None
    st.session_state.cache_key = ""

# Auto-trigger on first load OR when button pressed OR when params change
should_run = (
    run_btn
    or st.session_state.result is None
    or st.session_state.cache_key != cache_key
)

st.title("📊 Quantitative Signal Terminal")
mode_color = "#7c3aed" if is_futures else "#0ea5e9"
mode_label = "PERP FUTURES" if is_futures else "SPOT"
st.markdown(
    f"**{symbol}** &nbsp;|&nbsp; "
    f"<span style='background:{mode_color};color:#fff;padding:3px 10px;border-radius:12px;"
    f"font-size:.8rem;font-weight:700;'>{mode_label}</span> &nbsp;|&nbsp; "
    f"{timeframe} &nbsp;|&nbsp; {exchange.upper()}",
    unsafe_allow_html=True
)
st.divider()

if should_run:
    with st.spinner(f"Fetching live {mode_label} data for {symbol}..."):
        try:
            from src.engine.orchestrator import PredictorOrchestrator
            orch = PredictorOrchestrator()
            res  = orch.run_prediction(
                symbol=symbol,
                asset_type=asset_code,
                market_mode='futures' if is_futures else 'spot',
                timeframe=timeframe,
                preferred_exchange=exchange,
                account_size_usd=account,
                risk_per_trade_pct=risk_pct
            )
            st.session_state.result    = res
            st.session_state.cache_key = cache_key
        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)
            st.stop()

if st.session_state.result is None:
    st.warning("Click **ANALYZE LIVE** to start.")
    st.stop()

res = st.session_state.result

# ── UNPACK ─────────────────────────────────────────────────────────────────
meta  = res['metadata']
mkt   = res['market_data']
conf  = res['confluence']
setup = res['trade_setup']
ml    = res['ml_prediction']
smc   = res['smc_analysis']
arb   = res['arbitrage']
ind   = res['indicators_summary']
df_c  = res['df_chart']
fut_d = res['futures_data']
fut_s = res['futures_signals']
alpha = res.get('alpha_sniper', {})

curr_p = mkt['current_price']
action = conf['action']
chg    = (mkt['ticker'] or {}).get('change_24h_pct', 0.0)

# ── TOP METRICS ─────────────────────────────────────────────────────────────
t1, t2, t3, t4, t5 = st.columns([2,1.5,1.5,1.5,1.5])
with t1:
    st.markdown(action_html(action), unsafe_allow_html=True)
with t2:
    st.metric("Live Price", f"${curr_p:,.4f}" if curr_p > 1 else f"${curr_p:.6f}",
              delta=f"{chg:+.2f}%")
with t3:
    st.metric("Confluence Score", f"{conf['confluence_score']:+.1f} / 100")
with t4:
    st.metric("Calibrated Accuracy", f"{alpha.get('calibrated_win_probability_pct', 50):.1f}%" if alpha else f"{conf['quality_index_pct']}%")
with t5:
    if is_futures and fut_d and fut_d.get('ticker'):
        fr = (fut_d['ticker'].get('funding_rate', 0) or 0) * 100
        st.metric("Funding Rate (8h)", f"{fr:+.5f}%")
    else:
        vol = (mkt.get('ticker') or {}).get('volume', 0) or 0
        st.metric("Volume 24h", f"{vol:,.0f}")

# ── ALPHASNIPER PROPRIETARY INTELLIGENCE BANNER ──
if alpha:
    tier_bg = alpha.get('tier_color', '#00e676')
    st.markdown(
        f"<div style='background:linear-gradient(135deg,#161b22,#1c2333);border:1px solid #30363d;border-radius:12px;padding:14px 18px;margin:12px 0;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:10px;'>"
        f"<div>"
        f"<span style='background:{tier_bg};color:#000;padding:4px 14px;border-radius:20px;font-weight:900;font-size:.82rem;'>"
        f"{alpha.get('sniper_badge', 'SNIPER FILTER')}</span>"
        f"&nbsp;&nbsp;<span style='color:#c9d1d9;font-weight:700;font-size:1.02rem;'>AlphaSniper™ Proprietary Intelligence</span>"
        f"</div>"
        f"<div style='color:#69f0ae;font-size:1.15rem;font-weight:800;'>"
        f"Calibrated Win Expectancy: {alpha.get('calibrated_win_probability_pct', 50):.1f}%"
        f"</div>"
        f"</div>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;font-size:.82rem;color:#8b949e;'>"
        f"<div><b>AlphaRegime™:</b> <span style='color:#38bdf8;'>{alpha.get('alpha_regime')}</span></div>"
        f"<div><b>Hurst Exponent (H):</b> <span style='color:#c9d1d9;'>{alpha.get('hurst_exponent')}</span></div>"
        f"<div><b>Choppiness (CHOP):</b> <span style='color:#c9d1d9;'>{alpha.get('choppiness_index')}</span></div>"
        f"<div><b>Wyckoff Phase:</b> <span style='color:#facc15;'>{alpha.get('wyckoff_phase')}</span></div>"
        f"<div><b>Institutional Flow (IAI):</b> <span style='color:#a78bfa;'>{alpha.get('iai_status')}</span></div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True
    )

if mkt.get('forex_sessions'):
    sess = mkt['forex_sessions']
    active = ", ".join(sess['active_sessions']) or "Quiet hours"
    st.info(f"Active Sessions: **{active}**" + (" | London-NY Overlap (Peak Liquidity)" if sess.get('is_major_overlap') else ""))

st.divider()

# ── FUTURES PANEL ──────────────────────────────────────────────────────────
if is_futures and fut_d and fut_s:
    st.subheader("Derivatives Dashboard")
    tk = fut_d.get('ticker') or {}
    fr_val = (tk.get('funding_rate',0) or 0)*100
    oi_val = tk.get('open_interest',0) or 0
    basis_d = fut_d.get('basis',{})
    ls_data = fut_d.get('long_short_ratio',{})

    fc1,fc2,fc3,fc4 = st.columns(4)
    with fc1:
        st.metric("Mark Price",  f"${tk.get('mark_price',curr_p):,.2f}")
        st.metric("Index Price", f"${tk.get('index_price',curr_p):,.2f}")
    with fc2:
        st.metric("Funding Rate (8h)", f"{fr_val:+.5f}%")
        st.metric("Annualized",        f"{fr_val*3*365:+.1f}%")
    with fc3:
        st.metric("Open Interest",  f"{oi_val:,.0f}")
        st.metric("Basis Spread",   f"{basis_d.get('basis_pct',0):+.4f}%")
    with fc4:
        st.metric("Longs",  f"{ls_data.get('long_pct',50):.1f}%")
        st.metric("Shorts", f"{ls_data.get('short_pct',50):.1f}%")

    # Additional institutional metrics: CVD, VWAP & Liquidation Magnet
    cvd_data = fut_s.get('cvd_analysis', {})
    vwap_data = fut_s.get('vwap_analysis', {})
    liq_data = fut_s.get('liq_analysis', {})
    scalp_data = fut_s.get('scalp_analysis', {})

    fc5, fc6, fc7, fc8 = st.columns(4)
    with fc5:
        st.metric("Institutional VWAP", f"${vwap_data.get('vwap', curr_p):,.2f}", delta=f"{vwap_data.get('dist_vwap_pct', 0):+.2f}%")
    with fc6:
        st.metric("CVD Order Flow", f"{cvd_data.get('current_cvd', 0):,.0f}", delta=cvd_data.get('regime', 'BALANCED'))
    with fc7:
        magnet = liq_data.get('nearest_magnet', {})
        st.metric("Nearest Liq Magnet", f"${magnet.get('price', curr_p):,.2f}", delta=f"{liq_data.get('dist_to_magnet_pct', 0):+.2f}% ({magnet.get('leverage', '')})")
    with fc8:
        st.metric("Scalp Micro-Flow", scalp_data.get('scalp_setup', 'NEUTRAL'))

    st.pyplot(render_deriv(fut_d, df_c)); plt.close()

    # Alerts (Squeeze / Liquidation / Scalp / Funding)
    sq = fut_s.get('squeeze_analysis',{})
    if 'SETUP' in sq.get('squeeze_type','NONE'):
        msg = (sq.get('reasons') or [''])[0]
        if 'SHORT_SQUEEZE' in sq['squeeze_type']:
            st.success(f"⚡ SQUEEZE ALERT: {msg}")
        else:
            st.error(f"⚡ SQUEEZE ALERT: {msg}")

    if abs(liq_data.get('dist_to_magnet_pct', 99)) < 0.5:
        st.warning(f"🎯 LIQUIDATION MAGNET PROXIMITY: Price within {abs(liq_data.get('dist_to_magnet_pct', 0)):.2f}% of {magnet.get('leverage')} {magnet.get('type')} pool (${magnet.get('price', 0):,.2f})!")

    if scalp_data.get('scalp_setup') not in ('NEUTRAL', 'INACTIVE_TIMEFRAME'):
        st.info(f"⚡ 3m/5m SCALP TRIGGER: {scalp_data.get('scalp_setup')} (Rejection Wick: Lower={scalp_data.get('lower_wick_pct')}%, Upper={scalp_data.get('upper_wick_pct')}%)")

    fr_r = fut_s.get('funding_analysis',{})
    if 'EXTREME' in fr_r.get('regime',''):
        st.warning((fr_r.get('reasons') or [''])[0])

    # Liquidation Clusters Table
    if liq_data.get('clusters'):
        with st.expander("📍 Institutional Liquidation Clusters & Leverage Pools (Heatmap Map)", expanded=False):
            liq_rows = []
            for cl in liq_data['clusters']:
                liq_rows.append({
                    'Leverage Tier': cl['leverage'],
                    'Pool Type': cl['type'],
                    'Trigger Price (USD)': f"${cl['price']:,.2f}",
                    'Order Flow Catalysts': cl['side']
                })
            st.dataframe(pd.DataFrame(liq_rows), use_container_width=True, hide_index=True)

    st.divider()

# ── CHART ──────────────────────────────────────────────────────────────────
st.subheader(f"Price Chart — {symbol} / {timeframe}")
fig = render_chart(df_c, smc)
st.pyplot(fig); plt.close()
st.divider()

# ── 3-PANEL ANALYSIS ────────────────────────────────────────────────────────
a1, a2, a3 = st.columns(3)

with a1:
    st.subheader("Confluence Breakdown")
    for name, val in conf['layer_scores'].items():
        label = name.replace('_',' ').title()
        col   = "green" if val>0 else ("red" if val<0 else "gray")
        bar_w = int(min(100, abs(val)*1.5))
        bar_c = "#26a641" if val>0 else ("#da3633" if val<0 else "#666")
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;margin-bottom:3px;'>"
            f"<span style='font-size:.82rem;'>{label}</span>"
            f"<b style='color:{bar_c};'>{val:+.1f}</b></div>"
            f"<div style='background:#e0e0e0;border-radius:4px;height:5px;margin-bottom:8px;'>"
            f"<div style='background:{bar_c};width:{bar_w}%;height:5px;border-radius:4px;'></div></div>",
            unsafe_allow_html=True
        )
    norm = (conf['confluence_score']+100)/200
    st.progress(float(norm), text=f"Score: {conf['confluence_score']:+.1f} / 100")

with a2:
    st.subheader("ML Prediction")
    p_b = ml['p_bullish']*100
    p_s = ml['p_bearish']*100
    p_n = ml['p_neutral']*100

    def pbar(label, val, col):
        return (
            f"<div style='font-size:.88rem;margin-bottom:2px;'>{label}: <b style='color:{col};'>{val:.1f}%</b></div>"
            f"<div style='background:#ddd;height:8px;border-radius:4px;margin-bottom:8px;'>"
            f"<div style='background:{col};width:{val}%;height:8px;border-radius:4px;'></div></div>"
        )
    st.markdown(
        pbar("Bullish",p_b,"#26a641")+pbar("Bearish",p_s,"#da3633")+pbar("Neutral",p_n,"#888"),
        unsafe_allow_html=True
    )
    st.metric("Direction",            ml['predicted_direction'])
    st.metric("Model Confidence",     f"{ml['confidence_pct']}%")
    st.metric("Walk-Forward CV Acc",  f"{ml['cv_accuracy_pct']}%")
    st.metric("Expected Move",        f"{ml['expected_return_pct']:+.2f}%")

with a3:
    st.subheader("Smart Money (SMC)")
    st.metric("Market Structure",  smc['structure']['structure'])
    st.metric("Liquidity Sweep",   smc['structure'].get('liquidity_sweep','NONE'))
    st.metric("Open FVGs",         smc['open_fvgs_count'])
    st.metric("Order Blocks",      smc['order_blocks_count'])
    sh = smc['structure']['recent_swing_high']
    sl_v = smc['structure']['recent_swing_low']
    st.markdown(f"Swing High: **${sh:,.2f}** | Swing Low: **${sl_v:,.2f}**")
    for fvg in smc.get('active_fvgs',[])[:3]:
        col_h = "green" if 'BULLISH' in fvg['type'] else "red"
        st.markdown(f":{col_h}[{fvg['type'].replace('_',' ')}: ${fvg['bottom']:,.2f} — ${fvg['top']:,.2f}]")

st.divider()

# ── INDICATORS SUMMARY ──────────────────────────────────────────────────────
with st.expander("Technical Indicators Summary", expanded=False):
    ic1, ic2, ic3, ic4 = st.columns(4)
    with ic1:
        st.metric("RSI (14)",       f"{ind['rsi_14']}")
        st.metric("ADX (14)",       f"{ind['adx_14']}")
    with ic2:
        st.metric("SuperTrend",     ind['supertrend_dir'])
        st.metric("BB Squeeze",     "YES" if ind['bb_squeeze'] else "NO")
    with ic3:
        st.metric("EMA 20",         f"${ind['ema_20']:,.4f}")
        st.metric("EMA 50",         f"${ind['ema_50']:,.4f}")
    with ic4:
        st.metric("EMA 200",        f"${ind['ema_200']:,.4f}")
        st.metric("ATR (14)",       f"{ind['atr_14']:.4f}")

# ── TRADE SETUP ──────────────────────────────────────────────────────────────
st.subheader("Institutional Trade Setup")
if setup['status'] == 'ACTIVE_SETUP':
    sc1,sc2,sc3,sc4 = st.columns(4)
    with sc1:
        st.metric("Action", setup['action'])
        st.metric("Entry Zone", f"${setup['recommended_entry']:,.4f}")
    with sc2:
        st.metric("Stop Loss", f"${setup['stop_loss']:,.4f}", delta=f"-{setup['sl_distance_pct']}%", delta_color="inverse")
        st.metric("Risk Capital", f"${setup['risk_amount_usd']:,.2f}")
    with sc3:
        st.metric("TP1 (1:1.5 R:R)", f"${setup['tp1']:,.4f}", delta=f"+{setup['tp1_gain_pct']}%")
        st.metric("TP2 (1:2.5 R:R)", f"${setup['tp2']:,.4f}", delta=f"+{setup['tp2_gain_pct']}%")
    with sc4:
        st.metric("TP3 (Runner 1:4)", f"${setup['tp3']:,.4f}", delta=f"+{setup['tp3_gain_pct']}%")
        st.metric("Half-Kelly Alloc", f"{setup['half_kelly_pct']}% of portfolio")
else:
    st.info("No active setup — market neutral/consolidation. Capital preservation mode.")

st.divider()

# ── MULTI-EXCHANGE TABLE ─────────────────────────────────────────────────────
if asset_code == 'crypto':
    ec1, ec2 = st.columns([1.3, 1])
    with ec1:
        st.subheader("Multi-Exchange Live Prices")
        rows = []
        for ex, val in mkt.get('multi_exchange_prices',{}).items():
            p = val.get('price')
            rows.append({
                'Exchange': ex.upper(),
                'Price': f"${p:,.2f}" if p else "N/A",
                '24h %': f"{val.get('change_24h',0):+.2f}%" if val.get('change_24h') is not None else "—",
                'Status': val.get('status','N/A')
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with ec2:
        st.subheader("Arbitrage Scanner")
        if arb.get('arbitrage_available'):
            st.success(
                f"**ARBITRAGE DETECTED**\n\n"
                f"Buy: **{arb['cheapest_exchange'].upper()}** @ ${arb['cheapest_price']:,.2f}\n\n"
                f"Sell: **{arb['highest_exchange'].upper()}** @ ${arb['highest_price']:,.2f}\n\n"
                f"Net Spread: **{arb['net_spread_pct']:.3f}%** | Rating: **{arb.get('opportunity_rating')}**"
            )
        else:
            st.info("No profitable arbitrage detected.\nPrices within normal spread range.")
    st.divider()

# ── SIGNAL CHECKLIST ─────────────────────────────────────────────────────────
st.subheader("Signal Checklist")
cr1, cr2 = st.columns(2)
reasons = conf['reasons']
half = (len(reasons)+1)//2
for i, r in enumerate(reasons):
    col = cr1 if i < half else cr2
    if "(+" in r:
        col.markdown(f"<div class='layer-bull'>[+] {r}</div>", unsafe_allow_html=True)
    elif "(-" in r:
        col.markdown(f"<div class='layer-bear'>[-] {r}</div>", unsafe_allow_html=True)
    else:
        col.markdown(f"<div class='layer-neut'>[*] {r}</div>", unsafe_allow_html=True)

st.divider()
st.caption(
    f"Quant Terminal | {meta['symbol']} | {meta['market_mode'].upper()} | {meta['timeframe']} | "
    f"Updated: {meta['timestamp'][:19]} | Real Public APIs | Educational Use Only"
)
