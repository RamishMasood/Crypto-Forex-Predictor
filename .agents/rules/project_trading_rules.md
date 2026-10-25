---
trigger: always_on
description: Critical trading geometry, UI stability, and learning journal rules for the Crypto Forex Predictor project.
---

# Project Trading & UI Architecture Rules

## 1. User Communication
- Communicate flexibly in English or Roman Urdu based on user preference and context.

## 2. Risk & Target Geometry (src/engine/risk_manager.py)
- **Golden SL Geometry**: Base SL is kept strictly at `1.80 * ATR` (with structural swing buffer of `0.20 * ATR`, min SL floor `1.50 * ATR`) per user mandate to prevent market noise wicks from hunting stops.
- **Precision TP1 Scalp Bank**: TP1 is calibrated to `0.55 * ATR` (raised from 0.38 ATR) to bank +45% higher cash profit on initial target hits and immediately trigger Auto-Breakeven, neutralizing the loss-to-win asymmetry while maintaining high 90%+ accuracy.
- **Mandatory 1:1+ Runner Geometry**:
  - TP2 must be at least `1.15 * risk_distance` (1:1+ Risk:Reward, effectively `2.07 * ATR`).
  - TP3 must be `2.20 * risk_distance` (macro expansion runner, effectively `3.96 * ATR`).
  - Never tie TP2 or TP3 to scalp TP1 multiples (e.g. `1.65 * tp1_dist`).
- **Capital Risk Control**: Dollar risk is strictly controlled via Batch Lot Size (e.g. `0.03` lots) and Max Dollar Risk Cap (`max_dollar_risk`), never by suffocating stop loss breathing room.

## 3. Streamlit Fragment Stability (app.py)
- Inside `@st.fragment` with periodic reruns (`run_every=N`), never render variable loops of native widgets (`st.container`, `st.columns`, `st.button`) directly in the fragment root when list count can change dynamically.
- Always render dynamic list collections (open positions, batch ledger) as single atomic HTML table/card blocks (`render_html(...)`), and provide fixed-count action bars (selectbox + buttons) to prevent Protobuf `'setIn'` index delta desynchronization (`Bad message format: Bad 'setIn' index X`).

## 4. Closed-Loop Trade Learning Journal
- The trade learning journal (`.trade_learning_journal.json`) must actively feed lessons back into the `AutonomousTraderEngine` to adaptively adjust win-probability filters and buffers for symbols with recent losses.

## 5. Master Strategy Improvement Journal (`docs/STRATEGY_IMPROVEMENT_JOURNAL.md`)
- Before altering or modifying any strategy code in `src/strategies/`, always consult [`docs/STRATEGY_IMPROVEMENT_JOURNAL.md`](file:///c:/Users/FATTANI%20COMPUTRS/Desktop/Crypto-Forex-Predictor/docs/STRATEGY_IMPROVEMENT_JOURNAL.md).
- **Mandatory Update Logging**: Whenever any strategy is improved, tuned, or updated, you MUST immediately log the change in `docs/STRATEGY_IMPROVEMENT_JOURNAL.md` with the date, problem/root cause, technical fix implemented, and expected outcome.
- Never regress or remove past optimizations (timeframe noise pruning, session killzones, EMA fanning, ADX thresholds, signal bar completion) that were added to eliminate historical losses.
