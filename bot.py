import praw
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os
import pickle
from concurrent.futures import ThreadPoolExecutor
from colorama import init, Fore, Style
import json
import logging
import apprise


# --- Define paths for mounted data ---
DATA_DIR = '/data' # Base directory for mounted host data
CONFIG_FILE_PATH = os.path.join(DATA_DIR, 'search.json')
PROCESSED_SUBMISSIONS_FILE_PATH = os.path.join(DATA_DIR, 'processed_submissions.pkl')
# -------------------------------------

# Initialize colorama and logging
init(autoreset=True)

# Custom logging formatter with colors
class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.colors = {
            logging.DEBUG: Fore.CYAN,
            logging.INFO: Fore.GREEN,
            logging.WARNING: Fore.YELLOW,
            logging.ERROR: Fore.RED,
            logging.CRITICAL: Fore.RED + Style.BRIGHT
        }

    def format(self, record):
        color = self.colors.get(record.levelno, Fore.WHITE)
        record.msg = f"{color}{record.msg}{Style.RESET_ALL}"
        return super().format(record)

# Set up logging configuration
formatter = ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler])

# Load environment variables from .env file
load_dotenv()

# Credentials file path
CREDENTIALS_FILE_PATH = os.path.join(DATA_DIR, 'credentials.json')


def load_credentials():
    """Load credentials from credentials.json file with env var fallback."""
    creds = {}
    
    # Try to load from credentials file first
    try:
        with open(CREDENTIALS_FILE_PATH, 'r') as f:
            creds = json.load(f)
            logging.info(f"Loaded credentials from: {CREDENTIALS_FILE_PATH}")
    except FileNotFoundError:
        logging.info("No credentials file found, using environment variables")
    except json.JSONDecodeError:
        logging.warning("Invalid credentials file, using environment variables")
    
    # Build notification URLs list
    notification_urls = creds.get('notification_urls', [])
    
    # Auto-migrate old Pushover credentials to Apprise URL format
    if not notification_urls:
        pushover_token = creds.get('pushover_app_token') or os.getenv('PUSHOVER_APP_TOKEN')
        pushover_user = creds.get('pushover_user_key') or os.getenv('PUSHOVER_USER_KEY')
        if pushover_token and pushover_user:
            # Convert to Apprise Pushover URL format: pover://user_key@app_token
            notification_urls = [f"pover://{pushover_user}@{pushover_token}"]
            logging.info("Auto-migrated Pushover credentials to Apprise format")
    
    # Map to standard names with env var fallback
    return {
        'notification_urls': notification_urls,
        'reddit_client_id': creds.get('reddit_client_id') or os.getenv('REDDIT_CLIENT_ID'),
        'reddit_client_secret': creds.get('reddit_client_secret') or os.getenv('REDDIT_CLIENT_SECRET'),
        'reddit_user_agent': creds.get('reddit_user_agent') or os.getenv('REDDIT_USER_AGENT'),
        'reddit_username': creds.get('reddit_username') or os.getenv('REDDIT_USERNAME'),
        'reddit_password': creds.get('reddit_password') or os.getenv('REDDIT_PASSWORD'),
    }


# Load credentials globally (with retry loop for first-time setup)
CREDENTIALS = None

def wait_for_credentials():
    """Wait for Reddit credentials to be configured via web UI."""
    global CREDENTIALS
    # Only Reddit credentials are required - notifications are optional
    required_creds = ['reddit_client_id', 'reddit_client_secret', 'reddit_user_agent', 'reddit_username', 'reddit_password']
    
    while True:
        CREDENTIALS = load_credentials()
        missing = [key for key in required_creds if not CREDENTIALS.get(key)]
        
        if not missing:
            # Warn if no notification URLs configured
            if not CREDENTIALS.get('notification_urls'):
                logging.warning("⚠️ No notification services configured - notifications disabled")
                logging.info("Configure notifications via web UI at http://YOUR_NAS_IP:8080 → Settings")
            else:
                logging.info(f"🔔 Configured {len(CREDENTIALS['notification_urls'])} notification service(s)")
            logging.info("✅ Reddit credentials configured! Starting bot...")
            return
        
        logging.warning(f'⏳ Waiting for Reddit credentials: {", ".join(missing)}')
        logging.info('Configure via web UI at http://YOUR_NAS_IP:8080')
        time.sleep(30)  # Check every 30 seconds


wait_for_credentials()


