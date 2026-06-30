import praw
import time
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os
import pickle
import re
import html
import threading
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
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


# --- Uptime Kuma heartbeat (Push monitor) ---
# Tracks the last time ANY Reddit listing fetch genuinely succeeded.
_LAST_FETCH_SUCCESS_TS = None


def record_fetch_success():
    """Mark that a Reddit fetch just succeeded (used by the Kuma heartbeat)."""
    global _LAST_FETCH_SUCCESS_TS
    _LAST_FETCH_SUCCESS_TS = time.time()


def send_kuma_heartbeat():
    """Report bot health to an Uptime Kuma Push monitor.

    Reports UP only if a Reddit fetch has succeeded within KUMA_FETCH_STALE_SECONDS;
    otherwise reports DOWN. This makes Kuma alert on a 403-storm / silent failure even
    though the container is still running (a Docker monitor can't see that). If the
    container dies entirely, no beats are sent and Kuma's own timeout marks it down.

    No-op unless KUMA_PUSH_URL is set, e.g.
        KUMA_PUSH_URL=http://192.168.50.124:3444/api/push/<token>
    """
    push_url = os.getenv('KUMA_PUSH_URL')
    if not push_url:
        return

    # Must exceed your longest monitor interval (monitors default to every 10 min).
    stale_after = int(os.getenv('KUMA_FETCH_STALE_SECONDS', '1500'))  # 25 min
    now = time.time()
    last = _LAST_FETCH_SUCCESS_TS

    if last is not None and (now - last) < stale_after:
        status, msg = 'up', f"ok (last good fetch {int(now - last)}s ago)"
    elif last is None:
        status, msg = 'down', 'no successful Reddit fetch since startup'
    else:
        status, msg = 'down', f"no successful Reddit fetch for {int(now - last)}s (Reddit blocking?)"

    try:
        requests.get(push_url, params={'status': status, 'msg': msg}, timeout=5)
    except requests.RequestException as e:
        logging.warning(f"Failed to send Uptime Kuma heartbeat: {e}")

    send_kuma_fallback_heartbeat()


def _oauth_expected():
    """True if the authenticated API is configured and in the source order, i.e. running
    on RSS/JSON instead is a degradation worth alerting on (not an intentional setup)."""
    creds = CREDENTIALS or {}
    has_app = bool(creds.get('reddit_client_id') and creds.get('reddit_client_secret'))
    return has_app and 'oauth' in get_source_order()


def send_kuma_fallback_heartbeat():
    """Report to a SECOND Uptime Kuma Push monitor that tracks whether the bot is using
    the authenticated API vs a fallback source. Reports DOWN when OAuth is expected but
    the bot is currently on RSS/JSON, so you're notified about the degradation while the
    primary monitor stays UP (data is still flowing). No-op unless KUMA_FALLBACK_PUSH_URL
    is set."""
    url = os.getenv('KUMA_FALLBACK_PUSH_URL')
    if not url:
        return

    if not _oauth_expected():
        status, msg = 'up', f"using {_active_source or 'rss/json'} (by configuration)"
    elif _active_source == 'oauth':
        status, msg = 'up', 'using authenticated API'
    else:
        status, msg = 'down', f"OAuth unavailable - on fallback source ({_active_source or 'none'})"

    try:
        requests.get(url, params={'status': status, 'msg': msg}, timeout=5)
    except requests.RequestException as e:
        logging.warning(f"Failed to send Uptime Kuma fallback heartbeat: {e}")


# ===================== Reddit data-source pathways =====================
# Posts/comments can be fetched through several pathways, tried in order:
#   'oauth' - authenticated PRAW API (full login OR app-only read-only). 100 req/min, never blocked.
#   'rss'   - www.reddit.com Atom feed. No credentials, but per-IP rate-limited (throttled below).
#   'json'  - anonymous old.reddit.com JSON. Mostly blocked now; kept as last resort.
# The order is configurable via search.json ("source_order") or REDDIT_SOURCE_ORDER env var.
VALID_SOURCES = ('oauth', 'rss', 'json')
DEFAULT_SOURCE_ORDER = ['oauth', 'rss', 'json']
ATOM_NS = {'a': 'http://www.w3.org/2005/Atom'}
RSS_USER_AGENT = os.getenv(
    'RSS_USER_AGENT',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.0 Safari/605.1.15'
)

