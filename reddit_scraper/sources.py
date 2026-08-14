"""Reddit data-source pathways and the fetch dispatcher.

Posts/comments are fetched through several pathways, tried in the configured order
(see config.get_source_order). A source that errors or returns nothing is put on a
short cooldown so we don't keep hammering a blocked endpoint.
"""
import os
import re
import html
import time
import logging
import threading
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests

from . import config, status, notifications

ATOM_NS = {'a': 'http://www.w3.org/2005/Atom'}
RSS_USER_AGENT = os.getenv(
    'RSS_USER_AGENT',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.0 Safari/605.1.15'
)
JSON_USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

# --- Tuning knobs (config; read from env once, overridable in tests) ---
SOURCE_COOLDOWN_SECONDS = int(os.getenv('SOURCE_COOLDOWN_SECONDS', '300'))      # base cooldown
SOURCE_COOLDOWN_MAX = int(os.getenv('SOURCE_COOLDOWN_MAX_SECONDS', '3600'))     # cap on backoff
RSS_MIN_INTERVAL = float(os.getenv('RSS_MIN_INTERVAL_SECONDS', '4'))            # min gap between RSS reqs

# Optional proxying so the anonymous RSS/JSON endpoints aren't all hit from one IP
# (the IP Reddit ends up flagging). REDDIT_PROXIES is a comma-separated pool rotated
# per request; REDDIT_PROXY is a single proxy. Unset -> requests go out directly, so
# this is a no-op until a proxy URL is provided. Supports http(s):// and socks5://
# (socks needs `requests[socks]`). When any proxy is configured we NEVER fall back to a
# direct request, so a configured IP-hiding setup can't silently leak the real IP.
def _parse_proxies():
    pool = os.getenv('REDDIT_PROXIES')
    if pool:
        return [p.strip() for p in pool.split(',') if p.strip()]
    single = (os.getenv('REDDIT_PROXY') or '').strip()
    return [single] if single else []

_PROXIES = _parse_proxies()
PROXY_COOLDOWN_SECONDS = int(os.getenv('PROXY_COOLDOWN_SECONDS', '120'))

# Sylvia (api.sylvia-api.com) is a third-party Reddit gateway that returns native-Reddit-
# shaped JSON from Sylvia's own IP (so it doubles as IP hiding) and, unlike RSS, carries
# full post data (score/domain/flair). It's authenticated with an API key and is billed
# per successful request, so it's OPT-IN: the 'sylvia' source is skipped entirely unless
# SYLVIA_API_KEY is set, and it's not in the default source order.
SYLVIA_API_KEY = os.getenv('SYLVIA_API_KEY')
SYLVIA_BASE_URL = os.getenv('SYLVIA_BASE_URL', 'https://api.sylvia-api.com/v1/reddit').rstrip('/')
SYLVIA_TIMEOUT = float(os.getenv('SYLVIA_TIMEOUT_SECONDS', '15'))

# Short-lived response cache so concurrent monitors covering the same subreddit/thread
# share a single network request instead of each issuing its own (which both wastes
# requests and trips rate limits). TTL only needs to span one scheduling burst.
FETCH_CACHE_TTL = float(os.getenv('FETCH_CACHE_TTL_SECONDS', '90'))


