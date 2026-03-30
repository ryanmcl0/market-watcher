"""
Market Scheduler Module

APScheduler-based hourly execution during market hours.
Supports multiple markets with independent schedules.
"""

import logging
from datetime import datetime
from typing import Callable, Dict, Optional

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class MarketScheduler:
    """Schedule scans during market hours for multiple markets."""

    def __init__(
        self,
        scan_callback: Optional[Callable] = None,
        timezone: str = 'US/Eastern',
        market_open_hour: int = 9,
        market_open_minute: int = 30,
        market_close_hour: int = 16,
        scan_minute: int = 30
    ):
        """
        Initialize the market scheduler.

        Supports both legacy single-market mode (passing scan_callback)
        and multi-market mode (using add_market_schedule).

        Args:
            scan_callback: Function to call for each scan (legacy single-market)
            timezone: Market timezone (legacy, used as default)
            market_open_hour: Hour market opens (legacy)
            market_open_minute: Minute market opens (legacy)
            market_close_hour: Hour market closes (legacy)
            scan_minute: Minute past each hour to run scan (legacy)
        """
        self.default_timezone = pytz.timezone(timezone)
        self.scan_callback = scan_callback
        self.market_open_hour = market_open_hour
        self.market_open_minute = market_open_minute
        self.market_close_hour = market_close_hour
        self.scan_minute = scan_minute

        self.scheduler: Optional[BlockingScheduler] = None
        self._pending_jobs = []
        self._market_schedules: Dict[str, dict] = {}

    def add_market_schedule(
        self,
        market_id: str,
        callback: Callable,
        timezone: str,
        market_open_hour: int,
        market_open_minute: int,
        market_close_hour: int,
        market_close_minute: int = 0,
        scan_minute: int = 30,
        display_name: str = '',
        lunch_break: Optional[tuple] = None,
    ) -> None:
        """
        Register a market's scan schedule.

        Args:
            market_id: Unique market identifier (e.g. 'sp500', 'ftse100')
            callback: Scan function for this market
            timezone: Market timezone string
            market_open_hour: Hour market opens (24h)
            market_open_minute: Minute market opens
            market_close_hour: Hour market closes (24h)
            market_close_minute: Minute market closes
            scan_minute: Minute past each hour to run scan
            display_name: Human-readable market name
            lunch_break: Optional (start_hour, end_hour) for lunch break
        """
        schedule = {
            'market_id': market_id,
            'callback': callback,
            'timezone': pytz.timezone(timezone),
            'timezone_str': timezone,
            'market_open_hour': market_open_hour,
            'market_open_minute': market_open_minute,
            'market_close_hour': market_close_hour,
            'market_close_minute': market_close_minute,
            'scan_minute': scan_minute,
            'display_name': display_name or market_id,
            'lunch_break': lunch_break,
        }
        self._market_schedules[market_id] = schedule

    def add_daily_job(
        self,
        callback: Callable,
        hour: int,
        minute: int,
        job_id: str,
        name: str
    ) -> None:
        """
        Add a daily job that runs Mon-Fri at a specific time.

        Can be called before start() - jobs are queued and added when
        the scheduler is created.
        """
        job_spec = {
            'callback': callback,
            'hour': hour,
            'minute': minute,
            'job_id': job_id,
            'name': name,
        }

        if self.scheduler is not None:
            self._add_job_to_scheduler(job_spec)
        else:
            self._pending_jobs.append(job_spec)
            logger.info(f"Queued daily job '{name}' for {hour:02d}:{minute:02d}")

    def start(self) -> None:
        """Start the scheduler with all registered market schedules."""
        self.scheduler = BlockingScheduler(timezone=self.default_timezone)

        if self._market_schedules:
            # Multi-market mode
            for market_id, schedule in self._market_schedules.items():
                self._add_market_jobs(schedule)
        elif self.scan_callback:
            # Legacy single-market mode
            self._add_legacy_jobs()

        # Flush any jobs queued before start()
        for job_spec in self._pending_jobs:
            self._add_job_to_scheduler(job_spec)
        self._pending_jobs.clear()

        self._log_schedule()

        try:
            logger.info("Scheduler started. Press Ctrl+C to exit.")
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped by user")
            self.stop()

    def stop(self) -> None:
        """Stop the scheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def run_once(self) -> None:
        """Execute a single scan immediately."""
        logger.info("Running single scan...")
        if self.scan_callback:
            self._run_scan(self.scan_callback, 'default')

    def is_market_open(self, market_id: Optional[str] = None) -> bool:
        """
        Check if a market is currently open.

        Args:
            market_id: Market to check. If None, checks default/legacy market.

        Returns:
            True if market is open
        """
        if market_id and market_id in self._market_schedules:
            schedule = self._market_schedules[market_id]
            tz = schedule['timezone']
            now = datetime.now(tz)

            if now.weekday() >= 5:
                return False

            market_open = now.replace(
                hour=schedule['market_open_hour'],
                minute=schedule['market_open_minute'],
                second=0, microsecond=0
            )
            market_close = now.replace(
                hour=schedule['market_close_hour'],
                minute=schedule['market_close_minute'],
                second=0, microsecond=0
            )

            if not (market_open <= now <= market_close):
                return False

            # Check lunch break
            lunch = schedule.get('lunch_break')
            if lunch:
                lunch_start = now.replace(hour=lunch[0], minute=0, second=0)
                lunch_end = now.replace(hour=lunch[1], minute=0, second=0)
                if lunch_start <= now < lunch_end:
                    return False

            return True

        # Legacy fallback
        now = datetime.now(self.default_timezone)
        if now.weekday() >= 5:
            return False
        market_open = now.replace(
            hour=self.market_open_hour, minute=self.market_open_minute,
            second=0, microsecond=0
        )
        market_close = now.replace(
            hour=self.market_close_hour, minute=0, second=0, microsecond=0
        )
        return market_open <= now <= market_close

    def get_next_scan_time(self) -> Optional[datetime]:
        """Get the next scheduled scan time."""
        if not self.scheduler:
            return None

        jobs = self.scheduler.get_jobs()
        if not jobs:
            return None

        next_times = []
        for job in jobs:
            nrt = getattr(job, 'next_run_time', None)
            if nrt:
                next_times.append(nrt)

        return min(next_times) if next_times else None

    def _add_market_jobs(self, schedule: dict) -> None:
        """Add hourly and market-open scan jobs for a single market."""
        market_id = schedule['market_id']
        tz = schedule['timezone']
        callback = schedule['callback']
        open_hour = schedule['market_open_hour']
        open_minute = schedule['market_open_minute']
        close_hour = schedule['market_close_hour']
        scan_minute = schedule['scan_minute']
        lunch = schedule.get('lunch_break')
        display = schedule['display_name']

        # Build scan hours: from open hour to close_hour - 1
        scan_hours = list(range(open_hour, close_hour))

        # Exclude lunch break hours if applicable
        if lunch:
            scan_hours = [h for h in scan_hours if h < lunch[0] or h >= lunch[1]]

        hours_str = ','.join(str(h) for h in scan_hours)

        # Hourly scan trigger
        hourly_trigger = CronTrigger(
            day_of_week='mon-fri',
            hour=hours_str,
            minute=scan_minute,
            timezone=tz
        )

        def make_scan_cb(cb, mid):
            def _scan():
                self._run_scan(cb, mid)
            return _scan

        self.scheduler.add_job(
            make_scan_cb(callback, market_id),
            hourly_trigger,
            id=f'hourly_scan_{market_id}',
            name=f'Hourly Scan ({display})',
            misfire_grace_time=300
        )

        # Market open scan (5 minutes after open)
        open_scan_minute = open_minute + 5
        open_scan_hour = open_hour
        if open_scan_minute >= 60:
            open_scan_minute -= 60
            open_scan_hour += 1

        open_trigger = CronTrigger(
            day_of_week='mon-fri',
            hour=open_scan_hour,
            minute=open_scan_minute,
            timezone=tz
        )

        self.scheduler.add_job(
            make_scan_cb(callback, market_id),
            open_trigger,
            id=f'market_open_scan_{market_id}',
            name=f'Market Open Scan ({display})',
            misfire_grace_time=300
        )

        logger.info(
            f"Registered {display}: hours {hours_str} at :{scan_minute:02d}, "
            f"open scan at {open_scan_hour:02d}:{open_scan_minute:02d} "
            f"({schedule['timezone_str']})"
        )

    def _add_legacy_jobs(self) -> None:
        """Add jobs for legacy single-market mode."""
        hourly_trigger = CronTrigger(
            day_of_week='mon-fri',
            hour='9-15',
            minute=self.scan_minute,
            timezone=self.default_timezone
        )

        self.scheduler.add_job(
            lambda: self._run_scan(self.scan_callback, 'sp500'),
            hourly_trigger,
            id='hourly_scan',
            name='Hourly Market Scan',
            misfire_grace_time=300
        )

        open_trigger = CronTrigger(
            day_of_week='mon-fri',
            hour=self.market_open_hour,
            minute=self.market_open_minute + 5,
            timezone=self.default_timezone
        )

        self.scheduler.add_job(
            lambda: self._run_scan(self.scan_callback, 'sp500'),
            open_trigger,
            id='market_open_scan',
            name='Market Open Scan',
            misfire_grace_time=300
        )

    def _add_job_to_scheduler(self, job_spec: dict) -> None:
        """Add a single daily job to the running scheduler."""
        trigger = CronTrigger(
            day_of_week='mon-fri',
            hour=job_spec['hour'],
            minute=job_spec['minute'],
            timezone=self.default_timezone
        )

        def _wrapped():
            try:
                logger.info(f"Running daily job: {job_spec['name']}")
                job_spec['callback']()
                logger.info(f"Daily job completed: {job_spec['name']}")
            except Exception as e:
                logger.error(f"Daily job '{job_spec['name']}' failed: {e}", exc_info=True)

        self.scheduler.add_job(
            _wrapped,
            trigger,
            id=job_spec['job_id'],
            name=job_spec['name'],
            misfire_grace_time=300
        )
        logger.info(
            f"Added daily job '{job_spec['name']}' at "
            f"{job_spec['hour']:02d}:{job_spec['minute']:02d}"
        )

    def _run_scan(self, callback: Callable, market_id: str) -> None:
        """Execute a scan callback with error handling."""
        try:
            logger.info(f"Starting scheduled scan for {market_id}")
            callback()
            logger.info(f"Scheduled scan completed for {market_id}")
        except Exception as e:
            logger.error(f"Scan failed for {market_id}: {e}", exc_info=True)

    def _log_schedule(self) -> None:
        """Log the scheduled jobs."""
        if self._market_schedules:
            logger.info("Scheduled market scans:")
            for market_id, schedule in self._market_schedules.items():
                display = schedule['display_name']
                tz = schedule['timezone_str']
                oh = schedule['market_open_hour']
                om = schedule['market_open_minute']
                ch = schedule['market_close_hour']
                cm = schedule['market_close_minute']
                lunch = schedule.get('lunch_break')
                lunch_str = f" (lunch {lunch[0]:02d}:00-{lunch[1]:02d}:00)" if lunch else ""
                logger.info(
                    f"  - {display}: {oh:02d}:{om:02d}-{ch:02d}:{cm:02d} {tz}{lunch_str}"
                )
        else:
            logger.info("Scheduled scans:")
            logger.info("  - Hourly: 9:30 AM - 3:30 PM ET, Monday-Friday")
            logger.info("  - Market open: 9:35 AM ET, Monday-Friday")

        next_scan = self.get_next_scan_time()
        if next_scan:
            logger.info(f"  - Next scan: {next_scan}")
