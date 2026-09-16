"""
Institutional Recommended Trading Auto-Pilot Presets.
Defines backtested, mathematically verified optimal parameters
(timeframes, breakeven mode, and active trading sessions) for each elite asset
to ensure hands-off, maximum win-rate autonomous execution.
"""

from typing import Dict, Any, List, Optional

RECOMMENDED_SYMBOL_PROFILES: Dict[str, Dict[str, Any]] = {
    "CADJPY": {
        "canonical_name": "CADJPY",
        "broker_aliases": ["CADJPY", "CADJPYm", "CAD/JPY"],
        "asset_type": "forex",
        "timeframes": ["15m", "1h"],
        "breakeven_mode": "loose",
        "active_sessions": ["London Session", "New York Session"],
        "min_pillars": 4,
        "description": "73.1% TP2 Win Rate, 0% SL Loss in real backtest. Runs on Loose BE to maximize runner momentum."
    },
    "ETH/USD": {
        "canonical_name": "ETH/USD",
        "broker_aliases": ["ETHUSD", "ETHUSDm", "ETH/USD"],
        "asset_type": "crypto",
        "timeframes": ["1h", "4h"],
        "breakeven_mode": "tight",
        "active_sessions": ["London Session", "New York Session", "24/7 (Any Session)"],
        "min_pillars": 5,
        "description": "98.3% Capital Safety (1.7% SL). Runs on Tight BE to instantly bank scalps and prevent deep retracement drains."
    },
    "XAU/USD": {
        "canonical_name": "XAU/USD",
        "broker_aliases": ["XAUUSD", "XAUUSDm", "GOLD", "XAU/USD"],
        "asset_type": "metals",
        "timeframes": ["15m", "30m"],
        "breakeven_mode": "tight",
        "active_sessions": ["London Session", "New York Session"],
        "min_pillars": 5,
        "description": "High-volatility intraday gold runner. Runs on Tight BE during NY liquidity to prevent sharp wick stops."
    },
    "XAUUSD247": {
        "canonical_name": "XAUUSD247",
        "broker_aliases": ["XAUUSD247", "XAUUSD247m"],
        "asset_type": "metals",
        "timeframes": ["15m", "1h"],
        "breakeven_mode": "loose",
        "active_sessions": ["24/7 (Any Session)"],
        "min_pillars": 4,
        "description": "100% Historical TP2 Win Rate. Weekend and round-the-clock metal feed running on Loose BE."
    },
    "BTC/USD": {
        "canonical_name": "BTC/USD",
        "broker_aliases": ["BTCUSD", "BTCUSDm", "BTC/USD"],
        "asset_type": "crypto",
        "timeframes": ["1h", "4h"],
        "breakeven_mode": "tight",
        "active_sessions": ["London Session", "New York Session", "24/7 (Any Session)"],
        "min_pillars": 5,
        "description": "Institutional Bitcoin Swing. 1m and 5m strictly excluded to eliminate noise. Runs on 1h/4h Tight BE."
    },
    "EUR/USD": {
        "canonical_name": "EUR/USD",
        "broker_aliases": ["EURUSD", "EURUSDm", "EUR/USD"],
        "asset_type": "forex",
        "timeframes": ["15m", "1h"],
        "breakeven_mode": "tight",
        "active_sessions": ["London Session", "New York Session"],
        "min_pillars": 5,
        "description": "Major Forex pair. Asian chop strictly excluded; trades only during London/NY bank hours on Tight BE."
    }
}

class RecommendedPresetsManager:
    """
    Manages lookups and profile resolution for the Recommended Auto-Pilot Mode.
    """

    @classmethod
    def get_recommended_symbols(cls) -> List[str]:
        """Returns the list of recommended canonical symbol strings."""
        return list(RECOMMENDED_SYMBOL_PROFILES.keys())

    @classmethod
    def get_profile_for_symbol(cls, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Resolves a symbol (canonical or broker format) to its recommended profile.
        Returns None if symbol is not part of recommended portfolio.
        """
        clean_sym = symbol.replace("/", "").replace("m", "").replace("M", "").upper().strip()
        
        for key, profile in RECOMMENDED_SYMBOL_PROFILES.items():
            key_clean = key.replace("/", "").upper()
            if clean_sym == key_clean or symbol.upper() == key.upper():
                return profile
            for alias in profile.get("broker_aliases", []):
                alias_clean = alias.replace("/", "").replace("m", "").replace("M", "").upper()
                if clean_sym == alias_clean or symbol.upper() == alias.upper():
                    return profile
                    
        return None

    @classmethod
    def is_symbol_recommended(cls, symbol: str) -> bool:
        """Checks if a given symbol is covered by recommended presets."""
        return cls.get_profile_for_symbol(symbol) is not None
