import praw
import time
import requests
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
BOT_STATUS_FILE_PATH = os.path.join(DATA_DIR, 'bot_status.json')
# -------------------------------------


def save_bot_status(using_fallback, message=None):
    """Save bot status to file for API/frontend to read."""
    try:
        status = {
            'using_json_fallback': using_fallback,
            'message': message,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        with open(BOT_STATUS_FILE_PATH, 'w') as f:
            json.dump(status, f)
    except Exception as e:
        logging.error(f"Failed to save bot status: {e}")

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


def fetch_posts_json(subreddit, limit=10):
    """Fetch posts from Reddit using JSON endpoint (no API auth required).
    
    Uses old.reddit.com which is more reliable for JSON endpoints.
    Returns a list of post dicts with keys: id, title, url, score, permalink, domain, link_flair_text, author
    """
    url = f"https://old.reddit.com/r/{subreddit}/new.json?limit={limit}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        posts = []
        
        for child in data.get('data', {}).get('children', []):
            post_data = child.get('data', {})
            posts.append({
                'id': post_data.get('id', ''),
                'title': post_data.get('title', ''),
                'url': post_data.get('url', ''),
                'score': post_data.get('score', 0),
                'permalink': post_data.get('permalink', ''),
                'domain': post_data.get('domain', ''),
                'link_flair_text': post_data.get('link_flair_text', ''),
                'author': post_data.get('author', ''),
            })
        
        return posts
    except requests.exceptions.RequestException as e:
        logging.error(f"JSON endpoint error for r/{subreddit}: {e}")
        return None


def fetch_bst_thread_comments_json(subreddit, thread_id, limit=100):
    """Fetch top-level comments from a Reddit thread via JSON endpoint, sorted by new."""
    url = f"https://old.reddit.com/r/{subreddit}/comments/{thread_id}.json?limit={limit}&sort=new"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        comments = []
        for child in data[1]['data']['children']:
            if child.get('kind') != 't1':
                continue
            d = child['data']
            comments.append({
                'id': d.get('id', ''),
                'body': d.get('body', ''),
                'author': d.get('author', ''),
                'score': d.get('score', 0),
                'permalink': d.get('permalink', ''),
            })
        return comments
    except Exception as e:
        logging.error(f"Error fetching BST comments for thread {thread_id}: {e}")
        return None


class RedditMonitor:
    processed_submissions_file = PROCESSED_SUBMISSIONS_FILE_PATH
    max_file_size = 5 * 1024 * 1024  # 5 MB
    _auth_error_notified = False  # Track if we've sent a 401 notification
    _using_json_fallback = False  # Track if we're using JSON fallback due to API errors
    _bst_thread_cache = {}  # subreddit+pattern -> {thread_id, cached_at}
    BST_THREAD_CACHE_TTL = 3600  # refresh cached thread ID every hour

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
        self.monitor_type = kwargs.get('monitor_type', 'posts')
        self.thread_title_pattern = kwargs.get('thread_title_pattern', 'Buy/Sell/Trade')
        self.keyword_logic = kwargs.get('keyword_logic', 'any')
        self.load_processed_submissions()

    def run(self):
        """Dispatch to the correct monitor method based on monitor_type."""
        if self.monitor_type == 'bst_comments':
            self.search_bst_comments()
        else:
            self.search_reddit_for_keywords()

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

    def find_current_bst_thread(self):
        """Find the thread ID of the current weekly BST megathread, with 1-hour caching."""
        cache_key = f"{self.subreddit}-{self.thread_title_pattern}"
        cached = RedditMonitor._bst_thread_cache.get(cache_key)
        if cached and (time.time() - cached['cached_at']) < RedditMonitor.BST_THREAD_CACHE_TTL:
            return cached['thread_id']

        thread_id = None

        if self.reddit and not RedditMonitor._using_json_fallback:
            try:
                sub = self.reddit.subreddit(self.subreddit)
                # Check stickied posts first (most reliable for weekly threads)
                for slot in [1, 2]:
                    try:
                        sticky = sub.sticky(number=slot)
                        if self.thread_title_pattern.lower() in sticky.title.lower():
                            thread_id = sticky.id
                            break
                    except Exception:
                        pass
                # Fall back to scanning recent posts
                if not thread_id:
                    for post in sub.new(limit=25):
                        if self.thread_title_pattern.lower() in post.title.lower():
                            thread_id = post.id
                            break
            except Exception as e:
                logging.warning(f"PRAW error finding BST thread: {e}")

        # JSON fallback
        if not thread_id:
            posts = fetch_posts_json(self.subreddit, limit=25)
            if posts:
                for post in posts:
                    if self.thread_title_pattern.lower() in post['title'].lower():
                        parts = post['permalink'].strip('/').split('/')
                        if 'comments' in parts:
                            thread_id = parts[parts.index('comments') + 1]
                            break

        if thread_id:
            RedditMonitor._bst_thread_cache[cache_key] = {'thread_id': thread_id, 'cached_at': time.time()}
            logging.info(f"BST thread located: {thread_id}")
        else:
            logging.warning(f"Could not find BST thread matching '{self.thread_title_pattern}' in r/{self.subreddit}")

        return thread_id

    def search_bst_comments(self):
        """Scan the current weekly BST megathread comments for size/keyword matches."""
        thread_id = self.find_current_bst_thread()
        if not thread_id:
            return

        logging.info(f"Scanning BST thread {thread_id} comments in r/{self.subreddit}...")
        comments = fetch_bst_thread_comments_json(self.subreddit, thread_id)
        if comments is None:
            return

        for comment in comments:
            self._process_comment(
                comment_id=comment['id'],
                body=comment['body'],
                author=comment['author'],
                permalink=comment['permalink'],
            )
        logging.info(f"Finished scanning BST thread comments in r/{self.subreddit}.")

    def _process_comment(self, comment_id, body, author, permalink):
        """Check a BST comment against keyword filters and notify on match."""
        submission_id = f"{self.subreddit}-comment-{comment_id}"
        if submission_id in self.processed_submissions:
            return False

        body_lower = body.lower()

        if self.keyword_logic == 'any':
            has_keywords = any(kw.lower() in body_lower for kw in self.keywords)
        else:
            has_keywords = all(kw.lower() in body_lower for kw in self.keywords)

        has_excluded = any(kw.lower() in body_lower for kw in self.exclude_keywords)
        meets_author_excludes = author.lower() not in [a.lower() for a in self.author_excludes]

        if has_keywords and not has_excluded and meets_author_excludes:
            excerpt = body[:300] + '...' if len(body) > 300 else body
            message = (
                f"BST listing match in r/{self.subreddit}!\n"
                f"u/{author}:\n{excerpt}\n"
                f"Link: https://www.reddit.com{permalink}"
            )
            self.send_push_notification(message, title=f"FMF BST Match")
            logging.info(f"BST match: u/{author} | {body[:80]}...")
            self.processed_submissions.add(submission_id)
            self.save_processed_submissions()
            return True

        return False

    def search_reddit_for_keywords(self):
        """Search subreddit for keywords. Uses PRAW API first, falls back to JSON endpoint on auth failure."""
        notifications_count = 0
        
        # Decide whether to use API or JSON fallback
        use_json = RedditMonitor._using_json_fallback or self.reddit is None
        
        if not use_json:
            # Try PRAW API first
            try:
                logging.info(f"Searching '{self.subreddit}' subreddit for keywords (API mode)...")
                subreddit_obj = self.reddit.subreddit(self.subreddit)
                
                for submission in subreddit_obj.new(limit=10):
                    self._process_post(
                        post_id=submission.id,
                        title=submission.title,
                        url=submission.url,
                        score=submission.score,
                        permalink=submission.permalink,
                        domain=getattr(submission, 'domain', ''),
                        flair=getattr(submission, 'link_flair_text', '') or '',
                        author=submission.author.name if submission.author else ''
                    )
                
                logging.info(f"Finished searching '{self.subreddit}' subreddit for keywords.")
                # Reset flags on success
                RedditMonitor._auth_error_notified = False
                if RedditMonitor._using_json_fallback:
                    save_bot_status(False, "API authentication restored")
                RedditMonitor._using_json_fallback = False
                return
                
            except Exception as e:
                error_str = str(e)
                # Check for 401 unauthorized - switch to JSON fallback
                if '401' in error_str or 'unauthorized' in error_str.lower():
                    logging.warning(f"⚠️ Reddit API auth failed for '{self.subreddit}'. Switching to JSON fallback mode.")
                    if not RedditMonitor._auth_error_notified:
                        self.send_error_notification("Reddit API authentication failed (401). Switching to API-free JSON mode.")
                        RedditMonitor._auth_error_notified = True
                        save_bot_status(True, "Reddit API authentication failed. Using JSON fallback mode (no API credentials required).")
                    RedditMonitor._using_json_fallback = True
                    use_json = True  # Fall through to JSON mode
                else:
                    error_message = f"Error during Reddit search for '{self.subreddit}': {e}"
                    logging.error(error_message)
                    self.send_error_notification(error_message)
                    return
        
        # JSON fallback mode
        if use_json:
            logging.info(f"Searching '{self.subreddit}' subreddit for keywords (JSON mode - no auth)...")
            posts = fetch_posts_json(self.subreddit, limit=10)
            
            if posts is None:
                logging.error(f"Failed to fetch posts via JSON for '{self.subreddit}'")
                return
            
            for post in posts:
                self._process_post(
                    post_id=post['id'],
                    title=post['title'],
                    url=post['url'],
                    score=post['score'],
                    permalink=post['permalink'],
                    domain=post['domain'],
                    flair=post['link_flair_text'] or '',
                    author=post['author']
                )
            
            logging.info(f"Finished searching '{self.subreddit}' subreddit (JSON mode).")
    
    def _process_post(self, post_id, title, url, score, permalink, domain, flair, author):
        """Process a single post and send notification if it matches filters."""
        submission_id = f"{self.subreddit}-{post_id}"
        if submission_id in self.processed_submissions:
            logging.debug(f"Skipping duplicate post: {title}")
            return False
        
        message = f"Match found in '{self.subreddit}' subreddit:\n" \
                  f"Title: {title}\n" \
                  f"URL: {url}\n" \
                  f"Upvotes: {score}\n" \
                  f"Permalink: https://www.reddit.com{permalink}\n"
        
        # Check filters
        title_lower = title.lower()
        has_all_keywords = all(keyword in title_lower for keyword in self.keywords)
        has_excluded = any(keyword in title_lower for keyword in self.exclude_keywords)
        meets_upvotes = self.min_upvotes is None or score >= self.min_upvotes
        
        # Domain filters
        submission_domain = domain.lower()
        meets_domain_contains = not self.domain_contains or any(d in submission_domain for d in self.domain_contains)
        meets_domain_excludes = not any(d in submission_domain for d in self.domain_excludes)
        
        # Flair filter
        submission_flair = flair.lower()
        meets_flair = not self.flair_contains or any(f.lower() in submission_flair for f in self.flair_contains)
        
        # Author filters
        author_name = author.lower()
        meets_author_includes = not self.author_includes or author_name in [a.lower() for a in self.author_includes]
        meets_author_excludes = author_name not in [a.lower() for a in self.author_excludes]
        
        if (has_all_keywords and not has_excluded and meets_upvotes and 
            meets_domain_contains and meets_domain_excludes and 
            meets_flair and meets_author_includes and meets_author_excludes):
            logging.info(message)
            self.send_push_notification(message)
            logging.info('-' * 40)
            
            self.processed_submissions.add(submission_id)
            self.save_processed_submissions()
            return True
        
        return False


def sanitize_credential(value, name):
    """Remove non-ASCII characters from credentials that cause latin-1 encoding errors."""
    if not value:
        return value
    # Check for and warn about non-ASCII characters
    original = value
    sanitized = value.encode('ascii', 'ignore').decode('ascii')
    if original != sanitized:
        logging.warning(f"⚠️ Removed non-ASCII characters from {name}: found Unicode at positions {[i for i, c in enumerate(original) if ord(c) > 127]}")
    return sanitized


def authenticate_reddit():
    logging.info("Authenticating Reddit...")
    # Sanitize credentials to remove any accidental Unicode characters
    client_id = sanitize_credential(CREDENTIALS['reddit_client_id'], 'client_id')
    client_secret = sanitize_credential(CREDENTIALS['reddit_client_secret'], 'client_secret')
    user_agent = sanitize_credential(CREDENTIALS['reddit_user_agent'], 'user_agent')
    username = sanitize_credential(CREDENTIALS['reddit_username'], 'username')
    password = sanitize_credential(CREDENTIALS['reddit_password'], 'password')
    
    return praw.Reddit(client_id=client_id,
                       client_secret=client_secret,
                       user_agent=user_agent,
                       username=username,
                       password=password)

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

        # Base cycle interval - check every 2 minutes (monitors have their own schedules)
        logging.info(f"Cycle {loopTime} complete. Sleeping for 2 minutes before next check...")
        loopTime += 1
        time.sleep(120)  # Check every 2 minutes for lower CPU usage

if __name__ == "__main__":
    main()