class RedditMonitor:
    processed_submissions_file = PROCESSED_SUBMISSIONS_FILE_PATH
    max_file_size = 5 * 1024 * 1024  # 5 MB

    def __init__(self, reddit, subreddit, keywords, min_upvotes=None, exclude_keywords=None, 
                 domain_contains=None, domain_excludes=None, flair_contains=None,
                 author_includes=None, author_excludes=None, **kwargs):
        self.reddit = reddit
        self.subreddit = subreddit
        self.keywords = keywords
        self.min_upvotes = min_upvotes
        self.exclude_keywords = exclude_keywords or []
        self.domain_contains = domain_contains or []
        self.domain_excludes = domain_excludes or []
        self.flair_contains = flair_contains or []
        self.author_includes = author_includes or []
        self.author_excludes = author_excludes or []
        self.load_processed_submissions()

    def send_push_notification(self, message, title=None):
        """Send notification via Apprise to all configured services."""
        notification_urls = CREDENTIALS.get('notification_urls', [])
        
        if not notification_urls:
            logging.debug("No notification services configured, skipping notification")
            return
        
        logging.info(f"Sending notification to {len(notification_urls)} service(s)...")
        
        try:
            # Create Apprise instance and add all configured URLs
            apobj = apprise.Apprise()
            for url in notification_urls:
                apobj.add(url)
            
            # Send the notification
            result = apobj.notify(
                body=message,
                title=title or f"Reddit Alert: r/{self.subreddit}",
            )
            
            if result:
                logging.info("✅ Notification sent successfully")
            else:
                logging.warning("⚠️ Some notifications may have failed")
        except Exception as e:
            logging.error(f"Error sending notification: {e}")

    def load_processed_submissions(self):
        try:
            with open(self.processed_submissions_file, 'rb') as file:
                self.processed_submissions = pickle.load(file)
        except FileNotFoundError:
            self.processed_submissions = set()

    def save_processed_submissions(self):
        if os.path.exists(self.processed_submissions_file) and os.path.getsize(self.processed_submissions_file) > self.max_file_size:
            logging.info("Processed submissions file exceeded max size. Deleting and creating a new one.")
            os.remove(self.processed_submissions_file)
            self.processed_submissions = set()

        with open(self.processed_submissions_file, 'wb') as file:
            pickle.dump(self.processed_submissions, file)

    def send_error_notification(self, error_message):
        """Send error notification via Apprise to all configured services."""
        notification_urls = CREDENTIALS.get('notification_urls', [])
        
        if not notification_urls:
            logging.warning("No notification services configured, cannot send error notification")
            return
        
        logging.error("Error occurred. Sending error notification...")
        try:
            apobj = apprise.Apprise()
            for url in notification_urls:
                apobj.add(url)
            
            result = apobj.notify(
                body=f"Error in Reddit Scraper: {error_message}",
                title="⚠️ Reddit Monitor Error",
            )
            
            if result:
                logging.info("Error notification sent successfully")
            else:
                logging.warning("Error notification may have failed")
        except Exception as e:
            logging.error(f"Error sending error notification: {e}")

    def search_reddit_for_keywords(self):
        try:
            logging.info(f"Searching '{self.subreddit}' subreddit for keywords...")
            subreddit_obj = self.reddit.subreddit(self.subreddit)
            notifications_count = 0

            for submission in subreddit_obj.new(limit=10):  # Adjust the limit as needed
                submission_id = f"{self.subreddit}-{submission.id}"
                if submission_id in self.processed_submissions:
                    logging.info(f"Skipping duplicate post: {submission.title}")
                    continue

                message = f"Match found in '{self.subreddit}' subreddit:\n" \
                          f"Title: {submission.title}\n" \
                          f"URL: {submission.url}\n" \
                          f"Upvotes: {submission.score}\n" \
                          f"Permalink: https://www.reddit.com{submission.permalink}\n" \
                          ##f"Author: {submission.author.name}"
                # Check if title contains all required keywords and none of the excluded ones
                title_lower = submission.title.lower()
                has_all_keywords = all(keyword in title_lower for keyword in self.keywords)
                has_excluded = any(keyword in title_lower for keyword in self.exclude_keywords)
                meets_upvotes = self.min_upvotes is None or submission.score >= self.min_upvotes
                
                # Domain filters
                submission_domain = submission.domain.lower() if hasattr(submission, 'domain') else ''
                meets_domain_contains = not self.domain_contains or any(d in submission_domain for d in self.domain_contains)
                meets_domain_excludes = not any(d in submission_domain for d in self.domain_excludes)
                
                # Flair filter
                submission_flair = (submission.link_flair_text or '').lower() if hasattr(submission, 'link_flair_text') else ''
                meets_flair = not self.flair_contains or any(f.lower() in submission_flair for f in self.flair_contains)
                
                # Author filters
                author_name = submission.author.name.lower() if submission.author else ''
                meets_author_includes = not self.author_includes or author_name in [a.lower() for a in self.author_includes]
                meets_author_excludes = author_name not in [a.lower() for a in self.author_excludes]
                
                if (has_all_keywords and not has_excluded and meets_upvotes and 
                    meets_domain_contains and meets_domain_excludes and 
                    meets_flair and meets_author_includes and meets_author_excludes):
                    logging.info(message)
                    self.send_push_notification(message)
                    logging.info('-' * 40)

                    self.processed_submissions.add(submission_id)
                    self.save_processed_submissions()  # Save the processed submissions to file
                    notifications_count += 1

            logging.info(f"Finished searching '{self.subreddit}' subreddit for keywords.")
        except Exception as e:
            error_message = f"Error during Reddit search for '{self.subreddit}': {e}"
            logging.error(error_message)
            self.send_error_notification(error_message)

