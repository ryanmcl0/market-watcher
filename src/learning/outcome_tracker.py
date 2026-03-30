"""
Outcome Tracker Module

Records alert snapshots and resolves them by tracking price outcomes.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..scanner.signal_scorer import SignalScore

logger = logging.getLogger(__name__)


class OutcomeTracker:
    """Track outcomes of alert signals to measure prediction accuracy."""

    def __init__(
        self,
        outcomes_file: str = 'alert_outcomes.json',
        stop_loss_pct: float = 0.10,
        max_hold_days: int = 30,
        data_fetcher=None,
    ):
        self.outcomes_file = Path(outcomes_file)
        self.stop_loss_pct = stop_loss_pct
        self.max_hold_days = max_hold_days
        self.data_fetcher = data_fetcher

        self.outcomes: Dict = {'pending': [], 'completed': []}
        self._load()

    def record_signal(self, signal: SignalScore, weights: Optional[Dict[str, float]] = None) -> None:
        """Record a snapshot of an alert for future outcome tracking."""
        record = {
            'ticker': signal.ticker,
            'alert_price': signal.price,
            'alert_date': datetime.now().isoformat(),
            'score': signal.score,
            'rsi_score': signal.rsi_score,
            'macd_score': signal.macd_score,
            'volume_score': signal.volume_score,
            'support_score': signal.support_score,
            'rsi_value': signal.rsi_value,
            'volume_ratio': signal.volume_ratio,
            'take_profit_price': signal.take_profit_price,
            'take_profit_pct': signal.take_profit_pct,
            'estimated_days_to_target': signal.estimated_days_to_target,
            'weights_at_alert': weights or {},
            'market': signal.market,
            'currency_symbol': signal.currency_symbol,
        }

        self.outcomes['pending'].append(record)
        self._save()
        logger.info(f"Recorded outcome tracking for {signal.ticker} @ ${signal.price:.2f}")

    def check_outcomes(self) -> List[Dict]:
        """
        Check all pending outcomes against current prices.

        Returns list of newly resolved outcomes.
        """
        if not self.outcomes['pending']:
            logger.info("No pending outcomes to check")
            return []

        if self.data_fetcher is None:
            logger.error("No data_fetcher configured, cannot check outcomes")
            return []

        # Collect unique tickers
        tickers = list({r['ticker'] for r in self.outcomes['pending']})
        logger.info(f"Checking outcomes for {len(self.outcomes['pending'])} pending alerts ({len(tickers)} tickers)")

        # Batch fetch current data
        data_dict = self.data_fetcher.fetch_for_scanning(tickers, lookback_days=self.max_hold_days + 10)

        resolved = []
        still_pending = []

        for record in self.outcomes['pending']:
            ticker = record['ticker']
            alert_date = datetime.fromisoformat(record['alert_date'])
            alert_price = record['alert_price']

            data = data_dict.get(ticker)
            if data is None:
                still_pending.append(record)
                continue

            result = self._evaluate_outcome(record, data, alert_date, alert_price)

            if result is not None:
                completed = {**record, **result}
                self.outcomes['completed'].append(completed)
                resolved.append(completed)
                logger.info(
                    f"Resolved {ticker}: {result['outcome']} "
                    f"(return: {result['actual_return_pct']*100:+.1f}%, "
                    f"{result['days_held']}d held)"
                )
            else:
                still_pending.append(record)

        self.outcomes['pending'] = still_pending
        self._save()

        logger.info(f"Resolved {len(resolved)} outcomes, {len(still_pending)} still pending")
        return resolved

    def _evaluate_outcome(
        self,
        record: Dict,
        data,
        alert_date: datetime,
        alert_price: float,
    ) -> Optional[Dict]:
        """Evaluate a single pending outcome against price data."""
        try:
            # Filter data to after alert date
            data_after = data[data.index >= alert_date.strftime('%Y-%m-%d')]

            if data_after.empty:
                return None

            days_held = len(data_after)
            current_price = float(data_after['Close'].iloc[-1])
            high_since = float(data_after['High'].max())
            low_since = float(data_after['Low'].min())

            max_gain = (high_since - alert_price) / alert_price
            max_drawdown = (low_since - alert_price) / alert_price
            actual_return = (current_price - alert_price) / alert_price

            tp_price = record.get('take_profit_price')
            sl_price = alert_price * (1 - self.stop_loss_pct)

            # Check hit take-profit
            if tp_price and high_since >= tp_price:
                return {
                    'outcome': 'hit_tp',
                    'actual_return_pct': (tp_price - alert_price) / alert_price,
                    'max_gain_pct': max_gain,
                    'max_drawdown_pct': max_drawdown,
                    'days_held': days_held,
                    'resolved_date': datetime.now().isoformat(),
                    'exit_price': tp_price,
                }

            # Check hit stop-loss
            if low_since <= sl_price:
                return {
                    'outcome': 'hit_sl',
                    'actual_return_pct': -self.stop_loss_pct,
                    'max_gain_pct': max_gain,
                    'max_drawdown_pct': max_drawdown,
                    'days_held': days_held,
                    'resolved_date': datetime.now().isoformat(),
                    'exit_price': sl_price,
                }

            # Check expired
            if days_held >= self.max_hold_days:
                return {
                    'outcome': 'expired',
                    'actual_return_pct': actual_return,
                    'max_gain_pct': max_gain,
                    'max_drawdown_pct': max_drawdown,
                    'days_held': days_held,
                    'resolved_date': datetime.now().isoformat(),
                    'exit_price': current_price,
                }

            # Still pending
            return None

        except Exception as e:
            logger.debug(f"Error evaluating {record['ticker']}: {e}")
            return None

    def get_pending_count(self) -> int:
        return len(self.outcomes['pending'])

    def get_completed_count(self) -> int:
        return len(self.outcomes['completed'])

    def get_completed_outcomes(self) -> List[Dict]:
        return list(self.outcomes['completed'])

    def _load(self) -> None:
        if not self.outcomes_file.exists():
            return

        try:
            with open(self.outcomes_file, 'r') as f:
                data = json.load(f)
            self.outcomes = {
                'pending': data.get('pending', []),
                'completed': data.get('completed', []),
            }
            logger.debug(
                f"Loaded {len(self.outcomes['pending'])} pending, "
                f"{len(self.outcomes['completed'])} completed outcomes"
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Could not load outcomes file: {e}")

    def _save(self) -> None:
        try:
            self.outcomes_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.outcomes_file, 'w') as f:
                json.dump(self.outcomes, f, indent=2)
        except IOError as e:
            logger.warning(f"Could not save outcomes file: {e}")
