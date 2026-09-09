# 100% Real Multi-Exchange Crypto & Forex Predictor 📈

A production-grade, multi-exchange quantitative predictor and trading signal intelligence system for Cryptocurrency, Forex, and Precious Metals. Powered exclusively by verified public APIs with **zero private API keys required**.

---

## 🌟 Key Capabilities

1. **Multi-Exchange Live Ingestion (Zero Keys Required):**
   - **Crypto:** Binance (Direct Spot REST failover cluster), Bybit, Coinbase, KuCoin, Gate.io, and CoinGecko.
   - **Forex & Commodities:** Yahoo Finance & Frankfurter European Central Bank (ECB) Reference API (`EUR/USD`, `GBP/USD`, `USD/JPY`, `AUD/USD`, `USD/CAD`, `USD/CHF`, `NZD/USD`, `XAU/USD Gold`, `XAG/USD Silver`).
   - Real-time order book depth imbalance, spread tracking, and cross-exchange arbitrage detector.

2. **Institutional Confluence Engine (5 Analytical Layers):**
   - **Layer 1: Smart Money Concepts (SMC):** 3-candle Fair Value Gaps (FVG), Institutional Order Blocks (OB), Liquidity Sweeps, and Market Structure Shifts (BOS / MSS).
   - **Layer 2: Multi-Factor Trend & Momentum:** EMA Ribbon (20/50/200), SuperTrend (ATR-adaptive), MACD Histogram acceleration, and ADX regime filter ($ADX > 25$).
   - **Layer 3: Statistical Mean Reversion & Volatility:** Multi-period RSI (Overbought/Oversold), Bollinger Bands %B and Bandwidth Squeeze, and Stochastic RSI.
   - **Layer 4: Machine Learning Ensemble:** Walk-forward calibrated Random Forest Classifier & Gradient Boosting Regressor predicting directional probabilities $P(\text{Bullish})$, $P(\text{Bearish})$, expected forward return %, and feature importances.
   - **Layer 5: Live Order Flow & Depth Imbalance:** Bid/Ask liquidity depth pressure ratio.

3. **Institutional Risk Management & Trade Setup:**
   - Directional Action: `STRONG BUY`, `BUY`, `NEUTRAL`, `SELL`, `STRONG SELL`.
   - Recommended Entry Level.
   - Volatility-based Stop Loss (ATR & Swing structure).
   - Multi-Tier Take Profit Targets: TP1 (1:1.5 R:R), TP2 (1:2.5 R:R), TP3 (1:4.0 R:R runner).
   - Conservative Half-Kelly Criterion and Position Size ($ and units) based on user portfolio risk.

4. **Dual Interface:**
   - **Interactive Web Terminal:** Beautiful dark-mode Streamlit dashboard with Plotly/Matplotlib candlesticks, SMC overlays, and live exchange tables.
   - **High-Performance CLI:** Rich-formatted terminal screener and single-asset predictor for quick analysis or automated scripting.

---

## 🚀 Quickstart Guide

### 1. Launch the Interactive Web Dashboard
```bash
cd C:\Users\ramis\.gemini\antigravity\scratch\crypto_forex_predictor
streamlit run app.py
```
Open `http://localhost:8501` in your browser to inspect live predictions, adjust risk parameters, and switch pairs.

---

### 2. Run the Command-Line Interface (CLI)

#### Analyze Bitcoin (BTC/USDT) on 1h timeframe:
```bash
python main.py --symbol BTC/USDT --asset-type crypto --timeframe 1h
```

#### Analyze Gold (XAU/USD):
```bash
python main.py --symbol XAU/USD --asset-type forex --timeframe 1h
```

#### Analyze Euro / US Dollar (EUR/USD):
```bash
python main.py --symbol EUR/USD --asset-type forex --timeframe 15m
```

#### Screen Top Crypto & Forex Assets at Once:
```bash
python main.py --screen
```

---

## 🧪 Running Automated Tests
```bash
python -m unittest tests/test_all.py
```
All unit tests validate data feeds, indicators, SMC algorithms, ML training pipelines, risk calculations, and live orchestrator execution.
