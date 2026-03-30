"""
Technical Indicators Module

Calculates technical indicators for signal generation:
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Volume analysis
- Support levels (Moving Averages)
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


class TechnicalIndicators:
    """Calculate technical indicators for signal generation."""

    @staticmethod
    def calculate_rsi(
        close: pd.Series,
        period: int = 14
    ) -> pd.Series:
        """
        Calculate RSI using Wilder's smoothing method.

        Args:
            close: Series of closing prices
            period: RSI period (default 14)

        Returns:
            Series of RSI values (0-100)
        """
        delta = close.diff()

        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        # Use exponential moving average (Wilder's smoothing)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def calculate_macd(
        close: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Dict[str, pd.Series]:
        """
        Calculate MACD line, signal line, and histogram.

        Args:
            close: Series of closing prices
            fast: Fast EMA period (default 12)
            slow: Slow EMA period (default 26)
            signal: Signal line period (default 9)

        Returns:
            Dictionary with 'macd', 'signal', and 'histogram' Series
        """
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }

    @staticmethod
    def detect_macd_crossover(
        macd: pd.Series,
        signal: pd.Series,
        lookback: int = 3
    ) -> Tuple[bool, int]:
        """
        Detect if MACD has crossed above signal line recently.

        Args:
            macd: MACD line Series
            signal: Signal line Series
            lookback: Number of bars to look back for crossover

        Returns:
            Tuple of (is_bullish_crossover, bars_since_crossover)
        """
        if len(macd) < 2:
            return False, -1

        # Check current position
        current_above = macd.iloc[-1] > signal.iloc[-1]

        if not current_above:
            return False, -1

        # Look for crossover within lookback period
        for i in range(1, min(lookback + 1, len(macd))):
            idx = -(i + 1)
            if len(macd) + idx < 0:
                break
            if macd.iloc[idx] <= signal.iloc[idx]:
                return True, i

        return False, -1

    @staticmethod
    def calculate_volume_ratio(
        volume: pd.Series,
        lookback: int = 20
    ) -> pd.Series:
        """
        Calculate volume ratio relative to moving average.

        Args:
            volume: Series of volume data
            lookback: Period for average volume calculation

        Returns:
            Series of volume ratios (e.g., 1.5 = 150% of average)
        """
        avg_volume = volume.rolling(window=lookback).mean()
        return volume / avg_volume

    @staticmethod
    def detect_volume_spike(
        volume: pd.Series,
        lookback: int = 20,
        threshold: float = 1.5
    ) -> pd.Series:
        """
        Detect volume spikes relative to moving average.

        Args:
            volume: Series of volume data
            lookback: Period for average volume calculation
            threshold: Minimum ratio to consider a spike

        Returns:
            Boolean Series where True indicates a volume spike
        """
        ratio = TechnicalIndicators.calculate_volume_ratio(volume, lookback)
        return ratio >= threshold

    @staticmethod
    def calculate_moving_averages(
        close: pd.Series,
        periods: List[int] = [50, 200]
    ) -> Dict[str, pd.Series]:
        """
        Calculate simple moving averages for given periods.

        Args:
            close: Series of closing prices
            periods: List of MA periods to calculate

        Returns:
            Dictionary mapping period to MA Series
        """
        result = {}
        for period in periods:
            result[f'ma_{period}'] = close.rolling(window=period).mean()
        return result

    @staticmethod
    def calculate_distance_to_support(
        close: pd.Series,
        ma_values: Dict[str, pd.Series]
    ) -> Dict[str, pd.Series]:
        """
        Calculate percentage distance from price to each moving average.

        Args:
            close: Series of closing prices
            ma_values: Dictionary of moving average Series

        Returns:
            Dictionary mapping MA name to distance percentage Series
        """
        result = {}
        for name, ma in ma_values.items():
            result[f'dist_{name}'] = (close - ma) / ma
        return result

    @staticmethod
    def is_near_support(
        close: float,
        ma_values: Dict[str, float],
        tolerance: float = 0.03
    ) -> Tuple[bool, Optional[str], float]:
        """
        Check if current price is near any support level.

        Args:
            close: Current closing price
            ma_values: Dictionary of current MA values
            tolerance: Maximum distance to consider "near" (e.g., 0.03 = 3%)

        Returns:
            Tuple of (is_near, support_type, distance)
            - is_near: True if near any support
            - support_type: 'ma_50', 'ma_200', or 'both'
            - distance: Distance to nearest support (negative = below)
        """
        near_supports = []
        min_distance = float('inf')
        min_support = None

        for name, ma in ma_values.items():
            if ma is None or np.isnan(ma):
                continue

            distance = (close - ma) / ma

            # Check if near support (above MA but within tolerance)
            if -tolerance <= distance <= tolerance:
                near_supports.append(name)

            if abs(distance) < abs(min_distance):
                min_distance = distance
                min_support = name

        if not near_supports:
            return False, None, min_distance

        if len(near_supports) > 1:
            return True, 'both', min_distance
        else:
            return True, near_supports[0], min_distance

    @staticmethod
    def find_recent_high(
        high: pd.Series,
        lookback: int = 20
    ) -> float:
        """
        Find the highest price in the lookback period.

        Args:
            high: Series of high prices
            lookback: Number of bars to look back

        Returns:
            Highest price in the period
        """
        return high.tail(lookback).max()

    @staticmethod
    def find_recent_low(
        low: pd.Series,
        lookback: int = 20
    ) -> float:
        """
        Find the lowest price in the lookback period.

        Args:
            low: Series of low prices
            lookback: Number of bars to look back

        Returns:
            Lowest price in the period
        """
        return low.tail(lookback).min()

    @staticmethod
    def calculate_dip_magnitude(
        current_price: float,
        recent_high: float
    ) -> float:
        """
        Calculate how much price has dropped from recent high.

        Args:
            current_price: Current price
            recent_high: Recent high price

        Returns:
            Dip percentage (negative value, e.g., -0.10 = 10% dip)
        """
        if recent_high == 0:
            return 0.0
        return (current_price - recent_high) / recent_high

    @staticmethod
    def find_swing_highs(
        data: pd.DataFrame,
        lookback: int = 60,
        prominence: int = 5
    ) -> List[float]:
        """
        Find swing high prices that could act as resistance.

        Args:
            data: DataFrame with OHLCV data
            lookback: Number of bars to analyze
            prominence: Minimum bars on each side to qualify as swing high

        Returns:
            List of swing high prices, sorted descending
        """
        if len(data) < lookback:
            lookback = len(data)

        high = data['High'].tail(lookback)
        swing_highs = []

        for i in range(prominence, len(high) - prominence):
            is_swing_high = True
            center_val = high.iloc[i]

            for j in range(1, prominence + 1):
                if high.iloc[i - j] >= center_val or high.iloc[i + j] >= center_val:
                    is_swing_high = False
                    break

            if is_swing_high:
                swing_highs.append(center_val)

        return sorted(swing_highs, reverse=True)
