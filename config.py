"""
Market Watcher Configuration

All settings for the S&P 500 dip-buying alert system.
"""

import os

# Load environment variables from .env file (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use environment variables directly


# =============================================================================
# SCANNER CONFIGURATION
# =============================================================================

SCANNER_CONFIG = {
    # Signal thresholds
    'min_score': 50,              # Minimum signal score to trigger alert (0-100)
    'max_alerts': 10,             # Maximum alerts per scan cycle
    'cooldown_hours': 24,         # Don't re-alert same stock within this period

    # Data fetching
    'batch_size': 50,             # Stocks per yfinance batch
    'inter_batch_delay': 1.5,     # Seconds between batches (rate limiting)
    'lookback_days': 250,         # Days of history needed (for 200-day MA)

    # Indicator weights for composite score
    'weights': {
        'rsi': 0.25,
        'macd': 0.25,
        'volume': 0.20,
        'support': 0.30
    },

    # RSI settings
    'rsi_period': 14,
    'rsi_oversold': 30,           # Buy signal when RSI below this
    'rsi_overbought': 70,         # Reference only

    # MACD settings
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,

    # Volume settings
    'volume_lookback': 20,        # Days for average volume calculation
    'volume_spike_threshold': 1.5, # Volume must be this multiple of average

    # Support level settings
    'ma_periods': [50, 200],      # Moving average periods for support
    'support_tolerance': 0.05,    # Price within 5% of MA considered "near support"

    # Take profit settings
    'recent_high_lookback': 20,   # Days to look back for recent high
    'recovery_lookback_days': 365, # Days to analyze historical recoveries
    'max_take_profit_pct': 0.15,  # Cap take profit at 15%
}


# =============================================================================
# TELEGRAM CONFIGURATION
# =============================================================================

TELEGRAM_CONFIG = {
    'bot_token': os.getenv('TELEGRAM_BOT_TOKEN', ''),
    'chat_id': os.getenv('TELEGRAM_CHAT_ID', ''),
    'timeout': 10,                # Request timeout in seconds
    'parse_mode': 'HTML',         # Message formatting
}


# =============================================================================
# SCHEDULER CONFIGURATION
# =============================================================================

SCHEDULER_CONFIG = {
    'timezone': 'US/Eastern',     # Market timezone
    'market_open_hour': 9,        # Market opens at 9:30 AM ET
    'market_open_minute': 30,
    'market_close_hour': 16,      # Market closes at 4:00 PM ET
    'scan_minute': 30,            # Run at :30 past each hour
}


# =============================================================================
# MULTI-MARKET CONFIGURATION
# =============================================================================

MARKETS_CONFIG = {
    'sp500': {
        'enabled': True,
        'display_name': 'S&P 500',
        'timezone': 'US/Eastern',
        'market_open_hour': 9,
        'market_open_minute': 30,
        'market_close_hour': 16,
        'market_close_minute': 0,
        'scan_minute': 30,
        'ticker_suffix': '',
        'currency_symbol': '$',
        'currency_code': 'USD',
        'cache_file': 'sp500_cache.json',
    },
    'ftse100': {
        'enabled': True,
        'display_name': 'FTSE 100',
        'timezone': 'Europe/London',
        'market_open_hour': 8,
        'market_open_minute': 0,
        'market_close_hour': 16,
        'market_close_minute': 30,
        'scan_minute': 30,
        'ticker_suffix': '.L',
        'currency_symbol': '£',
        'currency_code': 'GBP',
        'cache_file': 'ftse100_cache.json',
    },
    'hangseng': {
        'enabled': True,
        'display_name': 'Hang Seng',
        'timezone': 'Asia/Hong_Kong',
        'market_open_hour': 9,
        'market_open_minute': 30,
        'market_close_hour': 16,
        'market_close_minute': 0,
        'scan_minute': 30,
        'ticker_suffix': '.HK',
        'currency_symbol': 'HK$',
        'currency_code': 'HKD',
        'cache_file': 'hangseng_cache.json',
    },
}


# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

LOGGING_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'log_file': 'logs/scanner.log',
    'max_bytes': 10_000_000,      # 10MB per log file
    'backup_count': 5,            # Keep 5 backup files
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
}


# =============================================================================
# DATA CONFIGURATION
# =============================================================================

DATA_CONFIG = {
    'cache_dir': 'data',
    'sp500_cache_file': 'sp500_cache.json',
    'sp500_cache_days': 7,        # Refresh S&P 500 list weekly
}


# =============================================================================
# STATE FILES
# =============================================================================

STATE_CONFIG = {
    'alert_state_file': 'alert_state.json',
}


# =============================================================================
# LEARNING SYSTEM CONFIGURATION
# =============================================================================

LEARNING_CONFIG = {
    'outcomes_file': 'alert_outcomes.json',
    'stop_loss_pct': 0.10,
    'max_hold_days': 30,
    'min_outcomes_for_analysis': 10,
    'performance_report_day': 'fri',
    'weight_history_file': 'weight_history.json',
    'min_weight': 0.10,
    'max_adjustment_per_cycle': 0.05,
    'min_outcomes_for_adjustment': 20,
    'auto_apply_weights': False,
    'outcome_check_hour': 17,
    'outcome_check_minute': 0,
}