_SOURCE_ORDER = None
_active_source = None
_source_cooldown_until = {}      # source name -> epoch time until which it is skipped
_source_state_lock = threading.Lock()
SOURCE_COOLDOWN_SECONDS = int(os.getenv('SOURCE_COOLDOWN_SECONDS', '300'))  # skip a blocked source for 5 min

# RSS is aggressively per-IP rate-limited, so serialize requests with a minimum gap.
_rss_throttle_lock = threading.Lock()
_rss_last_request = [0.0]
RSS_MIN_INTERVAL = float(os.getenv('RSS_MIN_INTERVAL_SECONDS', '4'))


def get_source_order():
    return list(_SOURCE_ORDER) if _SOURCE_ORDER else list(DEFAULT_SOURCE_ORDER)


def set_source_order(order):
    """Set the ordered list of data-source pathways, keeping only valid names."""
    global _SOURCE_ORDER
    cleaned = [s.strip() for s in (order or []) if s and s.strip() in VALID_SOURCES]
    _SOURCE_ORDER = cleaned or list(DEFAULT_SOURCE_ORDER)
    logging.info(f"Reddit source order: {' -> '.join(_SOURCE_ORDER)}")


def apply_source_order_from_config(config):
    """Resolve source order from search.json ('source_order'), then REDDIT_SOURCE_ORDER env, then default."""
    order = (config or {}).get('source_order')
    if not order:
        env = os.getenv('REDDIT_SOURCE_ORDER')
        order = env.split(',') if env else None
    set_source_order(order)


def _source_available(name):
    with _source_state_lock:
        return time.time() >= _source_cooldown_until.get(name, 0)


def _mark_source_down(name, seconds=None):
    cooldown = seconds or SOURCE_COOLDOWN_SECONDS
    with _source_state_lock:
        _source_cooldown_until[name] = time.time() + cooldown
    logging.warning(f"Pausing Reddit source '{name}' for {cooldown}s after failure")


def _set_active_source(source):
    """Record (and surface) the data source currently serving data, only when it changes."""
    global _active_source
    if source != _active_source:
        _active_source = source
        logging.info(f"📡 Active Reddit data source: {source}")
        save_bot_status(source != 'oauth', f"Active data source: {source}", active_source=source)


def _rss_throttle():
    """Block until at least RSS_MIN_INTERVAL seconds have passed since the last RSS request."""
    with _rss_throttle_lock:
        wait = RSS_MIN_INTERVAL - (time.time() - _rss_last_request[0])
        if wait > 0:
            time.sleep(wait)
        _rss_last_request[0] = time.time()


def notify_error(message):
    """Module-level error notification (used by the source dispatcher)."""
    urls = CREDENTIALS.get('notification_urls', []) if CREDENTIALS else []
    if not urls:
        return
    try:
        apobj = apprise.Apprise()
        for url in urls:
            apobj.add(url)
        apobj.notify(body=f"Error in Reddit Scraper: {message}", title="⚠️ Reddit Monitor Error")
    except Exception as e:
        logging.error(f"Error sending notification: {e}")


def _fetch_posts_oauth(reddit, subreddit, limit):
    """Fetch posts via the authenticated PRAW API. Raises on auth/API errors."""
    sub = reddit.subreddit(subreddit)
    posts = []
    for s in sub.new(limit=limit):
        posts.append({
            'id': s.id,
            'title': s.title,
            'url': s.url,
            'score': s.score,
            'permalink': s.permalink,
            'domain': getattr(s, 'domain', '') or '',
            'link_flair_text': getattr(s, 'link_flair_text', '') or '',
            'author': s.author.name if s.author else '',
        })
    return posts