class _SourceState:
    """Mutable runtime state behind the fetch dispatcher: the fetch-success heartbeat,
    the active source, source cooldowns + exponential backoff, the coalescing cache,
    proxy rotation, the RSS throttle clock, and one-time-notification flags.

    A single module-level instance (`_state`) owns it; the module-level functions below
    are a thin facade over it, so callers and tests don't reach into individual fields.
    Tuning knobs (SOURCE_COOLDOWN_*, RSS_MIN_INTERVAL, FETCH_CACHE_TTL,
    PROXY_COOLDOWN_SECONDS, _PROXIES, SYLVIA_API_KEY) stay module-level config, read here
    by name so tests can still override them.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset all runtime state to fresh (called at import and between tests)."""
        self.last_fetch_success_ts = None   # last time ANY fetch succeeded (Kuma heartbeat)
        self.active_source = None           # data source currently serving data
        self.auth_error_notified = False    # OAuth-401 notified? (reset on next oauth success)

        self.source_cooldown_until = {}     # source -> epoch until which it is skipped
        self.source_failures = {}           # source -> consecutive failure count (for backoff)
        self._lock = threading.Lock()

        self.rss_last_request = 0.0         # RSS is per-IP rate-limited; serialize with a gap
        self._rss_lock = threading.Lock()

        self.proxy_index = 0                # round-robin cursor over _PROXIES
        self.proxy_cooldown_until = {}      # proxy -> epoch until which it is skipped
        self._proxy_lock = threading.Lock()

        self.fetch_cache = {}               # coalesce key -> (timestamp, value)
        self.key_locks = {}                 # coalesce key -> Lock (callers share, not stampede)
        self._cache_lock = threading.Lock()

        self.sylvia_key_warned = False      # so the "no Sylvia key" skip logs once

    # --- fetch-success heartbeat / active source ---
    def record_fetch_success(self):
        self.last_fetch_success_ts = time.time()

    def set_active_source(self, source):
        """Record (and surface) the active source, only when it changes."""
        if source != self.active_source:
            self.active_source = source
            logging.info(f"📡 Active Reddit data source: {source}")
            status.save_bot_status(source != 'oauth', f"Active data source: {source}", active_source=source)

    # --- one-time OAuth-failure notification guard ---
    def claim_auth_error_notification(self):
        """Atomically claim the right to send the one-time OAuth-failure notification.
        Monitors run concurrently, so without this guard every thread hitting the same
        401 fires its own. Returns True for exactly one caller until reset on oauth success."""
        with self._lock:
            if self.auth_error_notified:
                return False
            self.auth_error_notified = True
            return True

    def reset_auth_error_notification(self):
        with self._lock:
            self.auth_error_notified = False

    # --- source cooldown + exponential backoff ---
    def source_available(self, name):
        if name == 'sylvia' and not SYLVIA_API_KEY:
            with self._lock:
                if not self.sylvia_key_warned:
                    logging.warning("Source 'sylvia' is in the order but SYLVIA_API_KEY is unset; skipping it.")
                    self.sylvia_key_warned = True
            return False
        with self._lock:
            return time.time() >= self.source_cooldown_until.get(name, 0)

    def mark_source_down(self, name, seconds=None):
        """Cool down a failed source. With no explicit duration, back off exponentially on
        consecutive failures (base, 2x, 4x, ... capped) so a dead source gets a real rest."""
        with self._lock:
            if seconds is None:
                n = self.source_failures.get(name, 0) + 1
                self.source_failures[name] = n
                cooldown = min(SOURCE_COOLDOWN_SECONDS * (2 ** (n - 1)), SOURCE_COOLDOWN_MAX)
            else:
                cooldown = seconds
            self.source_cooldown_until[name] = time.time() + cooldown
        logging.warning(f"Pausing Reddit source '{name}' for {int(cooldown)}s after failure")

    def note_source_success(self, name):
        """Reset a source's backoff after it succeeds."""
        with self._lock:
            self.source_failures[name] = 0

    # --- coalescing cache ---
    def coalesce(self, key, producer):
        """Return a cached fresh value for key, or produce + cache it. Concurrent callers
        for the same key wait on a per-key lock and share the single result."""
        now = time.time()
        with self._cache_lock:
            entry = self.fetch_cache.get(key)
            if entry and now - entry[0] < FETCH_CACHE_TTL:
                return entry[1]
            key_lock = self.key_locks.setdefault(key, threading.Lock())

        with key_lock:
            # Re-check inside the per-key lock: another thread may have just produced it.
            now = time.time()
            with self._cache_lock:
                entry = self.fetch_cache.get(key)
                if entry and now - entry[0] < FETCH_CACHE_TTL:
                    return entry[1]
            value = producer()
            with self._cache_lock:
                self.fetch_cache[key] = (time.time(), value)
            return value

    # --- RSS throttle ---
    def rss_throttle(self):
        """Block until at least RSS_MIN_INTERVAL seconds have passed since the last RSS request."""
        with self._rss_lock:
            wait = RSS_MIN_INTERVAL - (time.time() - self.rss_last_request)
            if wait > 0:
                time.sleep(wait)
            self.rss_last_request = time.time()

    # --- proxy rotation ---
    def next_proxy(self):
        """Round-robin the next proxy that isn't cooling down, or None if all are (or none set)."""
        if not _PROXIES:
            return None
        now = time.time()
        with self._proxy_lock:
            n = len(_PROXIES)
            for _ in range(n):
                i = self.proxy_index % n
                self.proxy_index = (i + 1) % n
                proxy = _PROXIES[i]
                if self.proxy_cooldown_until.get(proxy, 0) <= now:
                    return proxy
            return None

    def mark_proxy_down(self, proxy):
        """Skip a proxy that failed to connect for a short while, then let it back in."""
        with self._proxy_lock:
            self.proxy_cooldown_until[proxy] = time.time() + PROXY_COOLDOWN_SECONDS


