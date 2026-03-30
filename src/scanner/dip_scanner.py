"""
Dip Scanner Module

Main orchestration for scanning S&P 500 stocks for dip-buying opportunities.
"""

import logging
import time
from typing import Dict, List, Optional

import pandas as pd

from ..data.data_fetcher import DataFetcher
from ..data.sp500_universe import SP500Universe
from .signal_scorer import SignalScore, SignalScorer
from .profit_target import ProfitTargetCalculator

logger = logging.getLogger(__name__)


class DipScanner:
    """Scans stocks for dip-buying opportunities."""

    def __init__(
        self,
        data_fetcher: Optional[DataFetcher] = None,
        universe=None,
        scorer: Optional[SignalScorer] = None,
        profit_calculator: Optional[ProfitTargetCalculator] = None,
        batch_size: int = 50,
        inter_batch_delay: float = 1.5,
        lookback_days: int = 250,
        market_id: str = 'sp500',
        currency_symbol: str = '$',
    ):
        """
        Initialize the dip scanner.

        Args:
            data_fetcher: DataFetcher instance (created if None)
            universe: Any object with get_tickers() method (created if None)
            scorer: SignalScorer instance (created if None)
            profit_calculator: ProfitTargetCalculator instance (created if None)
            batch_size: Stocks per batch for API calls
            inter_batch_delay: Seconds between batches
            lookback_days: Days of history to fetch
            market_id: Market identifier (e.g. 'sp500', 'ftse100', 'hangseng')
            currency_symbol: Currency symbol for display (e.g. '$', '£', 'HK$')
        """
        self.data_fetcher = data_fetcher or DataFetcher()
        self.universe = universe or SP500Universe()
        self.scorer = scorer or SignalScorer()
        self.profit_calculator = profit_calculator or ProfitTargetCalculator()
        self.market_id = market_id
        self.currency_symbol = currency_symbol

        self.batch_size = batch_size
        self.inter_batch_delay = inter_batch_delay
        self.lookback_days = lookback_days

    def scan(
        self,
        min_score: float = 70,
        top_n: int = 10,
        tickers: Optional[List[str]] = None
    ) -> List[SignalScore]:
        """
        Scan stocks and return top opportunities.

        Args:
            min_score: Minimum signal score to include
            top_n: Maximum number of signals to return
            tickers: Optional list of tickers to scan (default: S&P 500)

        Returns:
            List of SignalScore objects, sorted by score descending
        """
        logger.info("Starting scan...")
        start_time = time.time()

        if tickers is None:
            tickers = self.universe.get_tickers()

        logger.info(f"Scanning {len(tickers)} stocks...")

        all_signals = []
        batches = list(self._batch_tickers(tickers))
        total_batches = len(batches)

        for batch_num, batch in enumerate(batches, 1):
            logger.debug(f"Processing batch {batch_num}/{total_batches}")

            try:
                signals = self._process_batch(batch)
                all_signals.extend(signals)
            except Exception as e:
                logger.error(f"Error processing batch {batch_num}: {e}")
                continue

            # Rate limiting delay (skip on last batch)
            if batch_num < total_batches and self.inter_batch_delay > 0:
                time.sleep(self.inter_batch_delay)

        # Filter and rank signals
        ranked_signals = self.scorer.rank_signals(all_signals, min_score)

        # Add take-profit targets to top signals
        for signal in ranked_signals[:top_n]:
            self._add_profit_target(signal)

        elapsed = time.time() - start_time
        logger.info(
            f"Scan complete in {elapsed:.1f}s. "
            f"Found {len(ranked_signals)} signals above {min_score}"
        )

        return ranked_signals[:top_n]

    def scan_single(self, ticker: str) -> Optional[SignalScore]:
        """
        Scan a single stock.

        Args:
            ticker: Stock ticker symbol

        Returns:
            SignalScore if calculable, None otherwise
        """
        data = self.data_fetcher.fetch_single_stock(ticker, self.lookback_days)

        if data is None:
            return None

        signal = self.scorer.score_stock(ticker, data)

        if signal is not None:
            signal.market = self.market_id
            signal.currency_symbol = self.currency_symbol
            self._add_profit_target(signal, data)

        return signal

    def _batch_tickers(self, tickers: List[str]):
        """Yield tickers in batches."""
        for i in range(0, len(tickers), self.batch_size):
            yield tickers[i:i + self.batch_size]

    def _process_batch(self, tickers: List[str]) -> List[SignalScore]:
        """
        Process a batch of tickers.

        Args:
            tickers: List of ticker symbols

        Returns:
            List of SignalScore objects
        """
        # Fetch data for batch
        data_dict = self.data_fetcher.fetch_for_scanning(
            tickers, self.lookback_days
        )

        signals = []

        for ticker, data in data_dict.items():
            try:
                signal = self.scorer.score_stock(ticker, data)
                if signal is not None:
                    signal.market = self.market_id
                    signal.currency_symbol = self.currency_symbol
                    # Store data reference for profit target calculation
                    signal._data = data
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"Error scoring {ticker}: {e}")
                continue

        return signals

    def _add_profit_target(
        self,
        signal: SignalScore,
        data: Optional[pd.DataFrame] = None
    ) -> None:
        """
        Add take-profit target to a signal.

        Args:
            signal: SignalScore to update
            data: Optional DataFrame (uses cached if not provided)
        """
        if data is None:
            data = getattr(signal, '_data', None)

        if data is None:
            # Fetch data if not available
            data = self.data_fetcher.fetch_single_stock(
                signal.ticker, self.lookback_days
            )

        if data is None:
            return

        target = self.profit_calculator.calculate_take_profit(
            data, signal.price
        )

        signal.take_profit_price = target['take_profit_price']
        signal.take_profit_pct = target['take_profit_pct']
        signal.take_profit_confidence = target['confidence']
        signal.estimated_days_to_target = target['estimated_days_to_target']

        # Clean up cached data
        if hasattr(signal, '_data'):
            delattr(signal, '_data')

    def get_market_summary(self) -> Dict:
        """
        Get a summary of current market conditions.

        Returns:
            Dictionary with market summary stats
        """
        tickers = self.universe.get_tickers()
        sample_tickers = tickers[:50]  # Quick sample

        data_dict = self.data_fetcher.fetch_for_scanning(
            sample_tickers, lookback_days=30
        )

        oversold_count = 0
        total_counted = 0

        for ticker, data in data_dict.items():
            try:
                from ..indicators.technical import TechnicalIndicators
                rsi = TechnicalIndicators.calculate_rsi(data['Close'])
                if rsi.iloc[-1] < 30:
                    oversold_count += 1
                total_counted += 1
            except Exception:
                continue

        return {
            'sample_size': total_counted,
            'oversold_count': oversold_count,
            'oversold_pct': oversold_count / total_counted if total_counted > 0 else 0
        }