def fetch_posts_rss(subreddit, limit=10):
    """Fetch posts via the www.reddit.com Atom feed (no auth). Raises on 403/429 so the
    dispatcher can fall through and back off. Note: RSS exposes no score and no external
    domain, so those fields degrade to 0 / '' (score/domain filters won't match)."""
    _rss_throttle()
    url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit={limit}"
    response = requests.get(url, headers={'User-Agent': RSS_USER_AGENT}, timeout=15)
    if response.status_code in (403, 429):
        raise RuntimeError(f"RSS blocked ({response.status_code})")
    response.raise_for_status()

    root = ET.fromstring(response.content)
    posts = []
    for entry in root.findall('a:entry', ATOM_NS)[:limit]:
        def text(tag):
            el = entry.find(f'a:{tag}', ATOM_NS)
            return el.text if (el is not None and el.text) else ''

        raw_id = text('id')                       # e.g. "t3_abc123"
        post_id = raw_id.split('_')[-1] if raw_id else ''
        link_el = entry.find('a:link', ATOM_NS)
        href = link_el.get('href') if link_el is not None else ''
        permalink = urlparse(href).path if href else ''
        author_el = entry.find('a:author/a:name', ATOM_NS)
        author = (author_el.text or '') if author_el is not None else ''
        if author.startswith('/u/'):
            author = author[3:]
        cat_el = entry.find('a:category', ATOM_NS)
        flair = cat_el.get('term') if cat_el is not None else ''

        posts.append({
            'id': post_id,
            'title': text('title'),
            'url': href,
            'score': 0,            # not exposed via RSS
            'permalink': permalink,
            'domain': '',          # not exposed via RSS
            'link_flair_text': flair or '',
            'author': author,
        })
    return posts


def fetch_thread_comments_rss(subreddit, thread_id, limit=500):
    """Fetch a thread's comments via the www.reddit.com Atom feed (no auth)."""
    _rss_throttle()
    url = f"https://www.reddit.com/r/{subreddit}/comments/{thread_id}/.rss?sort=new&limit={limit}"
    response = requests.get(url, headers={'User-Agent': RSS_USER_AGENT}, timeout=15)
    if response.status_code in (403, 429):
        raise RuntimeError(f"RSS blocked ({response.status_code})")
    response.raise_for_status()

    root = ET.fromstring(response.content)
    comments = []
    for entry in root.findall('a:entry', ATOM_NS):
        id_el = entry.find('a:id', ATOM_NS)
        raw_id = (id_el.text or '') if id_el is not None else ''
        if not raw_id.startswith('t1_'):          # keep comments only, not the post itself
            continue
        content_el = entry.find('a:content', ATOM_NS)
        body_html = (content_el.text or '') if content_el is not None else ''
        body = re.sub(r'<[^>]+>', '', html.unescape(body_html)).strip()
        author_el = entry.find('a:author/a:name', ATOM_NS)
        author = (author_el.text or '') if author_el is not None else ''
        if author.startswith('/u/'):
            author = author[3:]
        link_el = entry.find('a:link', ATOM_NS)
        permalink = urlparse(link_el.get('href')).path if link_el is not None else ''
        comments.append({
            'id': raw_id.split('_')[-1],
            'body': body,
            'author': author,
            'score': 0,
            'permalink': permalink,
        })
    return comments


