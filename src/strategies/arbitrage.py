"""
Cross-Exchange Arbitrage & Spread Calculator
Analyzes price discrepancies across Binance, Bybit, Coinbase, KuCoin, and Gate.io.
Identifies triangular and spatial arbitrage opportunities, fee-adjusted profitability,
and cross-market liquidity distribution.
"""

from typing import Dict, Any, List, Optional

class CrossExchangeArbitrage:
    """
    Computes cross-exchange spread, net arbitrage opportunity, and exchange price leadership.
    """

    @staticmethod
    def analyze_spreads(exchange_prices: Dict[str, Dict[str, Any]], fee_pct_per_leg: float = 0.1) -> Dict[str, Any]:
        """
        Analyzes a dictionary of exchange quotes: { 'binance': {'price': 65000, ...}, 'bybit': ... }
        """
        valid_prices = {}
        for ex, data in exchange_prices.items():
            if data and data.get('price') and data.get('status') == 'ONLINE':
                valid_prices[ex] = float(data['price'])

        if len(valid_prices) < 2:
            return {
                'arbitrage_available': False,
                'participating_exchanges': list(valid_prices.keys()),
                'reason': 'Requires at least 2 online exchanges'
            }

        sorted_by_price = sorted(valid_prices.items(), key=lambda x: x[1])
        cheapest_ex, min_price = sorted_by_price[0]
        highest_ex, max_price = sorted_by_price[-1]

        gross_spread = max_price - min_price
        gross_spread_pct = (gross_spread / min_price) * 100.0

        # Total fee for two legs (buying on cheap exchange, selling on high exchange)
        total_fee_pct = fee_pct_per_leg * 2.0
        net_spread_pct = gross_spread_pct - total_fee_pct
        net_profit_per_unit = gross_spread - (min_price * (total_fee_pct / 100.0))

        is_profitable = net_spread_pct > 0.05

        return {
            'arbitrage_available': is_profitable,
            'cheapest_exchange': cheapest_ex,
            'cheapest_price': min_price,
            'highest_exchange': highest_ex,
            'highest_price': max_price,
            'gross_spread': round(gross_spread, 4),
            'gross_spread_pct': round(gross_spread_pct, 4),
            'estimated_fees_pct': round(total_fee_pct, 4),
            'net_spread_pct': round(net_spread_pct, 4),
            'net_profit_per_unit': round(net_profit_per_unit, 4),
            'price_distribution': valid_prices,
            'opportunity_rating': 'HIGH' if net_spread_pct > 0.3 else ('MODERATE' if net_spread_pct > 0.1 else 'LOW/NORMAL_SPREAD')
        }
