"""
Signal Scorer Module

Calculates composite signal scores for buy opportunities.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..indicators.technical import TechnicalIndicators


@dataclass
class SignalScore:
    """Represents a scored buy signal for a stock."""

    ticker: str
    score: float  # 0-100 composite score
    price: float
    timestamp: datetime

    # RSI metrics
    rsi_value: float
    rsi_score: float

    # MACD metrics
    macd_crossover: bool
    macd_bars_since: int
    macd_score: float

    # Volume metrics
    volume_ratio: float
    volume_score: float

    # Support metrics
    distance_to_support: float
    support_type: Optional[str]  # 'ma_50', 'ma_200', or 'both'
    support_score: float

    # Dip metrics
    dip_from_high: float
    recent_high: float

    # Market identification
    market: str = ''                    # "sp500", "ftse100", "hangseng"
    currency_symbol: str = '$'          # "$", "£", "HK$"

    # Take profit (filled in by ProfitTargetCalculator)
    take_profit_price: Optional[float] = None
    take_profit_pct: Optional[float] = None
    take_profit_confidence: Optional[str] = None
    estimated_days_to_target: Optional[int] = None


class SignalScorer:
    """Score and rank buy signals across multiple stocks."""

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        rsi_period: int = 14,
        rsi_oversold: float = 30,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        macd_lookback: int = 3,
        volume_lookback: int = 20,
        volume_threshold: float = 1.5,
        ma_periods: List[int] = [50, 200],
        support_tolerance: float = 0.03,
        recent_high_lookback: int = 20
    ):
        """
        Initialize the signal scorer.

        Args:
            weights: Dictionary of indicator weights (must sum to 1.0)
            rsi_period: Period for RSI calculation
            rsi_oversold: RSI threshold for oversold condition
            macd_fast: MACD fast EMA period
            macd_slow: MACD slow EMA period
            macd_signal: MACD signal line period
            macd_lookback: Bars to look back for MACD crossover
            volume_lookback: Period for average volume
            volume_threshold: Minimum volume ratio for spike
            ma_periods: Moving average periods for support
            support_tolerance: Distance tolerance for "near support"
            recent_high_lookback: Bars to look back for recent high
        """
        self.weights = weights or {
            'rsi': 0.25,
            'macd': 0.25,
            'volume': 0.20,
            'support': 0.30
        }

        # Validate weights sum to 1.0
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.macd_lookback = macd_lookback
        self.volume_lookback = volume_lookback
        self.volume_threshold = volume_threshold
        self.ma_periods = ma_periods
        self.support_tolerance = support_tolerance
        self.recent_high_lookback = recent_high_lookback

    def score_stock(
        self,
        ticker: str,
        data: pd.DataFrame
    ) -> Optional[SignalScore]:
        """
        Calculate composite score for a single stock.

        Args:
            ticker: Stock ticker symbol
            data: DataFrame with OHLCV data

        Returns:
            SignalScore if calculable, None otherwise
        """
        if data is None or len(data) < max(self.ma_periods):
            return None

        try:
            close = data['Close']
            volume = data['Volume']
            high = data['High']

            current_price = float(close.iloc[-1])

            # Calculate RSI
            rsi = TechnicalIndicators.calculate_rsi(close, self.rsi_period)
            rsi_value = float(rsi.iloc[-1])
            rsi_score = self._calculate_rsi_score(rsi_value)

            # Calculate MACD
            macd_data = TechnicalIndicators.calculate_macd(
                close, self.macd_fast, self.macd_slow, self.macd_signal
            )
            macd_crossover, macd_bars_since = TechnicalIndicators.detect_macd_crossover(
                macd_data['macd'], macd_data['signal'], self.macd_lookback
            )
            macd_histogram = macd_data['macd'] - macd_data['signal']
            hist_rising = (
                len(macd_histogram) >= 2
                and float(macd_histogram.iloc[-1]) > float(macd_histogram.iloc[-2])
            )
            macd_score = self._calculate_macd_score(
                macd_crossover, macd_bars_since, hist_rising
            )

            # Calculate volume ratio
            volume_ratio = float(
                TechnicalIndicators.calculate_volume_ratio(
                    volume, self.volume_lookback
                ).iloc[-1]
            )
            volume_score = self._calculate_volume_score(volume_ratio)

            # Calculate support levels
            ma_values = TechnicalIndicators.calculate_moving_averages(
                close, self.ma_periods
            )
            current_mas = {k: float(v.iloc[-1]) for k, v in ma_values.items()}
            is_near, support_type, distance = TechnicalIndicators.is_near_support(
                current_price, current_mas, self.support_tolerance
            )
            support_score = self._calculate_support_score(is_near, distance)

            # Calculate dip from recent high
            recent_high = TechnicalIndicators.find_recent_high(
                high, self.recent_high_lookback
            )
            dip_from_high = TechnicalIndicators.calculate_dip_magnitude(
                current_price, recent_high
            )

            # Calculate composite score
            composite_score = (
                self.weights['rsi'] * rsi_score +
                self.weights['macd'] * macd_score +
                self.weights['volume'] * volume_score +
                self.weights['support'] * support_score
            )

            return SignalScore(
                ticker=ticker,
                score=composite_score,
                price=current_price,
                timestamp=datetime.now(),
                rsi_value=rsi_value,
                rsi_score=rsi_score,
                macd_crossover=macd_crossover,
                macd_bars_since=macd_bars_since,
                macd_score=macd_score,
                volume_ratio=volume_ratio,
                volume_score=volume_score,
                distance_to_support=distance,
                support_type=support_type,
                support_score=support_score,
                dip_from_high=dip_from_high,
                recent_high=recent_high
            )

        except Exception:
            return None

    def _calculate_rsi_score(self, rsi: float) -> float:
        """
        Convert RSI value to 0-100 score.

        Lower RSI = higher score (more oversold = more attractive)

        Scoring:
        - RSI < 20: 100 points
        - RSI 20-25: 75-100 points
        - RSI 25-30: 50-75 points
        - RSI 30-40: 25-50 points
        - RSI 40-50: 0-25 points
        - RSI > 50: 0 points
        """
        if np.isnan(rsi):
            return 0.0

        if rsi < 20:
            return 100.0
        elif rsi < 25:
            return 75 + (25 - rsi) * 5  # 75-100
        elif rsi < 30:
            return 50 + (30 - rsi) * 5  # 50-75
        elif rsi < 40:
            return 25 + (40 - rsi) * 2.5  # 25-50
        elif rsi < 50:
            return (50 - rsi) * 2.5  # 0-25
        else:
            return 0.0

    def _calculate_macd_score(
        self,
        crossover: bool,
        bars_since: int,
        hist_rising: bool = False
    ) -> float:
        """
        Convert MACD crossover to 0-100 score.

        Scoring:
        - Crossover today (bars_since=1): 100 points
        - Crossover 2 bars ago: 75 points
        - Crossover 3 bars ago: 50 points
        - No crossover but histogram rising: 25 points
        - No crossover: 0 points
        """
        if not crossover:
            return 25.0 if hist_rising else 0.0

        if bars_since == 1:
            return 100.0
        elif bars_since == 2:
            return 75.0
        elif bars_since == 3:
            return 50.0
        else:
            return 25.0

    def _calculate_volume_score(self, volume_ratio: float) -> float:
        """
        Convert volume ratio to 0-100 score.

        Scoring:
        - Ratio > 2.5: 100 points
        - Ratio 2.0-2.5: 75-100 points
        - Ratio 1.5-2.0: 50-75 points
        - Ratio 1.2-1.5: 25-50 points
        - Ratio < 1.2: 0-25 points
        """
        if np.isnan(volume_ratio):
            return 0.0

        if volume_ratio >= 2.5:
            return 100.0
        elif volume_ratio >= 2.0:
            return 75 + (volume_ratio - 2.0) * 50  # 75-100
        elif volume_ratio >= 1.5:
            return 50 + (volume_ratio - 1.5) * 50  # 50-75
        elif volume_ratio >= 1.2:
            return 25 + (volume_ratio - 1.2) * 83.3  # 25-50
        else:
            return max(0, volume_ratio * 20.8)  # 0-25

    def _calculate_support_score(
        self,
        is_near: bool,
        distance: float
    ) -> float:
        """
        Convert support proximity to 0-100 score.

        Scoring (when price is above support):
        - Within 1% of support: 100 points
        - 1-2% from support: 75 points
        - 2-3% from support: 50 points
        - 3-5% from support: 25 points
        - Not near support: 0 points
        """
        if np.isnan(distance):
            return 0.0

        if not is_near:
            return 0.0

        abs_distance = abs(distance)

        if abs_distance <= 0.01:
            return 100.0
        elif abs_distance <= 0.02:
            return 75.0
        elif abs_distance <= 0.03:
            return 50.0
        elif abs_distance <= 0.05:
            return 25.0
        else:
            return 0.0

    def rank_signals(
        self,
        signals: List[SignalScore],
        min_score: float = 70
    ) -> List[SignalScore]:
        """
        Filter and rank signals by score descending.

        Args:
            signals: List of SignalScore objects
            min_score: Minimum score to include

        Returns:
            Filtered and sorted list of signals
        """
        filtered = [s for s in signals if s.score >= min_score]
        return sorted(filtered, key=lambda x: x.score, reverse=True)