def fetch_posts(subreddit, limit, reddit):
    """Try each configured source in order until one returns data.

    Returns (posts, source_name), or (None, None) if every source failed.
    A source that errors or returns nothing is put on a short cooldown so we
    don't keep hammering a blocked endpoint every cycle.
    """
    for source in get_source_order():
        if not _source_available(source):
            continue
        try:
            if source == 'oauth':
                if reddit is None:
                    continue
                posts = _fetch_posts_oauth(reddit, subreddit, limit)
            elif source == 'rss':
                posts = fetch_posts_rss(subreddit, limit)
            elif source == 'json':
                posts = fetch_posts_json(subreddit, limit)
            else:
                continue
        except Exception as e:
            error_str = str(e)
            if source == 'oauth' and ('401' in error_str or 'unauthorized' in error_str.lower()):
                if not RedditMonitor._auth_error_notified:
                    notify_error("Reddit API authentication failed (401). Falling back to alternative sources (RSS/JSON).")
                    RedditMonitor._auth_error_notified = True
            logging.warning(f"Reddit source '{source}' failed for r/{subreddit}: {e}")
            _mark_source_down(source)
            continue

        if posts is None:
            logging.warning(f"Reddit source '{source}' returned nothing for r/{subreddit}")
            _mark_source_down(source)
            continue

        if source == 'oauth':
            RedditMonitor._auth_error_notified = False
        record_fetch_success()
        _set_active_source(source)
        return posts, source

    logging.error(f"All Reddit sources failed for r/{subreddit}")
    return None, None
# =======================================================================


# Persistent warning surfaced to the UI when a credential contains characters that
# can't be used for auth (e.g. a pasted Cyrillic lookalike) - see check_credential_encoding.
CREDENTIAL_WARNING = None


def save_bot_status(using_fallback, message=None, active_source=None):
    """Save bot status to file for API/frontend to read."""
    try:
        status = {
            'using_json_fallback': using_fallback,
            'active_source': active_source,
            'message': message,
            'credentials_warning': CREDENTIAL_WARNING,
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


def check_credential_encoding(creds):
    """Warn loudly if any Reddit credential contains non-ASCII characters.

    Reddit credentials are always ASCII; a stray non-ASCII char (e.g. a Cyrillic
    lookalike pasted in place of a Latin letter) is silently stripped by
    sanitize_credential, producing a *wrong* value that fails auth with a confusing
    401. Detect it up front and surface it to the UI instead of failing silently.
    """
    global CREDENTIAL_WARNING
    offenders = []
    for key in ('reddit_client_id', 'reddit_client_secret', 'reddit_user_agent',
                'reddit_username', 'reddit_password'):
        value = creds.get(key) or ''
        bad = [(i, hex(ord(c))) for i, c in enumerate(value) if ord(c) > 127]
        if bad:
            offenders.append(f"{key} (positions {[i for i, _ in bad]})")

    if offenders:
        CREDENTIAL_WARNING = (
            "Non-ASCII characters detected in: " + "; ".join(offenders) +
            ". This usually means a credential was pasted with a lookalike character "
            "(e.g. Cyrillic 'І' for Latin 'I') and will cause a 401 / fall back to RSS. "
            "Re-copy the affected credential from https://www.reddit.com/prefs/apps."
        )
        logging.error("🚨 " + CREDENTIAL_WARNING)
    else:
        CREDENTIAL_WARNING = None
    return offenders


def detect_auth_capability():
    """Load credentials and report which Reddit auth pathway is available.

    Credentials are now optional: the bot can run on RSS/JSON alone. Full OAuth
    (login) is used when username+password are present; app-only read-only OAuth
    when only client id+secret are present; otherwise no API auth.
    """
    global CREDENTIALS
    CREDENTIALS = load_credentials()
    check_credential_encoding(CREDENTIALS)

    has_app = bool(CREDENTIALS.get('reddit_client_id') and CREDENTIALS.get('reddit_client_secret'))
    has_login = has_app and bool(CREDENTIALS.get('reddit_username') and CREDENTIALS.get('reddit_password'))

    if has_login:
        logging.info("🔐 Reddit auth: full OAuth (logged-in).")
    elif has_app:
        logging.info("🔓 Reddit auth: read-only OAuth (app-only, no login).")
    else:
        logging.info("🌐 No Reddit API credentials - using RSS/JSON pathways only.")
        logging.info("   Add an app (client id/secret) via the web UI for higher, unblocked limits.")

    if CREDENTIALS.get('notification_urls'):
        logging.info(f"🔔 Configured {len(CREDENTIALS['notification_urls'])} notification service(s)")
    else:
        logging.warning("⚠️ No notification services configured - notifications disabled")


detect_auth_capability()


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

        record_fetch_success()
        return posts
    except requests.exceptions.RequestException as e:
        logging.error(f"JSON endpoint error for r/{subreddit}: {e}")
        return None


def fetch_thread_comments_json(subreddit, thread_id, limit=500):
    """Fetch top-level comments from a Reddit thread via JSON endpoint, sorted by new."""
    url = f"https://old.reddit.com/r/{subreddit}/comments/{thread_id}.json?limit={limit}&sort=new"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list) or len(data) < 2:
            logging.error(f"Unexpected response structure for thread {thread_id}")
            return None

        comments = []
        for child in data[1].get('data', {}).get('children', []):
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
        logging.error(f"Error fetching comments for thread {thread_id}: {e}")
        return None


