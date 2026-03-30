"""
Alert Manager Module

Manages alert deduplication and cooldown periods.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from ..scanner.signal_scorer import SignalScore

logger = logging.getLogger(__name__)


class AlertManager:
    """Manage alert deduplication and cooldown periods."""

    def __init__(
        self,
        cooldown_hours: int = 24,
        state_file: str = "alert_state.json"
    ):
        """
        Initialize the alert manager.

        Args:
            cooldown_hours: Hours before re-alerting same stock
            state_file: Path to state persistence file
        """
        self.cooldown_hours = cooldown_hours
        self.state_file = Path(state_file)
        self.alert_history: Dict[str, datetime] = {}

        self._load_state()

    def should_alert(self, ticker: str) -> bool:
        """
        Check if ticker is eligible for alert (not in cooldown).

        Args:
            ticker: Stock ticker symbol

        Returns:
            True if alert should be sent, False if in cooldown
        """
        last_alert = self.alert_history.get(ticker)

        if last_alert is None:
            return True

        elapsed = datetime.now() - last_alert
        return elapsed > timedelta(hours=self.cooldown_hours)

    def record_alert(self, ticker: str) -> None:
        """
        Record that an alert was sent for a ticker.

        Args:
            ticker: Stock ticker symbol
        """
        self.alert_history[ticker] = datetime.now()
        self._save_state()

    def filter_signals(
        self,
        signals: List[SignalScore]
    ) -> List[SignalScore]:
        """
        Filter out signals that are in cooldown.

        Args:
            signals: List of SignalScore objects

        Returns:
            Filtered list of signals eligible for alerting
        """
        return [s for s in signals if self.should_alert(s.ticker)]

    def get_cooldown_remaining(self, ticker: str) -> Optional[timedelta]:
        """
        Get remaining cooldown time for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Remaining cooldown time, or None if not in cooldown
        """
        last_alert = self.alert_history.get(ticker)

        if last_alert is None:
            return None

        elapsed = datetime.now() - last_alert
        cooldown = timedelta(hours=self.cooldown_hours)

        if elapsed >= cooldown:
            return None

        return cooldown - elapsed

    def clear_cooldown(self, ticker: str) -> None:
        """
        Clear cooldown for a specific ticker.

        Args:
            ticker: Stock ticker symbol
        """
        if ticker in self.alert_history:
            del self.alert_history[ticker]
            self._save_state()

    def clear_all_cooldowns(self) -> None:
        """Clear all cooldowns."""
        self.alert_history.clear()
        self._save_state()

    def get_active_cooldowns(self) -> Dict[str, datetime]:
        """
        Get all tickers currently in cooldown.

        Returns:
            Dictionary of ticker to last alert time
        """
        now = datetime.now()
        cooldown = timedelta(hours=self.cooldown_hours)

        return {
            ticker: last_alert
            for ticker, last_alert in self.alert_history.items()
            if (now - last_alert) < cooldown
        }

    def cleanup_expired(self) -> int:
        """
        Remove expired entries from history.

        Returns:
            Number of entries removed
        """
        now = datetime.now()
        max_age = timedelta(hours=self.cooldown_hours * 2)  # Keep for 2x cooldown

        expired = [
            ticker
            for ticker, last_alert in self.alert_history.items()
            if (now - last_alert) > max_age
        ]

        for ticker in expired:
            del self.alert_history[ticker]

        if expired:
            self._save_state()
            logger.debug(f"Cleaned up {len(expired)} expired alert records")

        return len(expired)

    def _load_state(self) -> None:
        """Load state from file."""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)

            self.alert_history = {
                ticker: datetime.fromisoformat(ts)
                for ticker, ts in data.get('alert_history', {}).items()
            }

            logger.debug(f"Loaded {len(self.alert_history)} alert history entries")

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Could not load state file: {e}")
            self.alert_history = {}

    def _save_state(self) -> None:
        """Save state to file."""
        data = {
            'alert_history': {
                ticker: ts.isoformat()
                for ticker, ts in self.alert_history.items()
            },
            'last_updated': datetime.now().isoformat()
        }

        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)

        except IOError as e:
            logger.warning(f"Could not save state file: {e}")
