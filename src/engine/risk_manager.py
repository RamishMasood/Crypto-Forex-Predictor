"""
Institutional Risk Management and Trade Setup Generator
Calculates dynamic Stop-Loss (ATR & Swing-based), multi-tier Take-Profit targets (TP1, TP2, TP3),
Risk-to-Reward ratios, and Kelly Criterion position sizing.
"""

from typing import Dict, Any, Optional

class RiskManager:
    """
    Computes institutional risk parameters and structured trade setups.
    """

    @staticmethod
    def generate_trade_setup(
        current_price: float,
        action: str,
        atr: float,
        recent_swing_high: Optional[float] = None,
        recent_swing_low: Optional[float] = None,
        fvg_zone: Optional[Dict[str, Any]] = None,
        account_size_usd: float = 10000.0,
        risk_per_trade_pct: float = 1.5,
        win_probability: float = 0.55
    ) -> Dict[str, Any]:
        """
        Generates precise entry, stop loss, 3 take profit targets, and position sizing.
        """
        if action in ['NEUTRAL', 'HOLD']:
            return {
                'action': 'NEUTRAL',
                'status': 'NO_TRADE_SETUP',
                'recommended_entry': current_price,
                'stop_loss': current_price,
                'tp1': current_price,
                'tp2': current_price,
                'tp3': current_price,
                'risk_reward_ratio': '0:0',
                'risk_amount_usd': 0.0,
                'suggested_position_usd': 0.0,
                'suggested_units': 0.0,
                'kelly_fraction_pct': 0.0
            }

        atr = max(atr, current_price * 0.002) # Fallback minimum ATR
        is_long = 'BUY' in action

        # Entry Price determination (current price or optimal pullback)
        entry_price = current_price

        # Stop Loss determination
        if is_long:
            atr_sl = entry_price - (1.8 * atr)
            # If recent swing low is available and sensible, use the structural low
            if recent_swing_low and (entry_price > recent_swing_low) and ((entry_price - recent_swing_low) < 3.0 * atr):
                stop_loss = recent_swing_low - (0.2 * atr)
            else:
                stop_loss = atr_sl
            risk_per_unit = max(entry_price - stop_loss, entry_price * 0.002)

            # Take Profit targets (1:1.5, 1:2.5, 1:4.0 R:R)
            tp1 = entry_price + (1.5 * risk_per_unit)
            tp2 = entry_price + (2.5 * risk_per_unit)
            tp3 = entry_price + (4.0 * risk_per_unit)
        else:
            atr_sl = entry_price + (1.8 * atr)
            # If recent swing high is available and sensible, use the structural high
            if recent_swing_high and (recent_swing_high > entry_price) and ((recent_swing_high - entry_price) < 3.0 * atr):
                stop_loss = recent_swing_high + (0.2 * atr)
            else:
                stop_loss = atr_sl
            risk_per_unit = max(stop_loss - entry_price, entry_price * 0.002)

            # Take Profit targets
            tp1 = entry_price - (1.5 * risk_per_unit)
            tp2 = entry_price - (2.5 * risk_per_unit)
            tp3 = entry_price - (4.0 * risk_per_unit)

        # Position Sizing
        risk_capital_usd = account_size_usd * (risk_per_trade_pct / 100.0)
        units = risk_capital_usd / risk_per_unit if risk_per_unit > 0 else 0.0
        position_size_usd = units * entry_price

        # Half-Kelly sizing: f = (p * b - q) / b
        b = 2.5 # Using TP2 payoff ratio
        p = max(0.40, min(0.85, win_probability))
        q = 1.0 - p
        full_kelly = max(0.0, (p * b - q) / b)
        half_kelly_pct = (full_kelly * 0.5) * 100.0 # Conservative Half-Kelly

        return {
            'action': action,
            'status': 'ACTIVE_SETUP',
            'current_price': round(current_price, 5),
            'recommended_entry': round(entry_price, 5),
            'stop_loss': round(stop_loss, 5),
            'sl_distance_pct': round((abs(entry_price - stop_loss) / entry_price) * 100.0, 2),
            'tp1': round(tp1, 5),
            'tp1_gain_pct': round((abs(tp1 - entry_price) / entry_price) * 100.0, 2),
            'tp2': round(tp2, 5),
            'tp2_gain_pct': round((abs(tp2 - entry_price) / entry_price) * 100.0, 2),
            'tp3': round(tp3, 5),
            'tp3_gain_pct': round((abs(tp3 - entry_price) / entry_price) * 100.0, 2),
            'risk_reward_ratio': '1 : 2.5 (Target TP2)',
            'risk_amount_usd': round(risk_capital_usd, 2),
            'suggested_position_usd': round(position_size_usd, 2),
            'suggested_units': round(units, 4),
            'half_kelly_pct': round(half_kelly_pct, 1)
        }
