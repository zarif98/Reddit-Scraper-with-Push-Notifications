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

# Tracks the last time ANY Reddit fetch genuinely succeeded (used by the Kuma heartbeat).
_LAST_FETCH_SUCCESS_TS = None
# The data source currently serving data.
_active_source = None
# Whether we've already notified about an OAuth 401 (reset on the next oauth success).
_auth_error_notified = False

_source_cooldown_until = {}      # source name -> epoch time until which it is skipped
_source_failures = {}            # source name -> consecutive failure count (for backoff)
_source_state_lock = threading.Lock()
SOURCE_COOLDOWN_SECONDS = int(os.getenv('SOURCE_COOLDOWN_SECONDS', '300'))      # base cooldown
SOURCE_COOLDOWN_MAX = int(os.getenv('SOURCE_COOLDOWN_MAX_SECONDS', '3600'))     # cap on backoff

# RSS is aggressively per-IP rate-limited, so serialize requests with a minimum gap.
_rss_throttle_lock = threading.Lock()
_rss_last_request = [0.0]
RSS_MIN_INTERVAL = float(os.getenv('RSS_MIN_INTERVAL_SECONDS', '4'))

# Short-lived response cache so concurrent monitors covering the same subreddit/thread
# share a single network request instead of each issuing its own (which both wastes
# requests and trips rate limits). TTL only needs to span one scheduling burst.
FETCH_CACHE_TTL = float(os.getenv('FETCH_CACHE_TTL_SECONDS', '90'))
_fetch_cache = {}                # key -> (timestamp, value)
_fetch_cache_lock = threading.Lock()
_fetch_key_locks = {}            # key -> Lock (so concurrent callers coalesce, not stampede)


def record_fetch_success():
    """Mark that a Reddit fetch just succeeded (used by the Kuma heartbeat)."""
    global _LAST_FETCH_SUCCESS_TS
    _LAST_FETCH_SUCCESS_TS = time.time()


def _claim_auth_error_notification():
    """Atomically claim the right to send the one-time OAuth-failure notification.

    Monitors run concurrently, so without this guard every thread that hits the same
    401 fires its own notification. Returns True for exactly one caller until reset
    on the next oauth success.
    """
    global _auth_error_notified
    with _source_state_lock:
        if _auth_error_notified:
            return False
        _auth_error_notified = True
        return True


def _reset_auth_error_notification():
    global _auth_error_notified
    with _source_state_lock:
        _auth_error_notified = False


def _source_available(name):
    with _source_state_lock:
        return time.time() >= _source_cooldown_until.get(name, 0)


def _mark_source_down(name, seconds=None):
    """Cool down a failed source. With no explicit duration, back off exponentially on
    consecutive failures (base, 2x, 4x, ... capped) so a flagged IP / dead source gets
    a real rest instead of being retried every cycle."""
    with _source_state_lock:
        if seconds is None:
            n = _source_failures.get(name, 0) + 1
            _source_failures[name] = n
            cooldown = min(SOURCE_COOLDOWN_SECONDS * (2 ** (n - 1)), SOURCE_COOLDOWN_MAX)
        else:
            cooldown = seconds
        _source_cooldown_until[name] = time.time() + cooldown
    logging.warning(f"Pausing Reddit source '{name}' for {int(cooldown)}s after failure")


def _note_source_success(name):
    """Reset a source's backoff after it succeeds."""
    with _source_state_lock:
        _source_failures[name] = 0


def _coalesce(key, producer):
    """Return a cached fresh value for key, or produce + cache it. Concurrent callers
    for the same key wait on a per-key lock and share the single result."""
    now = time.time()
    with _fetch_cache_lock:
        entry = _fetch_cache.get(key)
        if entry and now - entry[0] < FETCH_CACHE_TTL:
            return entry[1]
        key_lock = _fetch_key_locks.setdefault(key, threading.Lock())

    with key_lock:
        # Re-check inside the per-key lock: another thread may have just produced it.
        now = time.time()
        with _fetch_cache_lock:
            entry = _fetch_cache.get(key)
            if entry and now - entry[0] < FETCH_CACHE_TTL:
                return entry[1]
        value = producer()
        with _fetch_cache_lock:
            _fetch_cache[key] = (time.time(), value)
        return value


def _set_active_source(source):
    """Record (and surface) the data source currently serving data, only when it changes."""
    global _active_source
    if source != _active_source:
        _active_source = source
        logging.info(f"📡 Active Reddit data source: {source}")
        status.save_bot_status(source != 'oauth', f"Active data source: {source}", active_source=source)


def _rss_throttle():
    """Block until at least RSS_MIN_INTERVAL seconds have passed since the last RSS request."""
    with _rss_throttle_lock:
        wait = RSS_MIN_INTERVAL - (time.time() - _rss_last_request[0])
        if wait > 0:
            time.sleep(wait)
        _rss_last_request[0] = time.time()


def fetch_posts_json(subreddit, limit=10):
    """Fetch posts via the anonymous old.reddit.com JSON endpoint (mostly blocked now)."""
    url = f"https://old.reddit.com/r/{subreddit}/new.json?limit={limit}"
    try:
        response = requests.get(url, headers={'User-Agent': JSON_USER_AGENT}, timeout=15)
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
        response = requests.get(url, headers={'User-Agent': JSON_USER_AGENT}, timeout=15)
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
    """Fetch a thread's comments through the configured source chain (oauth -> rss -> json)."""
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
