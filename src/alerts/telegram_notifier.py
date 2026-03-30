"""
Telegram Notifier Module

Send alerts via Telegram Bot API.
"""

import logging
from typing import Dict, List, Optional

import requests

from ..scanner.signal_scorer import SignalScore

logger = logging.getLogger(__name__)

# Map market IDs to timezone strings and abbreviations
MARKET_TIMEZONES = {
    'sp500': ('US/Eastern', 'ET'),
    'ftse100': ('Europe/London', 'GMT/BST'),
    'hangseng': ('Asia/Hong_Kong', 'HKT'),
}


class TelegramNotifier:
    """Send alerts via Telegram Bot API."""

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        timeout: int = 10,
        parse_mode: str = "HTML"
    ):
        """
        Initialize the Telegram notifier.

        Args:
            bot_token: Telegram Bot API token
            chat_id: Comma-separated chat IDs (e.g. "123,-1001234567890")
            timeout: Request timeout in seconds
            parse_mode: Message formatting mode (HTML or Markdown)
        """
        self.bot_token = bot_token
        self.chat_ids = [cid.strip() for cid in chat_id.split(',') if cid.strip()]
        self.timeout = timeout
        self.parse_mode = parse_mode

    def send_message(self, message: str) -> bool:
        """
        Send a text message to all configured chats.

        Args:
            message: Message text

        Returns:
            True if sent successfully to all chats, False otherwise
        """
        if not self.bot_token or not self.chat_ids:
            logger.error("Telegram bot token or chat IDs not configured")
            return False

        url = self.BASE_URL.format(token=self.bot_token, method="sendMessage")
        all_ok = True

        for chat_id in self.chat_ids:
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": self.parse_mode,
                "disable_web_page_preview": True
            }

            try:
                response = requests.post(url, json=payload, timeout=self.timeout)
                if response.status_code == 200:
                    logger.debug(f"Message sent to {chat_id}")
                else:
                    logger.error(f"Telegram API error for {chat_id}: {response.status_code} - {response.text}")
                    all_ok = False
            except requests.exceptions.Timeout:
                logger.error(f"Telegram request timed out for {chat_id}")
                all_ok = False
            except requests.exceptions.RequestException as e:
                logger.error(f"Telegram request failed for {chat_id}: {e}")
                all_ok = False

        return all_ok

    def send_alert(self, signal: SignalScore) -> bool:
        """
        Format and send a buy signal alert.

        Args:
            signal: SignalScore object

        Returns:
            True if sent successfully
        """
        message = self._format_alert(signal)
        return self.send_message(message)

    def send_batch_alert(self, signals: List[SignalScore]) -> bool:
        """
        Send summary of multiple signals in one message.

        Args:
            signals: List of SignalScore objects

        Returns:
            True if sent successfully
        """
        if not signals:
            return True

        if len(signals) == 1:
            return self.send_alert(signals[0])

        message = self._format_batch_alert(signals)
        return self.send_message(message)

    def send_outcome_update(self, resolved: List[Dict]) -> bool:
        """
        Send rich notifications for resolved trade outcomes.

        Args:
            resolved: List of resolved outcome dicts from OutcomeTracker

        Returns:
            True if all messages sent successfully
        """
        if not resolved:
            return True

        all_ok = True
        for outcome in resolved[:10]:
            message = self._format_outcome(outcome)
            if not self.send_message(message):
                all_ok = False

        if len(resolved) > 10:
            self.send_message(
                f"<i>...and {len(resolved) - 10} more outcomes resolved. "
                f"See weekly report for full details.</i>"
            )

        return all_ok

    def _format_outcome(self, outcome: Dict) -> str:
        """Format a single resolved outcome as an HTML message."""
        ticker = outcome['ticker']
        result_type = outcome['outcome']
        ret_pct = outcome.get('actual_return_pct', 0)
        entry_price = outcome['alert_price']
        exit_price = outcome.get('exit_price', entry_price)
        days_held = outcome.get('days_held', 0)
        score = outcome.get('score', 0)
        tp_price = outcome.get('take_profit_price')
        tp_pct = outcome.get('take_profit_pct')

        # Get currency symbol from outcome record
        currency = outcome.get('currency_symbol', '$')

        # Parse alert date for display
        alert_date_str = outcome.get('alert_date', '')
        try:
            from datetime import datetime
            alert_dt = datetime.fromisoformat(alert_date_str)
            date_display = alert_dt.strftime('%b %-d')
        except (ValueError, TypeError):
            date_display = 'unknown date'

        # Result header
        if result_type == 'hit_tp':
            result_label = "HIT TAKE PROFIT"
        elif result_type == 'hit_sl':
            result_label = "STOPPED OUT"
        else:
            result_label = "EXPIRED (held to limit)"

        # Return display
        ret_display = f"{ret_pct * 100:+.1f}%"

        # Take profit target line
        if tp_price and tp_pct:
            tp_line = f"<b>Take Profit Target:</b> {currency}{tp_price:.2f} (+{tp_pct * 100:.1f}%)"
        else:
            tp_line = "<b>Take Profit Target:</b> N/A"

        # Market name
        market_id = outcome.get('market', '')
        market_label = _get_market_display_name(market_id)
        market_suffix = f" ({market_label})" if market_label else ""

        message = (
            f"<b>TRADE UPDATE: {ticker}{market_suffix}</b>\n"
            f"\n"
            f"<b>Result:</b> {result_label}\n"
            f"<b>Return:</b> {ret_display}\n"
            f"\n"
            f"<b>Entry Price:</b> {currency}{entry_price:.2f} (recommended {date_display})\n"
            f"<b>Exit Price:</b> {currency}{exit_price:.2f}\n"
            f"<b>Days Held:</b> {days_held}\n"
            f"\n"
            f"<b>Original Signal Score:</b> {score:.0f}/100\n"
            f"{tp_line}\n"
            f"\n"
            f"<i>This is an automated follow-up to a previous buy signal.</i>"
        )
        return message

    def test_connection(self) -> bool:
        """
        Test if bot token and chat_id are valid.

        Returns:
            True if connection is valid
        """
        url = self.BASE_URL.format(token=self.bot_token, method="getMe")

        try:
            response = requests.get(url, timeout=self.timeout)
            if response.status_code == 200:
                bot_info = response.json()
                if bot_info.get('ok'):
                    logger.info(f"Connected to bot: @{bot_info['result']['username']}")
                    return True
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def _calculate_order_urgency(self, signal: SignalScore) -> str:
        """
        Calculate how urgently the user should place the order.

        Args:
            signal: SignalScore object

        Returns:
            Formatted urgency message
        """
        from datetime import datetime
        import pytz

        # Calculate urgency score (0-100)
        urgency_score = 0

        # Factor 1: Signal score (max 40 points)
        if signal.score >= 90:
            urgency_score += 40
        elif signal.score >= 80:
            urgency_score += 30
        elif signal.score >= 70:
            urgency_score += 20
        else:
            urgency_score += 10

        # Factor 2: MACD crossover freshness (max 30 points)
        if signal.macd_crossover:
            if signal.macd_bars_since == 1:
                urgency_score += 30
            elif signal.macd_bars_since == 2:
                urgency_score += 20
            else:
                urgency_score += 10

        # Factor 3: Volume spike (max 30 points)
        if signal.volume_ratio >= 2.5:
            urgency_score += 30
        elif signal.volume_ratio >= 2.0:
            urgency_score += 20
        elif signal.volume_ratio >= 1.5:
            urgency_score += 10

        # Use market-aware timezone
        market_id = signal.market or 'sp500'
        tz_str, _ = MARKET_TIMEZONES.get(market_id, ('US/Eastern', 'ET'))
        market_tz = pytz.timezone(tz_str)
        current_time = datetime.now(market_tz)
        current_hour = current_time.hour
        current_minute = current_time.minute

        # Determine market hours based on market
        if market_id == 'ftse100':
            open_hour, open_min, close_hour = 8, 0, 16
        elif market_id == 'hangseng':
            open_hour, open_min, close_hour = 9, 30, 16
        else:
            open_hour, open_min, close_hour = 9, 30, 16

        is_weekday = current_time.weekday() < 5
        market_open_time = current_hour > open_hour or (current_hour == open_hour and current_minute >= open_min)
        market_close_time = current_hour < close_hour
        is_market_hours = is_weekday and market_open_time and market_close_time

        if urgency_score >= 80:
            if is_market_hours:
                return "Place order within 30 minutes"
            else:
                return "Place order at market open"
        elif urgency_score >= 60:
            if is_market_hours:
                return "Place order within 1-2 hours"
            else:
                return "Place order at market open"
        elif urgency_score >= 40:
            if is_market_hours:
                return "Place order today"
            else:
                return "Place order tomorrow"
        else:
            return "Place order within 1-2 days"

    def _format_alert(self, signal: SignalScore) -> str:
        """
        Format a single signal as HTML message.

        Args:
            signal: SignalScore object

        Returns:
            Formatted HTML message
        """
        currency = signal.currency_symbol or '$'
        market_id = signal.market or 'sp500'
        market_label = _get_market_display_name(market_id)
        _, tz_abbr = MARKET_TIMEZONES.get(market_id, ('US/Eastern', 'ET'))

        # Market suffix for header
        market_suffix = f" ({market_label})" if market_label and market_id != 'sp500' else ""

        # MACD status
        macd_status = "Bullish Crossover" if signal.macd_crossover else "No Crossover"
        if signal.macd_crossover and signal.macd_bars_since > 1:
            macd_status += f" ({signal.macd_bars_since}d ago)"

        # Support info
        if signal.support_type:
            support_info = f"{abs(signal.distance_to_support)*100:.1f}% from {signal.support_type.upper()}"
        else:
            support_info = "Not near support"

        # Take profit info
        if signal.take_profit_price and signal.take_profit_pct:
            tp_info = f"{currency}{signal.take_profit_price:.2f} (+{signal.take_profit_pct*100:.1f}%)"
            tp_confidence = signal.take_profit_confidence or "low"
        else:
            tp_info = "Calculating..."
            tp_confidence = "low"

        # Estimated time to target
        if signal.estimated_days_to_target:
            days = signal.estimated_days_to_target
            if days == 1:
                time_estimate = "~1 trading day"
            elif days <= 5:
                time_estimate = f"~{days} trading days"
            elif days <= 10:
                time_estimate = "~1-2 weeks"
            elif days <= 20:
                time_estimate = "~2-4 weeks"
            else:
                time_estimate = "~1 month+"
        else:
            time_estimate = "Unknown"

        # Order urgency
        order_urgency = self._calculate_order_urgency(signal)

        # Dip info
        dip_info = f"{abs(signal.dip_from_high)*100:.1f}%" if signal.dip_from_high else "N/A"

        message = f"""
<b>BUY SIGNAL: {signal.ticker}{market_suffix}</b>

<b>Signal Score:</b> {signal.score:.1f}/100
<b>Current Price:</b> {currency}{signal.price:.2f}
<b>Dip from 20-day high:</b> -{dip_info}

<b>ACTION REQUIRED:</b> {order_urgency}

<b>TAKE PROFIT:</b> {tp_info}
<b>Est. Time to Target:</b> {time_estimate}
<i>Confidence: {tp_confidence}</i>

<b>Indicators:</b>
- RSI: {signal.rsi_value:.1f} (Score: {signal.rsi_score:.0f})
- MACD: {macd_status}
- Volume: {signal.volume_ratio:.1f}x average
- Support: {support_info}

<i>Generated at {signal.timestamp.strftime('%Y-%m-%d %H:%M')} {tz_abbr}</i>
"""
        return message.strip()

    def _format_batch_alert(self, signals: List[SignalScore]) -> str:
        """
        Format multiple signals as a summary message.

        Args:
            signals: List of SignalScore objects

        Returns:
            Formatted HTML message
        """
        # Determine market info from first signal
        market_id = signals[0].market or 'sp500'
        market_label = _get_market_display_name(market_id)
        currency = signals[0].currency_symbol or '$'
        _, tz_abbr = MARKET_TIMEZONES.get(market_id, ('US/Eastern', 'ET'))

        market_suffix = f" - {market_label}" if market_label else ""
        header = f"<b>BUY SIGNALS DETECTED ({len(signals)}){market_suffix}</b>\n\n"

        lines = []
        for i, signal in enumerate(signals, 1):
            sig_currency = signal.currency_symbol or '$'

            # Take profit info with time estimate
            if signal.take_profit_price and signal.take_profit_pct:
                tp_str = f"TP: {sig_currency}{signal.take_profit_price:.2f} (+{signal.take_profit_pct*100:.1f}%)"
                if signal.estimated_days_to_target:
                    days = signal.estimated_days_to_target
                    if days <= 5:
                        tp_str += f" ~{days}d"
                    elif days <= 10:
                        tp_str += " ~1-2wk"
                    elif days <= 20:
                        tp_str += " ~2-4wk"
                    else:
                        tp_str += " ~1mo+"
            else:
                tp_str = ""

            dip_str = f"-{abs(signal.dip_from_high)*100:.1f}%" if signal.dip_from_high else ""

            line = (
                f"<b>{i}. {signal.ticker}</b> - Score: {signal.score:.0f}\n"
                f"   {sig_currency}{signal.price:.2f} | RSI: {signal.rsi_value:.0f} | {dip_str}\n"
                f"   {tp_str}"
            )
            lines.append(line)

        footer = f"\n\n<i>Scan time: {signals[0].timestamp.strftime('%Y-%m-%d %H:%M')} {tz_abbr}</i>"

        return header + "\n\n".join(lines) + footer

    def send_startup_message(self, enabled_markets: Optional[List[str]] = None) -> bool:
        """Send a startup notification listing enabled markets."""
        if enabled_markets:
            markets_str = ", ".join(enabled_markets)
            message = (
                "<b>Market Watcher Started</b>\n\n"
                f"Watching: {markets_str}\n"
                "You will receive alerts when buy signals are detected."
            )
        else:
            message = (
                "<b>Market Watcher Started</b>\n\n"
                "S&P 500 dip-buying scanner is now running.\n"
                "You will receive alerts when buy signals are detected."
            )
        return self.send_message(message)

    def send_error_alert(self, error: str) -> bool:
        """Send an error notification."""
        message = f"<b>Scanner Error</b>\n\n{error}"
        return self.send_message(message)


def _get_market_display_name(market_id: str) -> str:
    """Get human-readable market name from market_id."""
    names = {
        'sp500': 'S&P 500',
        'ftse100': 'FTSE 100',
        'hangseng': 'Hang Seng',
    }
    return names.get(market_id, market_id)