_state = _SourceState()


# --- thin module-level facade over _state (keeps existing call sites and tests stable) ---
def record_fetch_success():
    """Mark that a Reddit fetch just succeeded (used by the Kuma heartbeat)."""
    _state.record_fetch_success()


def get_last_fetch_success_ts():
    """Epoch of the last successful fetch, or None (used by the health heartbeat)."""
    return _state.last_fetch_success_ts


def get_active_source():
    """The data source currently serving data, or None."""
    return _state.active_source


def _claim_auth_error_notification():
    return _state.claim_auth_error_notification()


def _reset_auth_error_notification():
    _state.reset_auth_error_notification()


def _source_available(name):
    return _state.source_available(name)


def _mark_source_down(name, seconds=None):
    _state.mark_source_down(name, seconds)


def _note_source_success(name):
    _state.note_source_success(name)


def _coalesce(key, producer):
    return _state.coalesce(key, producer)


def _set_active_source(source):
    _state.set_active_source(source)


def _rss_throttle():
    _state.rss_throttle()


def _redact_proxy(proxy):
    """Hide any user:pass credentials in a proxy URL before it goes to a log."""
    return re.sub(r'//[^@/]+@', '//***@', proxy)


def _next_proxy():
    return _state.next_proxy()


def _mark_proxy_down(proxy):
    _state.mark_proxy_down(proxy)


def _http_get(url, headers, timeout=15):
    """GET `url`, routed through a configured proxy when one is set.

    With no proxy configured this is a plain requests.get. With a pool, requests are
    rotated across proxies and a proxy that fails to *connect* is cooled down and the
    next one tried. If proxies are configured but all are cooling down we raise rather
    than fall back to a direct request, so IP hiding, once on, can't silently leak.
    """
    if not _PROXIES:
        return requests.get(url, headers=headers, timeout=timeout)

    last_err = None
    for _ in range(len(_PROXIES)):
        proxy = _next_proxy()
        if proxy is None:
            break
        try:
            return requests.get(url, headers=headers, timeout=timeout,
                                 proxies={'http': proxy, 'https': proxy})
        except (requests.exceptions.ProxyError,
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError) as e:
            last_err = e
            _mark_proxy_down(proxy)
            logging.warning(f"Proxy {_redact_proxy(proxy)} failed to connect: {e}; trying next")
    raise last_err or RuntimeError("All configured proxies are cooling down")


def fetch_posts_json(subreddit, limit=10):
    """Fetch posts via the anonymous old.reddit.com JSON endpoint (mostly blocked now)."""
    url = f"https://old.reddit.com/r/{subreddit}/new.json?limit={limit}"
    try:
        response = _http_get(url, headers={'User-Agent': JSON_USER_AGENT})
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
    """Fetch top-level comments from a Reddit thread via the JSON endpoint, sorted by new."""
    url = f"https://old.reddit.com/r/{subreddit}/comments/{thread_id}.json?limit={limit}&sort=new"
    try:
        response = _http_get(url, headers={'User-Agent': JSON_USER_AGENT})
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


def _sylvia_get(path):
    """GET a Sylvia gateway path with the API key. Raises RuntimeError on auth (401/403)
    and rate-limit (429) so the dispatcher cools the source down; raises for other HTTP
    errors too. Returns the parsed JSON body."""
    response = requests.get(f"{SYLVIA_BASE_URL}{path}",
                            headers={'X-API-KEY': SYLVIA_API_KEY}, timeout=SYLVIA_TIMEOUT)
    if response.status_code in (401, 403):
        raise RuntimeError(f"Sylvia auth failed ({response.status_code}); check SYLVIA_API_KEY")
    if response.status_code == 429:
        raise RuntimeError("Sylvia rate limit hit (429)")
    response.raise_for_status()
    return response.json()


def fetch_posts_sylvia(subreddit, limit=10):
    """Fetch posts via the Sylvia Reddit gateway. Returns native-Reddit-shaped post data
    (score/domain/flair all present), fetched from Sylvia's IP rather than ours. Paid per
    request, so only reached when 'sylvia' is in the source order and SYLVIA_API_KEY is set."""
    data = _sylvia_get(f"/r/{subreddit}/new?limit={limit}")
    posts = []
    for post_data in data.get('data', {}).get('posts', [])[:limit]:
        posts.append({
            'id': post_data.get('id', ''),
            'title': post_data.get('title', ''),
            'url': post_data.get('url', ''),
            'score': post_data.get('score', 0),
            'permalink': post_data.get('permalink', ''),
            'domain': post_data.get('domain', ''),
            'link_flair_text': post_data.get('link_flair_text') or '',
            'author': post_data.get('author', ''),
        })
    record_fetch_success()
    return posts


