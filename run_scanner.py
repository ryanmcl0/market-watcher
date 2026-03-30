#!/usr/bin/env python3
"""
Market Watcher - Multi-Market Dip-Buying Scanner

Run this script to start monitoring stocks for buy opportunities across
S&P 500, FTSE 100, and Hang Seng markets.

Usage:
    python run_scanner.py              # Run scheduler (hourly during market hours)
    python run_scanner.py --once       # Run single scan for all markets
    python run_scanner.py --test       # Test Telegram connection
    python run_scanner.py --ticker AAPL       # Scan a single ticker (auto-detects market)
    python run_scanner.py --ticker AZN.L      # Scan FTSE 100 ticker
    python run_scanner.py --ticker 0700.HK    # Scan Hang Seng ticker
    python run_scanner.py --market ftse100     # Restrict to a single market
"""

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    DATA_CONFIG,
    LEARNING_CONFIG,
    LOGGING_CONFIG,
    MARKETS_CONFIG,
    SCANNER_CONFIG,
    SCHEDULER_CONFIG,
    STATE_CONFIG,
    TELEGRAM_CONFIG,
)
from src.alerts.alert_manager import AlertManager
from src.alerts.telegram_notifier import TelegramNotifier
from src.data.data_fetcher import DataFetcher
from src.data.market_universe import MarketUniverse
from src.data.sp500_universe import SP500Universe
from src.learning.outcome_tracker import OutcomeTracker
from src.learning.performance_analyzer import PerformanceAnalyzer
from src.learning.weight_adjuster import WeightAdjuster
from src.scanner.dip_scanner import DipScanner
from src.scanner.profit_target import ProfitTargetCalculator
from src.scanner.signal_scorer import SignalScorer
from src.scheduler.market_scheduler import MarketScheduler


def setup_logging() -> None:
    """Configure logging with file and console handlers."""
    log_level = getattr(logging, LOGGING_CONFIG['level'].upper(), logging.INFO)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Console handler (always added)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(LOGGING_CONFIG['format']))
    root_logger.addHandler(console_handler)

    # File handler with rotation (best-effort)
    try:
        log_file = Path(LOGGING_CONFIG['log_file'])
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=LOGGING_CONFIG['max_bytes'],
            backupCount=LOGGING_CONFIG['backup_count']
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(LOGGING_CONFIG['format']))
        root_logger.addHandler(file_handler)
    except (PermissionError, OSError) as e:
        root_logger.warning(f"Could not create log file, using console only: {e}")

    # Reduce noise from third-party libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('yfinance').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)


def detect_market_from_ticker(ticker: str) -> str:
    """Auto-detect market from ticker suffix."""
    ticker_upper = ticker.upper()
    if ticker_upper.endswith('.L'):
        return 'ftse100'
    elif ticker_upper.endswith('.HK'):
        return 'hangseng'
    return 'sp500'