class RedditMonitor:
    processed_submissions_file = PROCESSED_SUBMISSIONS_FILE_PATH
    max_file_size = 5 * 1024 * 1024  # 5 MB
    _auth_error_notified = False  # Track if we've sent a 401 notification
    _using_json_fallback = False  # Track if we're using JSON fallback due to API errors
    _thread_cache = {}  # subreddit+pattern -> {thread_id, cached_at}
    THREAD_CACHE_TTL = 3600  # refresh cached thread ID every hour

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
        if self.monitor_type == 'thread_comments':
            self.search_thread_comments()
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

    def find_current_thread(self):
        """Find the thread ID of the current weekly megathread, with 1-hour caching."""
        cache_key = f"{self.subreddit}-{self.thread_title_pattern}"
        cached = RedditMonitor._thread_cache.get(cache_key)
        if cached and (time.time() - cached['cached_at']) < RedditMonitor.THREAD_CACHE_TTL:
            return cached['thread_id']

        thread_id = None
        pattern = self.thread_title_pattern.lower()

        # Stickied posts are the most reliable signal, but only PRAW exposes them.
        if self.reddit and _source_available('oauth'):
            try:
                sub = self.reddit.subreddit(self.subreddit)
                for slot in [1, 2]:
                    try:
                        sticky = sub.sticky(number=slot)
                        if pattern in sticky.title.lower():
                            thread_id = sticky.id
                            break
                    except Exception:
                        pass
            except Exception as e:
                logging.warning(f"PRAW error finding sticky BST thread: {e}")

        # Otherwise scan recent posts via the source chain (oauth -> rss -> json).
        if not thread_id:
            posts, _ = fetch_posts(self.subreddit, 25, self.reddit)
            for post in (posts or []):
                if pattern in (post['title'] or '').lower():
                    if post.get('id'):
                        thread_id = post['id']
                    else:
                        parts = post['permalink'].strip('/').split('/')
                        if 'comments' in parts:
                            thread_id = parts[parts.index('comments') + 1]
                    break

        if thread_id:
            RedditMonitor._thread_cache[cache_key] = {'thread_id': thread_id, 'cached_at': time.time()}
            logging.info(f"Thread located: {thread_id}")
        else:
            logging.warning(f"Could not find thread matching '{self.thread_title_pattern}' in r/{self.subreddit}")

        return thread_id

    def search_thread_comments(self):
        """Scan a pinned/recurring thread's comments for keyword matches."""
        thread_id = self.find_current_thread()
        if not thread_id:
            return

        logging.info(f"Scanning thread {thread_id} comments in r/{self.subreddit}...")
        comments = self._fetch_comments(thread_id)
        if comments is None:
            return

        for comment in comments:
            self._process_comment(
                comment_id=comment['id'],
                body=comment['body'],
                author=comment['author'],
                permalink=comment['permalink'],
            )
        logging.info(f"Finished scanning thread comments in r/{self.subreddit}.")

    def _fetch_comments(self, thread_id):
        """Fetch a thread's comments through the configured source chain (oauth -> rss -> json)."""
        for source in get_source_order():
            if not _source_available(source):
                continue
            try:
                if source == 'oauth':
                    if self.reddit is None:
                        continue
                    submission = self.reddit.submission(id=thread_id)
                    submission.comment_sort = 'new'
                    submission.comments.replace_more(limit=0)
                    comments = [
                        {
                            'id': c.id,
                            'body': c.body,
                            'author': c.author.name if c.author else '[deleted]',
                            'permalink': c.permalink,
                        }
                        for c in submission.comments
                    ]
                elif source == 'rss':
                    comments = fetch_thread_comments_rss(self.subreddit, thread_id)
                elif source == 'json':
                    comments = fetch_thread_comments_json(self.subreddit, thread_id)
                else:
                    continue
            except Exception as e:
                logging.warning(f"Comment source '{source}' failed for thread {thread_id}: {e}")
                _mark_source_down(source)
                continue

            if comments is None:
                _mark_source_down(source)
                continue

            record_fetch_success()
            return comments

        logging.error(f"All sources failed fetching comments for thread {thread_id}")
        return None

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
        author_lower = author.lower()
        meets_author_includes = not self.author_includes or author_lower in [a.lower() for a in self.author_includes]
        meets_author_excludes = author_lower not in [a.lower() for a in self.author_excludes]

        if has_keywords and not has_excluded and meets_author_includes and meets_author_excludes:
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
        """Search a subreddit for keywords, fetching posts through the configured source chain."""
        logging.info(f"Searching '{self.subreddit}' subreddit for keywords...")
        posts, source = fetch_posts(self.subreddit, 10, self.reddit)

        if posts is None:
            logging.error(f"Failed to fetch posts for '{self.subreddit}' from all sources")
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

        logging.info(f"Finished searching '{self.subreddit}' subreddit (source: {source}).")
    
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
    """Build a PRAW client for the 'oauth' pathway.

    Returns a logged-in client if username+password are set, a read-only
    (app-only) client if only client id+secret are set, or None if no app
    credentials exist (the bot then relies on the RSS/JSON pathways).
    """
    # Sanitize credentials to remove any accidental Unicode characters
    client_id = sanitize_credential(CREDENTIALS.get('reddit_client_id'), 'client_id')
    client_secret = sanitize_credential(CREDENTIALS.get('reddit_client_secret'), 'client_secret')
    user_agent = sanitize_credential(CREDENTIALS.get('reddit_user_agent'), 'user_agent') or 'reddit-scraper/1.0'
    username = sanitize_credential(CREDENTIALS.get('reddit_username'), 'username')
    password = sanitize_credential(CREDENTIALS.get('reddit_password'), 'password')

    if not (client_id and client_secret):
        logging.info("No Reddit app credentials - skipping OAuth pathway.")
        return None

    if username and password:
        logging.info("Authenticating Reddit (full OAuth)...")
        return praw.Reddit(client_id=client_id,
                           client_secret=client_secret,
                           user_agent=user_agent,
                           username=username,
                           password=password)

    logging.info("Authenticating Reddit (read-only, app-only)...")
    reddit = praw.Reddit(client_id=client_id,
                         client_secret=client_secret,
                         user_agent=user_agent)
    reddit.read_only = True
    return reddit

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
    apply_source_order_from_config(config)
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
                apply_source_order_from_config(config)
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

        # Report health to Uptime Kuma (up only if a Reddit fetch succeeded recently)
        send_kuma_heartbeat()

        # Base cycle interval - check every 2 minutes (monitors have their own schedules)
        logging.info(f"Cycle {loopTime} complete. Sleeping for 2 minutes before next check...")
        loopTime += 1
        time.sleep(120)  # Check every 2 minutes for lower CPU usage

if __name__ == "__main__":
    main()