def fetch_thread_comments_sylvia(subreddit, thread_id, limit=500):
    """Fetch a thread's top-level comments via the Sylvia gateway. Its 'full_thread'
    response mirrors Reddit's native [post_listing, comment_listing] pair, so we read the
    t1 children of the second listing (same shape as fetch_thread_comments_json)."""
    data = _sylvia_get(f"/submission/{thread_id}/full?sort=new")
    thread = data.get('data', {}).get('thread', [])
    if not isinstance(thread, list) or len(thread) < 2:
        logging.error(f"Unexpected Sylvia thread structure for {thread_id}")
        return None

    comments = []
    for child in thread[1].get('data', {}).get('children', []):
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


def fetch_posts_rss(subreddit, limit=10):
    """Fetch posts via the www.reddit.com Atom feed (no auth). Raises on 403/429 so the
    dispatcher can fall through and back off. Note: RSS exposes no score and no external
    domain, so those fields degrade to 0 / '' (score/domain filters won't match)."""
    _rss_throttle()
    url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit={limit}"
    response = _http_get(url, headers={'User-Agent': RSS_USER_AGENT})
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
    response = _http_get(url, headers={'User-Agent': RSS_USER_AGENT})
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


def fetch_posts(subreddit, limit, reddit):
    """Fetch posts, coalescing concurrent/duplicate calls for the same subreddit+limit
    so overlapping monitors share one request. See _fetch_posts_impl for the chain."""
    return _coalesce(('posts', subreddit, limit),
                     lambda: _fetch_posts_impl(subreddit, limit, reddit))


def _fetch_posts_impl(subreddit, limit, reddit):
    """Try each configured source in order until one returns data.

    Returns (posts, source_name), or (None, None) if every source failed.
    """
    for source in config.get_source_order():
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
            elif source == 'sylvia':
                posts = fetch_posts_sylvia(subreddit, limit)
            else:
                continue
        except Exception as e:
            error_str = str(e)
            if source == 'oauth' and ('401' in error_str or 'unauthorized' in error_str.lower()):
                if _claim_auth_error_notification():
                    notifications.notify_error(
                        "Reddit API authentication failed (401). Falling back to alternative sources (RSS/JSON).")
            logging.warning(f"Reddit source '{source}' failed for r/{subreddit}: {e}")
            _mark_source_down(source)
            continue

        if posts is None:
            logging.warning(f"Reddit source '{source}' returned nothing for r/{subreddit}")
            _mark_source_down(source)
            continue

        if source == 'oauth':
            _reset_auth_error_notification()
        _note_source_success(source)
        record_fetch_success()
        _set_active_source(source)
        return posts, source

    logging.error(f"All Reddit sources failed for r/{subreddit}")
    return None, None


def fetch_thread_comments(subreddit, thread_id, reddit):
    """Fetch a thread's comments, coalescing concurrent/duplicate calls for the same
    thread so overlapping monitors share one request. See _fetch_thread_comments_impl."""
    return _coalesce(('comments', subreddit, thread_id),
                     lambda: _fetch_thread_comments_impl(subreddit, thread_id, reddit))


def _fetch_thread_comments_impl(subreddit, thread_id, reddit):
    """Fetch a thread's comments through the configured source chain (see config.get_source_order)."""
    for source in config.get_source_order():
        if not _source_available(source):
            continue
        try:
            if source == 'oauth':
                if reddit is None:
                    continue
                submission = reddit.submission(id=thread_id)
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
                comments = fetch_thread_comments_rss(subreddit, thread_id)
            elif source == 'json':
                comments = fetch_thread_comments_json(subreddit, thread_id)
            elif source == 'sylvia':
                comments = fetch_thread_comments_sylvia(subreddit, thread_id)
            else:
                continue
        except Exception as e:
            logging.warning(f"Comment source '{source}' failed for thread {thread_id}: {e}")
            _mark_source_down(source)
            continue

        if comments is None:
            _mark_source_down(source)
            continue

        _note_source_success(source)
        record_fetch_success()
        return comments

    logging.error(f"All sources failed fetching comments for thread {thread_id}")
    return None
