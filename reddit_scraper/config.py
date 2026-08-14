"""Configuration: data paths, search.json access, and data-source ordering.

Paths are resolved from the DATA_DIR env var at call time (not captured at import)
so tests can repoint DATA_DIR and reload entrypoints without stale paths.
"""

import json
import logging
import os
import uuid

from . import models

# Monitor color palette (used to auto-assign a color on create). MUST stay in sync with the
# frontend picker in frontend/types/monitor.ts — keep the two lists identical.
DEFAULT_COLORS = [
    '#8B5CF6',  # Purple
    '#3B82F6',  # Blue
    '#22C55E',  # Green
    '#EF4444',  # Red
    '#F97316',  # Orange
    '#EC4899',  # Pink
    '#06B6D4',  # Cyan
    '#EAB308',  # Yellow
    '#10B981',  # Emerald
    '#F43F5E',  # Rose
]

# Data-source pathways, tried in order by the dispatcher:
#   'oauth'  - authenticated PRAW API (full login OR app-only read-only). Richest + unblocked.
#   'json'   - anonymous old.reddit.com JSON. Often blocked, but when it works it returns
#              full post data (score, domain, flair) unlike RSS, so it's preferred over RSS.
#   'rss'    - www.reddit.com Atom feed (no creds, rate-limited, no score/domain). Last resort.
#   'sylvia' - api.sylvia-api.com third-party Reddit gateway (full native-JSON data, hides
#              our IP, but PAID per request and needs SYLVIA_API_KEY). Opt-in: not in the
#              default order, and skipped entirely unless a key is set (see sources).
# Backoff (see sources._mark_source_down) keeps a blocked source from being retried hot,
# so ordering a richer-but-flakier source first costs only an occasional cheap re-probe.
VALID_SOURCES = ('oauth', 'rss', 'json', 'sylvia')
DEFAULT_SOURCE_ORDER = ['oauth', 'json', 'rss']

# The single source of truth for "does this source provide score/domain data and count as a
# healthy primary (not a degradation)?" Everything that needs that distinction derives from
# here: the bot's fallback flag (sources._SourceState.set_active_source), the API's
# rich_filters_supported (api.get_source_capability), and the UI banner/filter gating. Add a
# new rich source here and all three stay in agreement. `json` returns score/domain too but
# is an unofficial, frequently-blocked fallback, so it is deliberately not counted rich.
RICH_SOURCES = ('oauth', 'sylvia')


def supports_rich_filters(source):
    """True if `source` provides score/domain (so upvote/domain filters apply and it's not
    a degraded fallback for UI purposes). See RICH_SOURCES."""
    return source in RICH_SOURCES


# The UI's data-source picker maps a chosen primary to a full source order. The free json/rss
# pathways stay as a last-ditch fallback behind the primary so a blocked primary degrades
# gracefully. Lives here (not in api.py) so all source-topology knowledge is in one module.
SOURCE_ORDER_PRESETS = {
    'reddit': ['oauth', 'json', 'rss'],
    'sylvia': ['sylvia', 'json', 'rss'],
}


# --- Paths (call-time, env-aware) ---
def get_data_dir():
    return os.environ.get('DATA_DIR', '/data')


def get_config_path():
    return os.path.join(get_data_dir(), 'search.json')


def get_credentials_path():
    return os.path.join(get_data_dir(), 'credentials.json')


def get_bot_status_path():
    return os.path.join(get_data_dir(), 'bot_status.json')


def get_processed_submissions_path():
    return os.path.join(get_data_dir(), 'processed_submissions.pkl')


# --- search.json access ---
def read_config():
    """Simple read used by the bot loop; returns None on missing/invalid file."""
    path = get_config_path()
    logging.info(f"Loading configuration from: {path}")
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"Configuration file not found at: {path}")
        return None
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from configuration file: {path}")
        return None


def get_config_mtime():
    try:
        return os.path.getmtime(get_config_path())
    except OSError:
        return None


def get_credentials_mtime():
    try:
        return os.path.getmtime(get_credentials_path())
    except OSError:
        return None


def save_config(config):
    with open(get_config_path(), 'w') as f:
        json.dump(config, f, indent=4)


def normalize_monitor(monitor, index=0):
    """Return a monitor dict normalized through the Monitor model: missing id/name/color and
    other defaults filled in, tidy on-disk shape. Bot-only/legacy fields are preserved. A
    monitor that can't be validated (e.g. no subreddit) is returned unchanged."""
    try:
        seeded = {
            'id': monitor.get('id') or str(uuid.uuid4()),
            'color': monitor.get('color') or DEFAULT_COLORS[index % len(DEFAULT_COLORS)],
            **monitor,
        }
        return models.Monitor(**seeded).to_stored_dict()
    except Exception:
        return monitor


def load_managed_config():
    """Normalizing read used by the API: fills in ids/defaults via the Monitor model, creates
    a default file when missing, and persists any normalization it had to apply."""
    path = get_config_path()
    try:
        with open(path, 'r') as f:
            config = json.load(f)

        monitors = config.get('subreddits_to_search', [])
        normalized = [normalize_monitor(m, i) for i, m in enumerate(monitors)]
        if normalized != monitors:
            config['subreddits_to_search'] = normalized
            save_config(config)
        return config
    except FileNotFoundError:
        default_config = {'subreddits_to_search': []}
        save_config(default_config)
        return default_config
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON in config file: {e}")


# --- data-source ordering ---
_SOURCE_ORDER = None


def get_source_order():
    return list(_SOURCE_ORDER) if _SOURCE_ORDER else list(DEFAULT_SOURCE_ORDER)


def set_source_order(order):
    """Set the ordered list of data-source pathways, keeping only valid names."""
    global _SOURCE_ORDER
    cleaned = [s.strip() for s in (order or []) if s and s.strip() in VALID_SOURCES]
    _SOURCE_ORDER = cleaned or list(DEFAULT_SOURCE_ORDER)
    logging.info(f"Reddit source order: {' -> '.join(_SOURCE_ORDER)}")


def apply_source_order_from_config(config):
    """Resolve source order from search.json ('source_order'), then REDDIT_SOURCE_ORDER, then default."""
    order = (config or {}).get('source_order')
    if not order:
        env = os.getenv('REDDIT_SOURCE_ORDER')
        order = env.split(',') if env else None
    set_source_order(order)