def build_shared_components():
    """Build components shared across all markets."""
    data_fetcher = DataFetcher(cache_dir=DATA_CONFIG['cache_dir'])

    scorer = SignalScorer(
        weights=SCANNER_CONFIG['weights'],
        rsi_period=SCANNER_CONFIG['rsi_period'],
        rsi_oversold=SCANNER_CONFIG['rsi_oversold'],
        macd_fast=SCANNER_CONFIG['macd_fast'],
        macd_slow=SCANNER_CONFIG['macd_slow'],
        macd_signal=SCANNER_CONFIG['macd_signal'],
        volume_lookback=SCANNER_CONFIG['volume_lookback'],
        volume_threshold=SCANNER_CONFIG['volume_spike_threshold'],
        ma_periods=SCANNER_CONFIG['ma_periods'],
        support_tolerance=SCANNER_CONFIG['support_tolerance'],
        recent_high_lookback=SCANNER_CONFIG['recent_high_lookback']
    )

    profit_calculator = ProfitTargetCalculator(
        rsi_period=SCANNER_CONFIG['rsi_period'],
        rsi_oversold=SCANNER_CONFIG['rsi_oversold'],
        recovery_lookback_days=SCANNER_CONFIG['recovery_lookback_days'],
        recent_high_lookback=SCANNER_CONFIG['recent_high_lookback'],
        max_take_profit_pct=SCANNER_CONFIG['max_take_profit_pct']
    )

    notifier = TelegramNotifier(
        bot_token=TELEGRAM_CONFIG['bot_token'],
        chat_id=TELEGRAM_CONFIG['chat_id'],
        timeout=TELEGRAM_CONFIG['timeout'],
        parse_mode=TELEGRAM_CONFIG['parse_mode']
    )

    alert_manager = AlertManager(
        cooldown_hours=SCANNER_CONFIG['cooldown_hours'],
        state_file=STATE_CONFIG['alert_state_file']
    )

    outcome_tracker = OutcomeTracker(
        outcomes_file=LEARNING_CONFIG['outcomes_file'],
        stop_loss_pct=LEARNING_CONFIG['stop_loss_pct'],
        max_hold_days=LEARNING_CONFIG['max_hold_days'],
        data_fetcher=data_fetcher,
    )

    performance_analyzer = PerformanceAnalyzer(
        min_outcomes=LEARNING_CONFIG['min_outcomes_for_analysis'],
    )

    weight_adjuster = WeightAdjuster(
        current_weights=SCANNER_CONFIG['weights'],
        history_file=LEARNING_CONFIG['weight_history_file'],
        min_weight=LEARNING_CONFIG['min_weight'],
        max_adjustment=LEARNING_CONFIG['max_adjustment_per_cycle'],
        min_outcomes_for_adjustment=LEARNING_CONFIG['min_outcomes_for_adjustment'],
        auto_apply=LEARNING_CONFIG['auto_apply_weights'],
    )

    return {
        'data_fetcher': data_fetcher,
        'scorer': scorer,
        'profit_calculator': profit_calculator,
        'notifier': notifier,
        'alert_manager': alert_manager,
        'outcome_tracker': outcome_tracker,
        'performance_analyzer': performance_analyzer,
        'weight_adjuster': weight_adjuster,
    }


def build_market_scanner(market_id, market_config, shared):
    """Build a DipScanner for a specific market."""
    # Use SP500Universe for sp500 (preserves existing Wikipedia parsing),
    # MarketUniverse for all other markets
    if market_id == 'sp500':
        universe = SP500Universe(
            cache_file=os.path.join(
                DATA_CONFIG['cache_dir'],
                market_config['cache_file']
            ),
            cache_days=DATA_CONFIG.get('sp500_cache_days', 7)
        )
    else:
        universe = MarketUniverse(
            market_id=market_id,
            ticker_suffix=market_config['ticker_suffix'],
            cache_file=os.path.join(
                DATA_CONFIG['cache_dir'],
                market_config['cache_file']
            ),
            cache_days=DATA_CONFIG.get('sp500_cache_days', 7),
        )

    scanner = DipScanner(
        data_fetcher=shared['data_fetcher'],
        universe=universe,
        scorer=shared['scorer'],
        profit_calculator=shared['profit_calculator'],
        batch_size=SCANNER_CONFIG['batch_size'],
        inter_batch_delay=SCANNER_CONFIG['inter_batch_delay'],
        lookback_days=SCANNER_CONFIG['lookback_days'],
        market_id=market_id,
        currency_symbol=market_config['currency_symbol'],
    )

    return scanner


def create_scan_callback(scanner, notifier, alert_manager, outcome_tracker=None):
    """Create the callback function for scheduled scans."""
    logger = logging.getLogger(__name__)

    def scan_and_alert():
        logger.info(f"Starting scan cycle for {scanner.market_id}...")

        # Cleanup expired cooldowns
        alert_manager.cleanup_expired()

        # Run scan
        signals = scanner.scan(
            min_score=SCANNER_CONFIG['min_score'],
            top_n=SCANNER_CONFIG['max_alerts']
        )

        if not signals:
            logger.info(f"No signals found above threshold for {scanner.market_id}")
            return

        # Filter out signals in cooldown
        eligible_signals = alert_manager.filter_signals(signals)

        if not eligible_signals:
            logger.info(
                f"Found {len(signals)} signals for {scanner.market_id}, but all in cooldown"
            )
            return

        logger.info(
            f"Sending alerts for {len(eligible_signals)} {scanner.market_id} signals"
        )

        # Send alerts
        success = notifier.send_batch_alert(eligible_signals)

        if success:
            # Record alerts to prevent duplicates
            for signal in eligible_signals:
                alert_manager.record_alert(signal.ticker)

                # Record for outcome tracking
                if outcome_tracker is not None:
                    try:
                        outcome_tracker.record_signal(
                            signal,
                            weights=SCANNER_CONFIG['weights'],
                        )
                    except Exception as e:
                        logger.error(f"Failed to record outcome for {signal.ticker}: {e}")

            logger.info("Alerts sent successfully")
        else:
            logger.error("Failed to send alerts")

    return scan_and_alert


