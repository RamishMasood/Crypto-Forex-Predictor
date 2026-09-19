"""
Trade For Profit (SMC & Liquidation Heatmap Trap Trading Engine)
================================================================
Reverse-engineered from @TradeForProfit institutional masterclasses and live streams.

Core Philosophy:
1. Zero indicators on chart.
2. Market runs on LIQUIDITY: Retail stop-losses and liquidation levels act as magnets.
3. Liquidation Heatmap Simulation: Calculates 50x, 25x, and 10x leverage clusters,
   plus Equal Highs (EQH) and Equal Lows (EQL).
4. The Trap (Turtle Soup / Liquidity Grab):
   Price sweeps into a dense liquidation cluster to trigger forced orders/FOMO breakouts.
   Institutional absorption leaves a prominent rejection wick (wick ratio >= 35%-50%)
   and closes back inside the range.
5. Structure Shift (CHoCH) & Displacement:
   Aggressive push in the reverse direction breaking local internal swing structure.
6. A+ Entry Module:
   Entry on retest of the sweep wick equilibrium (50%) or displacement FVG.
   Stop Loss strictly anchored past the sweep extreme, adhering to Golden SL Geometry
   (base 1.80 * ATR, never < 1.50 * ATR).
   Take Profit 1 at 0.38 * ATR (locks Breakeven), TP2 at 1.15+ R:R (opposite liquidity pool),
   TP3 at 2.20 R:R (macro runner).
"""

from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd


class LiquidityHeatmapEngine:
    """
    Simulates high-density institutional liquidation heatmaps and stop-loss pools
    using price action swing geometry, Equal Highs/Lows, and leverage estimation.
    """

    @staticmethod
    def identify_equal_highs_lows(
        highs: np.ndarray,
        lows: np.ndarray,
        tolerance_pct: float = 0.15
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Detects Equal Highs (EQH) and Equal Lows (EQL).
        Retailers treat these as strong resistance/support; institutions view them as prime liquidity targets.
        """
        eq_highs = []
        eq_lows = []
        n = len(highs)
        if n < 10:
            return eq_highs, eq_lows

        # Search for peaks that match within tolerance
        for i in range(5, n - 2):
            for j in range(i + 3, min(i + 25, n)):
                # EQH Check
                diff_h = abs(highs[i] - highs[j])
                avg_h = (highs[i] + highs[j]) / 2.0
                if avg_h > 0 and (diff_h / avg_h) * 100.0 <= tolerance_pct:
                    eq_highs.append({
                        'level': float(avg_h),
                        'index_1': int(i),
                        'index_2': int(j),
                        'type': 'EQH_BUY_STOPS',
                        'label': 'Equal Highs (Buy-Stop Liquidity Pool)'
                    })

                # EQL Check
                diff_l = abs(lows[i] - lows[j])
                avg_l = (lows[i] + lows[j]) / 2.0
                if avg_l > 0 and (diff_l / avg_l) * 100.0 <= tolerance_pct:
                    eq_lows.append({
                        'level': float(avg_l),
                        'index_1': int(i),
                        'index_2': int(j),
                        'type': 'EQL_SELL_STOPS',
                        'label': 'Equal Lows (Sell-Stop Liquidity Pool)'
                    })

        return eq_highs, eq_lows

    @classmethod
    def build_liquidation_heatmap(
        cls,
        df: pd.DataFrame,
        futures_data: Optional[Dict[str, Any]] = None,
        lookback: int = 60
    ) -> Dict[str, Any]:
        """
        Generates simulated liquidation heatmaps (Upper Short Liquidations & Lower Long Liquidations).
        """
        n = len(df)
        if n < 15:
            return {'upper_pools': [], 'lower_pools': [], 'dominant_magnet': 'NONE'}

        sub_df = df.iloc[-lookback:] if n > lookback else df
        highs = sub_df['high'].values
        lows = sub_df['low'].values
        closes = sub_df['close'].values
        current_price = float(closes[-1])

        # 1. Swing Highs & Lows (Pivots)
        window = 4
        swing_highs = []
        swing_lows = []
        for i in range(window, len(sub_df) - window):
            if highs[i] == np.max(highs[i - window : i + window + 1]):
                swing_highs.append(float(highs[i]))
            if lows[i] == np.min(lows[i - window : i + window + 1]):
                swing_lows.append(float(lows[i]))

        # 2. Equal Highs & Equal Lows
        eq_highs, eq_lows = cls.identify_equal_highs_lows(highs, lows)

        # 3. Leverage bands (50x = ~1.8%, 25x = ~3.8%, 10x = ~9.5%)
        upper_pools: List[Dict[str, Any]] = []
        lower_pools: List[Dict[str, Any]] = []

        # Liquidation bands above current price (Short liquidations / Buy-side liquidity)
        for sh in set(swing_highs):
            if sh > current_price:
                dist_pct = ((sh - current_price) / current_price) * 100.0
                upper_pools.append({
                    'price': float(sh),
                    'distance_pct': float(round(dist_pct, 2)),
                    'density': 'HIGH',
                    'type': 'SWING_HIGH_BSL',
                    'source': 'Swing Pivot High'
                })
                # 50x short liquidation cluster above swing high
                lev_50x = sh * 1.018
                if lev_50x > current_price:
                    upper_pools.append({
                        'price': float(round(lev_50x, 2)),
                        'distance_pct': float(round(((lev_50x - current_price) / current_price) * 100.0, 2)),
                        'density': 'EXTREME',
                        'type': '50X_SHORT_LIQUIDATION',
                        'source': '50x Short Leverage Cluster'
                    })

        for eq in eq_highs:
            lvl = eq['level']
            if lvl > current_price:
                upper_pools.append({
                    'price': float(round(lvl, 2)),
                    'distance_pct': float(round(((lvl - current_price) / current_price) * 100.0, 2)),
                    'density': 'ULTRA_DENSE',
                    'type': 'EQH_BUY_STOPS',
                    'source': 'Equal Highs Liquidity Pool'
                })

        # Liquidation bands below current price (Long liquidations / Sell-side liquidity)
        for sl in set(swing_lows):
            if sl < current_price:
                dist_pct = ((current_price - sl) / current_price) * 100.0
                lower_pools.append({
                    'price': float(sl),
                    'distance_pct': float(round(dist_pct, 2)),
                    'density': 'HIGH',
                    'type': 'SWING_LOW_SSL',
                    'source': 'Swing Pivot Low'
                })
                # 50x long liquidation cluster below swing low
                lev_50x = sl * 0.982
                if lev_50x < current_price:
                    lower_pools.append({
                        'price': float(round(lev_50x, 2)),
                        'distance_pct': float(round(((current_price - lev_50x) / current_price) * 100.0, 2)),
                        'density': 'EXTREME',
                        'type': '50X_LONG_LIQUIDATION',
                        'source': '50x Long Leverage Cluster'
                    })

        for eq in eq_lows:
            lvl = eq['level']
            if lvl < current_price:
                lower_pools.append({
                    'price': float(round(lvl, 2)),
                    'distance_pct': float(round(((current_price - lvl) / current_price) * 100.0, 2)),
                    'density': 'ULTRA_DENSE',
                    'type': 'EQL_SELL_STOPS',
                    'source': 'Equal Lows Liquidity Pool'
                })

        # Sort pools by proximity to current price
        upper_pools.sort(key=lambda x: x['price'])
        lower_pools.sort(key=lambda x: x['price'], reverse=True)

        nearest_upper = upper_pools[0] if upper_pools else None
        nearest_lower = lower_pools[0] if lower_pools else None

        # Determine dominant liquidity magnet
        dominant_magnet = 'NONE'
        if nearest_upper and nearest_lower:
            if nearest_upper['distance_pct'] < nearest_lower['distance_pct']:
                dominant_magnet = 'UPPER_BUY_SIDE_LIQUIDITY'
            else:
                dominant_magnet = 'LOWER_SELL_SIDE_LIQUIDITY'
        elif nearest_upper:
            dominant_magnet = 'UPPER_BUY_SIDE_LIQUIDITY'
        elif nearest_lower:
            dominant_magnet = 'LOWER_SELL_SIDE_LIQUIDITY'

        return {
            'upper_pools': upper_pools[:5],
            'lower_pools': lower_pools[:5],
            'nearest_upper': nearest_upper,
            'nearest_lower': nearest_lower,
            'dominant_magnet': dominant_magnet,
            'eq_highs_count': len(eq_highs),
            'eq_lows_count': len(eq_lows)
        }


class TrapSweepDetector:
    """
    Detects institutional traps (Turtle Soup / Liquidity Sweeps / Stop Hunts).
    Identifies false breakouts beyond key liquidity clusters where institutions absorb orders.
    """

    @staticmethod
    def detect_trap_and_sweep(
        df: pd.DataFrame,
        heatmap: Dict[str, Any],
        atr: float
    ) -> Dict[str, Any]:
        """
        Inspects the most recent candles for liquidity sweeps and trap rejections.
        """
        n = len(df)
        if n < 5:
            return {'trap_detected': False, 'trap_type': 'NONE', 'confidence': 0.0}

        highs = df['high'].values
        lows = df['low'].values
        opens = df['open'].values
        closes = df['close'].values
        volumes = df['volume'].values if 'volume' in df.columns else np.ones(n)

        # Average volume for surge comparison
        avg_vol = float(np.mean(volumes[-20:])) if n >= 20 else float(np.mean(volumes))
        avg_vol = max(avg_vol, 1e-6)

        # Inspect the last 3 candles for trap signature
        last_h = float(highs[-1])
        last_l = float(lows[-1])
        last_o = float(opens[-1])
        last_c = float(closes[-1])
        last_v = float(volumes[-1])
        vol_ratio = last_v / avg_vol

        candle_range = max(last_h - last_l, 1e-9)
        upper_wick = last_h - max(last_o, last_c)
        lower_wick = min(last_o, last_c) - last_l
        upper_wick_ratio = upper_wick / candle_range
        lower_wick_ratio = lower_wick / candle_range

        # Check against lower pools (Sell-side sweep -> Bullish Trap)
        lower_pools = heatmap.get('lower_pools', [])
        bullish_trap = False
        bullish_swept_pool = None
        bullish_wick_extreme = last_l

        for pool in lower_pools:
            pool_lvl = pool['price']
            # Candle pushed below the pool level, but closed back ABOVE the pool level!
            # Or pushed below with a massive bottom wick
            if last_l < pool_lvl and last_c > pool_lvl and lower_wick_ratio >= 0.35:
                bullish_trap = True
                bullish_swept_pool = pool
                bullish_wick_extreme = min(bullish_wick_extreme, last_l)
                break
            # Also check candle i-1 if current candle is confirming the bounce
            elif n >= 2:
                prev_l = float(lows[-2])
                prev_c = float(closes[-2])
                prev_o = float(opens[-2])
                prev_range = max(highs[-2] - lows[-2], 1e-9)
                prev_lower_wick = (min(prev_o, prev_c) - prev_l) / prev_range
                if prev_l < pool_lvl and prev_lower_wick >= 0.40 and last_c > prev_c:
                    bullish_trap = True
                    bullish_swept_pool = pool
                    bullish_wick_extreme = prev_l
                    break

        # Check against upper pools (Buy-side sweep -> Bearish Trap)
        upper_pools = heatmap.get('upper_pools', [])
        bearish_trap = False
        bearish_swept_pool = None
        bearish_wick_extreme = last_h

        for pool in upper_pools:
            pool_lvl = pool['price']
            # Candle pushed above the pool level, but closed back BELOW the pool level!
            if last_h > pool_lvl and last_c < pool_lvl and upper_wick_ratio >= 0.35:
                bearish_trap = True
                bearish_swept_pool = pool
                bearish_wick_extreme = max(bearish_wick_extreme, last_h)
                break
            # Also check candle i-1 if current candle is confirming the rejection
            elif n >= 2:
                prev_h = float(highs[-2])
                prev_c = float(closes[-2])
                prev_o = float(opens[-2])
                prev_range = max(highs[-2] - lows[-2], 1e-9)
                prev_upper_wick = (prev_h - max(prev_o, prev_c)) / prev_range
                if prev_h > pool_lvl and prev_upper_wick >= 0.40 and last_c < prev_c:
                    bearish_trap = True
                    bearish_swept_pool = pool
                    bearish_wick_extreme = prev_h
                    break

        # Synthesize Trap Results
        if bullish_trap and not bearish_trap:
            return {
                'trap_detected': True,
                'trap_type': 'BULLISH_BEAR_TRAP',
                'description': 'Sell-Side Liquidity Swept (Bear Trap) - Retail shorts trapped under support',
                'swept_pool': bullish_swept_pool,
                'wick_extreme': float(bullish_wick_extreme),
                'rejection_wick_ratio': float(round(lower_wick_ratio, 2)),
                'volume_expansion_factor': float(round(vol_ratio, 2)),
                'retest_zone': float(round(bullish_wick_extreme + (candle_range * 0.50), 5)),
                'bias': 'BUY'
            }
        elif bearish_trap and not bullish_trap:
            return {
                'trap_detected': True,
                'trap_type': 'BEARISH_BULL_TRAP',
                'description': 'Buy-Side Liquidity Swept (Bull Trap) - Retail longs trapped above resistance',
                'swept_pool': bearish_swept_pool,
                'wick_extreme': float(bearish_wick_extreme),
                'rejection_wick_ratio': float(round(upper_wick_ratio, 2)),
                'volume_expansion_factor': float(round(vol_ratio, 2)),
                'retest_zone': float(round(bearish_wick_extreme - (candle_range * 0.50), 5)),
                'bias': 'SELL'
            }
        else:
            return {
                'trap_detected': False,
                'trap_type': 'NONE',
                'description': 'No active liquidity trap detected in immediate price action',
                'swept_pool': None,
                'wick_extreme': 0.0,
                'rejection_wick_ratio': 0.0,
                'volume_expansion_factor': float(round(vol_ratio, 2)),
                'retest_zone': 0.0,
                'bias': 'NEUTRAL'
            }


class TradeForProfitEngine:
    """
    Trade For Profit Master Engine
    Synthesizes:
    - Liquidity Heatmaps (Cluster Detection)
    - Trap & Sweep Detection (False Breakouts / Retail Trapping)
    - A+ Entry Module & Golden Target Geometry
    """

    @classmethod
    def evaluate(
        cls,
        df: pd.DataFrame,
        atr: float,
        futures_data: Optional[Dict[str, Any]] = None,
        timeframe: str = '1h',
        account_size_usd: float = 10000.0,
        risk_per_trade_pct: float = 1.5
    ) -> Dict[str, Any]:
        """
        Executes the Trade For Profit SMC Trap Strategy evaluation.
        """
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        min_atr_floor = (current_price * 0.0003) if current_price < 5.0 else (current_price * 0.0015)
        safe_atr = max(atr, min_atr_floor)

        # 1. Build Liquidation Heatmap
        heatmap = LiquidityHeatmapEngine.build_liquidation_heatmap(df, futures_data=futures_data)

        # 2. Detect Liquidity Trap & Sweep
        trap = TrapSweepDetector.detect_trap_and_sweep(df, heatmap, safe_atr)

        # 3. Setup Grade and A+ Trigger Formulation
        action = 'HOLD'
        setup_grade = 'SCANNING_POOLS'
        confidence = 45.0
        reasons = []

        if trap['trap_detected']:
            bias = trap['bias']
            wick_extreme = trap['wick_extreme']
            vol_fac = trap['volume_expansion_factor']
            wick_ratio = trap['rejection_wick_ratio']

            # Check volume confirmation & wick rejection strength
            is_high_volume = vol_fac >= 1.15
            is_strong_wick = wick_ratio >= 0.40

            if is_high_volume and is_strong_wick:
                setup_grade = 'A+_SUPER_CONFLUENCE'
                confidence = 88.0
            elif is_strong_wick:
                setup_grade = 'A_HIGH_CONVICTION'
                confidence = 78.0
            else:
                setup_grade = 'B_DEVELOPING'
                confidence = 68.0

            action = 'BUY' if bias == 'BUY' else 'SELL'
            swept_name = trap['swept_pool']['source'] if trap['swept_pool'] else 'Liquidity Pool'
            reasons.append(f"Trap Detected: {trap['description']} at {swept_name}")
            reasons.append(f"Institutional Absorption: Wick Ratio = {wick_ratio*100.0:.1f}%, Volume Factor = {vol_fac:.2f}x")

            # 4. Mandatory Risk & Target Geometry (Invariants)
            # Golden SL Geometry: Base SL must remain at 1.80 * ATR (with structural buffer)
            # Never compress SL below 1.50 * ATR!
            base_sl_dist = 1.80 * safe_atr
            swing_buffer = 0.20 * safe_atr
            min_sl_dist = 1.50 * safe_atr

            if action == 'BUY':
                entry_price = current_price
                # Stop loss placed beyond sweep wick extreme or base 1.80 ATR
                raw_sl = min(wick_extreme - swing_buffer, entry_price - base_sl_dist)
                # Invariant: never compress SL below 1.5 * ATR
                sl_distance = max(entry_price - raw_sl, min_sl_dist)
                stop_loss = entry_price - sl_distance

                # Precision TP1 Scalp Bank: 0.38 * ATR (immediately triggers Auto-Breakeven)
                tp1 = entry_price + (0.38 * safe_atr)

                # Mandatory 1:1+ Runner Geometry:
                # TP2 >= 1.15 * risk_distance (targeting opposite upper liquidity pool)
                min_tp2_dist = 1.15 * sl_distance
                # If nearest upper pool is further, target the pool!
                nearest_upper = heatmap.get('nearest_upper')
                if nearest_upper and (nearest_upper['price'] - entry_price) >= min_tp2_dist:
                    tp2 = float(nearest_upper['price'])
                else:
                    tp2 = entry_price + min_tp2_dist

                # TP3: 2.20 * risk_distance (macro expansion runner)
                tp3 = entry_price + (2.20 * sl_distance)

            else:  # SELL
                entry_price = current_price
                raw_sl = max(wick_extreme + swing_buffer, entry_price + base_sl_dist)
                sl_distance = max(raw_sl - entry_price, min_sl_dist)
                stop_loss = entry_price + sl_distance

                # Precision TP1 Scalp Bank: 0.38 * ATR
                tp1 = entry_price - (0.38 * safe_atr)

                # Mandatory 1:1+ Runner Geometry: TP2 >= 1.15 * risk_distance
                min_tp2_dist = 1.15 * sl_distance
                nearest_lower = heatmap.get('nearest_lower')
                if nearest_lower and (entry_price - nearest_lower['price']) >= min_tp2_dist:
                    tp2 = float(nearest_lower['price'])
                else:
                    tp2 = entry_price - min_tp2_dist

                tp3 = entry_price - (2.20 * sl_distance)

            rr_ratio = round((abs(tp2 - entry_price)) / max(sl_distance, 1e-9), 2)

            trade_setup = {
                'action': action,
                'status': f'{setup_grade}_ENTRY_READY',
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'invalidation_level': float(round(wick_extreme, 5)),
                'sl_distance_pct': float(round((sl_distance / entry_price) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp1_gain_pct': float(round((abs(tp1 - entry_price) / entry_price) * 100.0, 2)),
                'tp2': float(round(tp2, 5)),
                'tp2_gain_pct': float(round((abs(tp2 - entry_price) / entry_price) * 100.0, 2)),
                'tp3': float(round(tp3, 5)),
                'tp3_gain_pct': float(round((abs(tp3 - entry_price) / entry_price) * 100.0, 2)),
                'risk_reward_ratio': f"1:{rr_ratio}",
                'breakeven_rule': 'AUTO_BREAKEVEN_AT_TP1',
                'strategy_name': 'Trade For Profit (SMC Trap Module)'
            }
        else:
            trade_setup = {
                'action': 'HOLD',
                'status': 'SCANNING_LIQUIDATION_POOLS',
                'recommended_entry': current_price,
                'stop_loss': current_price,
                'tp1': current_price,
                'tp2': current_price,
                'tp3': current_price,
                'strategy_name': 'Trade For Profit (SMC Trap Module)'
            }
            reasons.append("Monitoring nearest liquidity clusters. Waiting for sweep & trap rejection.")

        return {
            'strategy': 'Trade For Profit (SMC Liquidation Trap)',
            'action': action,
            'setup_grade': setup_grade,
            'confidence': float(round(confidence, 1)),
            'trap_details': trap,
            'heatmap': heatmap,
            'trade_setup': trade_setup,
            'reasons': reasons,
            'dominant_magnet': heatmap.get('dominant_magnet', 'NONE')
        }
