"""
Higher Timeframe (HTF) Trend Confluence Checker.
Ensures lower timeframe execution setups (15m, 30m, 1h) strictly align
with the dominant higher timeframe institutional direction (1h, 4h, 1d)
to prevent counter-trend traps and boost runner completion rates.
"""

from typing import Tuple, Dict, Any, Optional
from datetime import datetime, timezone
import numpy as np
import pandas as pd

class HTFConfluenceChecker:
    """
    Validates trade setup alignment with the immediate higher timeframe.
    """

    HTF_MAP = {
        "1m": "15m",
        "3m": "30m",
        "5m": "1h",
        "15m": "1h",
        "30m": "4h",
        "1h": "4h",
        "4h": "1d",
        "1d": "1w"
    }

    MT5_TF_ENUMS = {}

    @classmethod
    def _init_mt5_enums(cls):
        if not cls.MT5_TF_ENUMS:
            try:
                import MetaTrader5 as mt5
                cls.MT5_TF_ENUMS = {
                    "1m": mt5.TIMEFRAME_M1,
                    "3m": mt5.TIMEFRAME_M3,
                    "5m": mt5.TIMEFRAME_M5,
                    "15m": mt5.TIMEFRAME_M15,
                    "30m": mt5.TIMEFRAME_M30,
                    "1h": mt5.TIMEFRAME_H1,
                    "4h": mt5.TIMEFRAME_H4,
                    "1d": mt5.TIMEFRAME_D1
                }
            except Exception:
                pass

    @classmethod
    def get_htf_timeframe(cls, current_tf: str) -> str:
        """Returns the higher timeframe string for a given execution timeframe."""
        clean_tf = current_tf.lower().strip()
        return cls.HTF_MAP.get(clean_tf, "4h")

    @classmethod
    def check_alignment(
        cls,
        symbol: str,
        current_tf: str,
        direction: str,
        df_htf: Optional[pd.DataFrame] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates if direction (BUY/SELL) matches HTF trend.
        If df_htf is provided, uses it. Otherwise attempts to pull from MT5.
        Returns: (is_aligned: bool, reason: str, details: dict)
        """
        htf_tf = cls.get_htf_timeframe(current_tf)
        clean_dir = direction.upper().strip()

        # If df_htf not provided, try to fetch from MT5
        if df_htf is None or len(df_htf) < 20:
            cls._init_mt5_enums()
            try:
                import MetaTrader5 as mt5
                htf_enum = cls.MT5_TF_ENUMS.get(htf_tf)
                if htf_enum is not None:
                    rates = mt5.copy_rates_from_pos(symbol, htf_enum, 0, 100)
                    if rates is not None and len(rates) >= 20:
                        df_htf = pd.DataFrame(rates)
            except Exception:
                pass

        # If still no data, pass through with warning
        if df_htf is None or len(df_htf) < 15:
            return True, f"HTF ({htf_tf}) data unavailable - pass by default", {
                "htf": htf_tf,
                "status": "NO_DATA",
                "aligned": True
            }

        close_col = 'close' if 'close' in df_htf.columns else 'Close'
        closes = df_htf[close_col].values.astype(float)
        last_close = float(closes[-1])

        # Calculate EMA20 & EMA50
        series = pd.Series(closes)
        ema20 = float(series.ewm(span=20, adjust=False).mean().iloc[-1])
        has_ema50 = len(series) >= 50
        ema50 = float(series.ewm(span=50, adjust=False).mean().iloc[-1]) if has_ema50 else ema20

        # Bullish HTF condition: price must be >= EMA20, and if EMA50 available, EMA20 >= EMA50
        # Bearish HTF condition: price must be <= EMA20, and if EMA50 available, EMA20 <= EMA50
        if has_ema50:
            is_bullish = (last_close >= ema20) and (ema20 >= ema50)
            is_bearish = (last_close <= ema20) and (ema20 <= ema50)
        else:
            is_bullish = (last_close >= ema20)
            is_bearish = (last_close <= ema20)

        details = {
            "htf": htf_tf,
            "last_close": round(last_close, 5),
            "ema20": round(ema20, 5),
            "ema50": round(ema50, 5),
            "is_bullish": is_bullish,
            "is_bearish": is_bearish
        }

        if clean_dir == "BUY":
            if last_close < ema20:
                return False, f"HTF ({htf_tf}) Conflict: Price ({last_close:.4f}) below EMA20 ({ema20:.4f})", details
            if not is_bullish:
                return False, f"HTF ({htf_tf}) Conflict: EMA20 ({ema20:.4f}) below EMA50 ({ema50:.4f}) in Bearish Structure", details
            return True, f"HTF ({htf_tf}) Trend Confirmed: Price ({last_close:.4f}) >= EMA20 ({ema20:.4f}) & EMA20 >= EMA50", details
        elif clean_dir == "SELL":
            if last_close > ema20:
                return False, f"HTF ({htf_tf}) Conflict: Price ({last_close:.4f}) above EMA20 ({ema20:.4f}) in Bullish Structure", details
            if not is_bearish:
                return False, f"HTF ({htf_tf}) Conflict: EMA20 ({ema20:.4f}) above EMA50 ({ema50:.4f}) in Bullish Structure", details
            return True, f"HTF ({htf_tf}) Trend Confirmed: Price ({last_close:.4f}) <= EMA20 ({ema20:.4f}) & EMA20 <= EMA50", details
        else:
            return True, "Neutral direction", details