def create_learning_callback(
    outcome_tracker, performance_analyzer, weight_adjuster, notifier
):
    """Create the callback for the daily learning cycle."""
    logger = logging.getLogger(__name__)

    def learning_cycle():
        logger.info("Starting learning cycle...")

        # Step 1: Check and resolve pending outcomes
        resolved = outcome_tracker.check_outcomes()

        if resolved:
            notifier.send_outcome_update(resolved)

        # Step 2: Analyze performance
        completed = outcome_tracker.get_completed_outcomes()
        analysis = performance_analyzer.analyze(completed)

        if analysis is None:
            logger.info(
                f"Not enough data for analysis yet "
                f"({outcome_tracker.get_completed_count()} completed, "
                f"need {performance_analyzer.min_outcomes})"
            )
            return

        # Step 3: Send weekly report on Fridays
        report_day = LEARNING_CONFIG.get('performance_report_day', 'fri')
        if performance_analyzer.is_report_day(report_day):
            report_html = performance_analyzer.format_report_html(analysis)
            notifier.send_message(report_html)

        # Step 4: Suggest or apply weight adjustments
        result = weight_adjuster.calculate_adjusted_weights(analysis)

        if result is not None:
            adjustment_html = weight_adjuster.format_adjustment_html(result)
            notifier.send_message(adjustment_html)

            if result['applied']:
                # Update the live scanner weights
                SCANNER_CONFIG['weights'] = dict(result['weights'])
                logger.info(f"Live weights updated: {result['weights']}")

        logger.info("Learning cycle complete")

    return learning_cycle


def test_telegram(notifier):
    """Test Telegram connection."""
    print("Testing Telegram connection...")

    if not TELEGRAM_CONFIG['bot_token']:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        print("Set it in your .env file or as an environment variable")
        return False

    if not TELEGRAM_CONFIG['chat_id']:
        print("ERROR: TELEGRAM_CHAT_ID not set")
        print("Set it in your .env file or as an environment variable")
        return False

    if notifier.test_connection():
        print("Bot connection: OK")

        # List enabled markets
        enabled = [
            cfg['display_name']
            for cfg in MARKETS_CONFIG.values()
            if cfg.get('enabled')
        ]

        if notifier.send_startup_message(enabled_markets=enabled):
            print("Message send: OK")
            print(f"Markets: {', '.join(enabled)}")
            print("\nTelegram connection successful!")
            return True
        else:
            print("Message send: FAILED")
            return False
    else:
        print("Bot connection: FAILED")
        print("Check your TELEGRAM_BOT_TOKEN")
        return False


def scan_single_ticker(scanner, ticker, currency_symbol):
    """Scan a single ticker and print results."""
    print(f"Scanning {ticker}...")

    signal = scanner.scan_single(ticker)

    if signal is None:
        print(f"Could not analyze {ticker} - insufficient data")
        return

    cs = currency_symbol

    print(f"\n{'='*50}")
    print(f"Ticker: {signal.ticker}")
    print(f"Market: {signal.market}")
    print(f"Price: {cs}{signal.price:.2f}")
    print(f"Signal Score: {signal.score:.1f}/100")
    print(f"\nIndicators:")
    print(f"  RSI: {signal.rsi_value:.1f} (Score: {signal.rsi_score:.0f})")
    print(f"  MACD Crossover: {'Yes' if signal.macd_crossover else 'No'} (Score: {signal.macd_score:.0f})")
    print(f"  Volume Ratio: {signal.volume_ratio:.2f}x (Score: {signal.volume_score:.0f})")
    print(f"  Support: {signal.support_type or 'None'} (Score: {signal.support_score:.0f})")
    print(f"\nDip from 20-day high: {abs(signal.dip_from_high)*100:.1f}%")

    if signal.take_profit_price:
        print(f"\nTake Profit Target: {cs}{signal.take_profit_price:.2f} (+{signal.take_profit_pct*100:.1f}%)")
        print(f"Confidence: {signal.take_profit_confidence}")

    print(f"{'='*50}")

    if signal.score >= SCANNER_CONFIG['min_score']:
        print("\nThis stock meets the alert threshold!")
    else:
        print(f"\nBelow alert threshold ({SCANNER_CONFIG['min_score']})")


