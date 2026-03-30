"""
Profit Target Calculator Module

Calculates realistic take-profit prices based on historical recovery patterns.
"""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..indicators.technical import TechnicalIndicators


class ProfitTargetCalculator:
    """Calculate take-profit recommendations based on historical data."""

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_oversold: float = 30,
        recovery_lookback_days: int = 365,
        recent_high_lookback: int = 20,
        max_take_profit_pct: float = 0.15
    ):
        """
        Initialize the profit target calculator.

        Args:
            rsi_period: Period for RSI calculation
            rsi_oversold: RSI threshold for oversold condition
            recovery_lookback_days: Days to analyze for historical recoveries
            recent_high_lookback: Bars to look back for recent high
            max_take_profit_pct: Maximum take profit percentage cap
        """
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.recovery_lookback_days = recovery_lookback_days
        self.recent_high_lookback = recent_high_lookback
        self.max_take_profit_pct = max_take_profit_pct

    def calculate_take_profit(
        self,
        data: pd.DataFrame,
        current_price: float
    ) -> Dict:
        """
        Calculate take-profit price based on historical recoveries.

        Args:
            data: DataFrame with OHLCV data
            current_price: Current stock price

        Returns:
            Dictionary with:
            - take_profit_price: Recommended take profit price
            - take_profit_pct: Percentage gain to target
            - dip_from_high_pct: Current dip from recent high
            - historical_avg_recovery: Average recovery from similar conditions
            - resistance_levels: Nearby resistance levels
            - confidence: 'high', 'medium', or 'low'
            - estimated_days_to_target: Estimated trading days to hit target
        """
        if data is None or len(data) < 50:
            return self._default_target(current_price)

        close = data['Close']
        high = data['High']

        # Calculate current dip magnitude
        recent_high = TechnicalIndicators.find_recent_high(
            high, self.recent_high_lookback
        )
        dip_pct = abs(TechnicalIndicators.calculate_dip_magnitude(
            current_price, recent_high
        ))

        # Analyze historical recoveries (now includes days estimate)
        avg_recovery, recovery_count, median_days = self.analyze_historical_recoveries(data)

        # Find resistance levels
        resistance_levels = self.find_resistance_levels(data, current_price)

        # Calculate take profit target
        take_profit_pct = self._calculate_target_pct(
            dip_pct, avg_recovery, resistance_levels, current_price
        )

        # Estimate days to target based on historical data and target size
        estimated_days = self._estimate_days_to_target(
            take_profit_pct, avg_recovery, median_days, data
        )

        # Determine confidence
        confidence = self._determine_confidence(recovery_count, resistance_levels)

        take_profit_price = current_price * (1 + take_profit_pct)

        return {
            'take_profit_price': round(take_profit_price, 2),
            'take_profit_pct': round(take_profit_pct, 4),
            'dip_from_high_pct': round(dip_pct, 4),
            'historical_avg_recovery': round(avg_recovery, 4) if avg_recovery else None,
            'recovery_sample_size': recovery_count,
            'resistance_levels': resistance_levels[:3] if resistance_levels else [],
            'confidence': confidence,
            'estimated_days_to_target': estimated_days
        }

    def analyze_historical_recoveries(
        self,
        data: pd.DataFrame
    ) -> tuple:
        """
        Find past RSI oversold events and measure subsequent recoveries.

        Args:
            data: DataFrame with OHLCV data

        Returns:
            Tuple of (median_recovery_pct, sample_count, median_days_to_recovery)
        """
        if len(data) < self.recovery_lookback_days:
            lookback = len(data)
        else:
            lookback = self.recovery_lookback_days

        close = data['Close'].tail(lookback)

        # Calculate RSI for historical data
        rsi = TechnicalIndicators.calculate_rsi(close, self.rsi_period)

        # Find oversold events
        oversold_mask = rsi < self.rsi_oversold
        oversold_indices = oversold_mask[oversold_mask].index.tolist()

        if not oversold_indices:
            return None, 0, None

        recoveries = []
        recovery_days = []

        for idx in oversold_indices:
            try:
                idx_pos = close.index.get_loc(idx)

                # Skip if too close to end
                if idx_pos >= len(close) - 5:
                    continue

                entry_price = close.iloc[idx_pos]

                # Look for recovery in next 20 trading days
                future_slice = close.iloc[idx_pos:min(idx_pos + 20, len(close))]
                max_future = future_slice.max()

                recovery = (max_future - entry_price) / entry_price
                if recovery > 0:
                    recoveries.append(recovery)

                    # Find how many days to reach peak
                    peak_idx = future_slice.idxmax()
                    peak_pos = future_slice.index.get_loc(peak_idx)
                    recovery_days.append(peak_pos)

            except (KeyError, IndexError):
                continue

        if not recoveries:
            return None, 0, None

        # Use median capped at 75th percentile for conservative estimate
        median_recovery = np.median(recoveries)
        p75_recovery = np.percentile(recoveries, 75)
        median_days = int(np.median(recovery_days)) if recovery_days else None

        return min(median_recovery, p75_recovery), len(recoveries), median_days

    def find_resistance_levels(
        self,
        data: pd.DataFrame,
        current_price: float
    ) -> List[float]:
        """
        Identify recent swing highs as potential resistance.

        Args:
            data: DataFrame with OHLCV data
            current_price: Current stock price

        Returns:
            List of resistance prices above current price, sorted ascending
        """
        swing_highs = TechnicalIndicators.find_swing_highs(data, lookback=60)

        # Filter to levels above current price
        resistance = [h for h in swing_highs if h > current_price]

        # Sort by proximity to current price
        resistance.sort()

        return resistance

    def _calculate_target_pct(
        self,
        dip_pct: float,
        avg_recovery: Optional[float],
        resistance_levels: List[float],
        current_price: float
    ) -> float:
        """
        Calculate the take profit percentage.

        Uses a conservative approach:
        1. Base target: minimum of historical recovery and 70% of dip
        2. Adjust for nearby resistance
        3. Cap at max_take_profit_pct
        """
        # Default target based on dip magnitude
        dip_based_target = dip_pct * 0.7  # Recover 70% of dip

        if avg_recovery is not None:
            # Use the more conservative of the two
            base_target = min(avg_recovery, dip_based_target)
        else:
            base_target = dip_based_target

        # Ensure minimum target of 3%
        base_target = max(base_target, 0.03)

        # Check if nearby resistance would limit the move
        if resistance_levels:
            nearest_resistance = resistance_levels[0]
            resistance_target = (nearest_resistance - current_price) / current_price

            # If resistance is closer than our target, adjust down
            if resistance_target < base_target:
                # Set target just below resistance (95% of the way)
                base_target = resistance_target * 0.95

        # Apply maximum cap
        return min(base_target, self.max_take_profit_pct)

    def _determine_confidence(
        self,
        recovery_count: int,
        resistance_levels: List[float]
    ) -> str:
        """
        Determine confidence level in the take profit target.

        High: Many historical samples, clear resistance
        Medium: Some samples or some resistance data
        Low: Limited data
        """
        if recovery_count >= 5 and len(resistance_levels) >= 2:
            return 'high'
        elif recovery_count >= 2 or len(resistance_levels) >= 1:
            return 'medium'
        else:
            return 'low'

    def _default_target(self, current_price: float) -> Dict:
        """Return a default conservative target when data is insufficient."""
        default_pct = 0.05  # 5% default target

        return {
            'take_profit_price': round(current_price * (1 + default_pct), 2),
            'take_profit_pct': default_pct,
            'dip_from_high_pct': None,
            'historical_avg_recovery': None,
            'recovery_sample_size': 0,
            'resistance_levels': [],
            'confidence': 'low',
            'estimated_days_to_target': 10  # Default estimate
        }

    def _estimate_days_to_target(
        self,
        take_profit_pct: float,
        avg_recovery: Optional[float],
        median_days: Optional[int],
        data: pd.DataFrame
    ) -> int:
        """
        Estimate trading days to reach the take profit target.

        Uses historical recovery times and adjusts based on target vs avg recovery.

        Args:
            take_profit_pct: Target profit percentage
            avg_recovery: Historical average recovery percentage
            median_days: Historical median days to recovery
            data: DataFrame with OHLCV data for volatility calculation

        Returns:
            Estimated number of trading days
        """
        # If we have historical data, use it as baseline
        if median_days is not None and avg_recovery is not None and avg_recovery > 0:
            # Scale days based on how our target compares to historical recovery
            ratio = take_profit_pct / avg_recovery
            estimated = int(median_days * ratio)
            # Clamp to reasonable range (1-30 trading days)
            return max(1, min(estimated, 30))

        # Fallback: estimate based on average daily volatility
        try:
            close = data['Close']
            daily_returns = close.pct_change().dropna()

            if len(daily_returns) < 20:
                return 10  # Default

            # Average absolute daily move
            avg_daily_move = daily_returns.abs().mean()

            if avg_daily_move > 0:
                # Rough estimate: days = target / average daily move
                # Add buffer since we need consecutive positive moves
                estimated = int(take_profit_pct / avg_daily_move * 1.5)
                return max(1, min(estimated, 30))

        except Exception:
            pass

        # Ultimate fallback
        return 10
