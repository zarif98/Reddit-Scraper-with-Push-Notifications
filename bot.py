"""Entrypoint for the Reddit monitor bot.

Wiring + main loop only; the implementation lives in the reddit_scraper package.
"""
import time
import logging
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from colorama import init, Fore, Style

from reddit_scraper import config, credentials, health
from reddit_scraper.monitor import RedditMonitor
# Re-exported for the test suite / external callers.
from reddit_scraper.sources import fetch_posts_json, fetch_thread_comments_json  # noqa: F401

# Initialize colorama and logging
init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.colors = {
            logging.DEBUG: Fore.CYAN,
            logging.INFO: Fore.GREEN,
            logging.WARNING: Fore.YELLOW,
            logging.ERROR: Fore.RED,
            logging.CRITICAL: Fore.RED + Style.BRIGHT,
        }

    def format(self, record):
        color = self.colors.get(record.levelno, Fore.WHITE)
        record.msg = f"{color}{record.msg}{Style.RESET_ALL}"
        return super().format(record)


_formatter = ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s')
_handler = logging.StreamHandler()
_handler.setFormatter(_formatter)
logging.basicConfig(level=logging.INFO, handlers=[_handler])

# Load environment variables from .env file
load_dotenv()


def main():
    credentials.detect_auth_capability()
    reddit = credentials.authenticate_reddit()  # Authenticate Reddit once (None if no creds)

    # Initial config load
    cfg = config.read_config()
    if cfg is None:
        exit(1)

    subreddits_to_search = cfg.get('subreddits_to_search', [])
    config.apply_source_order_from_config(cfg)
    last_config_mtime = config.get_config_mtime()

    # Track last run time for each monitor by ID
    last_run_times = {}

    loop_time = 0
    while True:
        # Check if config file has been modified
        current_mtime = config.get_config_mtime()
        if current_mtime and last_config_mtime and current_mtime > last_config_mtime:
            logging.info("Configuration file changed, reloading...")
            new_config = config.read_config()
            if new_config is not None:
                cfg = new_config
                subreddits_to_search = cfg.get('subreddits_to_search', [])
                config.apply_source_order_from_config(cfg)
                last_config_mtime = current_mtime
                logging.info("Configuration reloaded successfully.")
            else:
                logging.warning("Failed to reload configuration, using previous settings.")

        # Filter to only enabled monitors
        enabled_monitors = [m for m in subreddits_to_search if m.get('enabled', True)]

        # Determine which monitors are due to run based on their refresh interval
        current_time = time.time()
        monitors_to_run = []

        for monitor in enabled_monitors:
            monitor_id = monitor.get('id', monitor.get('subreddit', 'unknown'))
            # Use cooldown_minutes as the per-monitor refresh interval (default 10 min)
            refresh_interval = monitor.get('cooldown_minutes', 10) * 60  # seconds

            last_run = last_run_times.get(monitor_id, 0)
            time_since_last_run = current_time - last_run

            if time_since_last_run >= refresh_interval:
                monitors_to_run.append(monitor)
                last_run_times[monitor_id] = current_time
                logging.info(f"Running monitor: {monitor.get('name', monitor.get('subreddit'))} "
                             f"(interval: {monitor.get('cooldown_minutes', 10)} min)")
            else:
                time_remaining = int((refresh_interval - time_since_last_run) / 60)
                logging.debug(f"Skipping {monitor.get('name', monitor.get('subreddit'))} - {time_remaining} min until next run")

        if monitors_to_run:
            with ThreadPoolExecutor() as executor:
                futures = [executor.submit(RedditMonitor(reddit, **params).run) for params in monitors_to_run]

                for future in futures:
                    try:
                        future.result()
                    except Exception as e:
                        error_message = f"Error during subreddit search: {e}"
                        logging.error(error_message)
                        RedditMonitor(reddit, subreddit='error', keywords=[]).send_error_notification(error_message)
        else:
            logging.debug("No monitors due to run this cycle")

        # Report health to Uptime Kuma (up only if a Reddit fetch succeeded recently)
        health.send_kuma_heartbeat()

        # Base cycle interval - check every 2 minutes (monitors have their own schedules)
        logging.info(f"Cycle {loop_time} complete. Sleeping for 2 minutes before next check...")
        loop_time += 1
        time.sleep(120)  # Check every 2 minutes for lower CPU usage


if __name__ == "__main__":
    main()