def get_enabled_markets(market_filter=None):
    """Get enabled market configs, optionally filtered to a single market."""
    markets = {}
    for market_id, config in MARKETS_CONFIG.items():
        if not config.get('enabled'):
            continue
        if market_filter and market_id != market_filter:
            continue
        markets[market_id] = config
    return markets


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Multi-Market Dip-Buying Scanner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run single scan for all enabled markets'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test Telegram connection'
    )
    parser.add_argument(
        '--ticker',
        type=str,
        help='Scan a single ticker (auto-detects market from suffix)'
    )
    parser.add_argument(
        '--market',
        type=str,
        choices=list(MARKETS_CONFIG.keys()),
        help='Restrict to a single market (e.g. sp500, ftse100, hangseng)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--learn',
        action='store_true',
        help='Run learning cycle manually (check outcomes, analyze, adjust weights)'
    )

    args = parser.parse_args()

    # Override log level if debug
    if args.debug:
        LOGGING_CONFIG['level'] = 'DEBUG'

    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Market Watcher starting...")

    # Build shared components
    shared = build_shared_components()

    # Handle test mode (doesn't need scanners)
    if args.test:
        success = test_telegram(shared['notifier'])
        sys.exit(0 if success else 1)

    # Handle single ticker scan
    if args.ticker:
        ticker = args.ticker.upper()
        market_id = args.market or detect_market_from_ticker(ticker)
        market_config = MARKETS_CONFIG[market_id]

        scanner = build_market_scanner(market_id, market_config, shared)
        scan_single_ticker(scanner, ticker, market_config['currency_symbol'])
        sys.exit(0)

    # Handle learning cycle
    if args.learn:
        learning_callback = create_learning_callback(
            shared['outcome_tracker'],
            shared['performance_analyzer'],
            shared['weight_adjuster'],
            shared['notifier'],
        )
        learning_callback()
        sys.exit(0)

    # Determine enabled markets
    enabled_markets = get_enabled_markets(args.market)

    if not enabled_markets:
        logger.error("No markets enabled. Check MARKETS_CONFIG in config.py")
        sys.exit(1)

    # Build per-market scanners and callbacks
    market_scanners = {}
    market_callbacks = {}

    for market_id, market_config in enabled_markets.items():
        scanner = build_market_scanner(market_id, market_config, shared)
        market_scanners[market_id] = scanner

        callback = create_scan_callback(
            scanner,
            shared['notifier'],
            shared['alert_manager'],
            shared['outcome_tracker'],
        )
        market_callbacks[market_id] = callback

    # Handle --once mode
    if args.once:
        for market_id, callback in market_callbacks.items():
            display = enabled_markets[market_id]['display_name']
            logger.info(f"Running scan for {display}...")
            callback()
        sys.exit(0)

    # Default: run scheduled scanner
    enabled_display_names = [
        cfg['display_name'] for cfg in enabled_markets.values()
    ]

    # Send startup message
    if TELEGRAM_CONFIG['bot_token'] and TELEGRAM_CONFIG['chat_id']:
        shared['notifier'].send_startup_message(
            enabled_markets=enabled_display_names
        )

    scheduler = MarketScheduler(
        timezone=SCHEDULER_CONFIG['timezone'],
    )

    # Register each market's schedule
    for market_id, market_config in enabled_markets.items():
        # Hang Seng has a lunch break 12:00-13:00 HKT
        lunch_break = (12, 13) if market_id == 'hangseng' else None

        scheduler.add_market_schedule(
            market_id=market_id,
            callback=market_callbacks[market_id],
            timezone=market_config['timezone'],
            market_open_hour=market_config['market_open_hour'],
            market_open_minute=market_config['market_open_minute'],
            market_close_hour=market_config['market_close_hour'],
            market_close_minute=market_config.get('market_close_minute', 0),
            scan_minute=market_config['scan_minute'],
            display_name=market_config['display_name'],
            lunch_break=lunch_break,
        )

    # Add daily learning job (runs once after all markets close)
    learning_callback = create_learning_callback(
        shared['outcome_tracker'],
        shared['performance_analyzer'],
        shared['weight_adjuster'],
        shared['notifier'],
    )
    scheduler.add_daily_job(
        callback=learning_callback,
        hour=LEARNING_CONFIG['outcome_check_hour'],
        minute=LEARNING_CONFIG['outcome_check_minute'],
        job_id='daily_learning',
        name='Daily Learning Cycle',
    )

    scheduler.start()


if __name__ == '__main__':
    main()