def authenticate_reddit():
    logging.info("Authenticating Reddit...")
    return praw.Reddit(client_id=CREDENTIALS['reddit_client_id'],
                       client_secret=CREDENTIALS['reddit_client_secret'],
                       user_agent=CREDENTIALS['reddit_user_agent'],
                       username=CREDENTIALS['reddit_username'],
                       password=CREDENTIALS['reddit_password'])

def load_config():
    """Load configuration from search.json file."""
    logging.info(f"Loading configuration from: {CONFIG_FILE_PATH}")
    try:
        with open(CONFIG_FILE_PATH, 'r') as config_file:
            config = json.load(config_file)
        return config
    except FileNotFoundError:
        logging.error(f"Configuration file not found at: {CONFIG_FILE_PATH}")
        return None
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from configuration file: {CONFIG_FILE_PATH}")
        return None

def get_config_mtime():
    """Get the modification time of the config file."""
    try:
        return os.path.getmtime(CONFIG_FILE_PATH)
    except OSError:
        return None

def main():
    reddit = authenticate_reddit()  # Authenticate Reddit once

    # Initial config load
    config = load_config()
    if config is None:
        exit(1)
    
    subreddits_to_search = config.get('subreddits_to_search', [])
    last_config_mtime = get_config_mtime()
    
    # Track last run time for each monitor by ID
    last_run_times = {}
    
    loopTime = 0
    while True:
        # Check if config file has been modified
        current_mtime = get_config_mtime()
        if current_mtime and last_config_mtime and current_mtime > last_config_mtime:
            logging.info("Configuration file changed, reloading...")
            new_config = load_config()
            if new_config is not None:
                config = new_config
                subreddits_to_search = config.get('subreddits_to_search', [])
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
            refresh_interval = monitor.get('cooldown_minutes', 10) * 60  # Convert to seconds
            
            last_run = last_run_times.get(monitor_id, 0)
            time_since_last_run = current_time - last_run
            
            if time_since_last_run >= refresh_interval:
                monitors_to_run.append(monitor)
                last_run_times[monitor_id] = current_time
                logging.info(f"Running monitor: {monitor.get('name', monitor.get('subreddit'))} (interval: {monitor.get('cooldown_minutes', 10)} min)")
            else:
                time_remaining = int((refresh_interval - time_since_last_run) / 60)
                logging.debug(f"Skipping {monitor.get('name', monitor.get('subreddit'))} - {time_remaining} min until next run")
        
        if monitors_to_run:
            with ThreadPoolExecutor() as executor:
                futures = [executor.submit(RedditMonitor(reddit, **params).search_reddit_for_keywords) for params in monitors_to_run]

                for future in futures:
                    try:
                        future.result()
                    except Exception as e:
                        error_message = f"Error during subreddit search: {e}"
                        logging.error(error_message)
                        RedditMonitor(reddit, subreddit='error', keywords=[]).send_error_notification(error_message)
        else:
            logging.debug("No monitors due to run this cycle")

        # Base cycle interval - check every 2 minutes (monitors have their own schedules)
        logging.info(f"Cycle {loopTime} complete. Sleeping for 2 minutes before next check...")
        loopTime += 1
        time.sleep(120)  # Check every 2 minutes for lower CPU usage

if __name__ == "__main__":
    main()
