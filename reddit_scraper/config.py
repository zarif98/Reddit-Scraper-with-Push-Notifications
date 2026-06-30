"""Configuration: data paths, search.json access, and data-source ordering.

Paths are resolved from the DATA_DIR env var at call time (not captured at import)
so tests can repoint DATA_DIR and reload entrypoints without stale paths.
"""
import os
import json
import uuid
import logging

DEFAULT_COLORS = [
    '#8B5CF6', '#3B82F6', '#22C55E', '#EF4444',
    '#F97316', '#EC4899', '#06B6D4', '#EAB308',
]

OPTIONAL_LIST_FIELDS = ['exclude_keywords', 'domain_contains', 'domain_excludes',
                        'flair_contains', 'author_includes', 'author_excludes']

# Data-source pathways, tried in order by the dispatcher:
#   'oauth' - authenticated PRAW API (full login OR app-only read-only).
#   'rss'   - www.reddit.com Atom feed (no creds, rate-limited).
#   'json'  - anonymous old.reddit.com JSON (mostly blocked; last resort).
VALID_SOURCES = ('oauth', 'rss', 'json')
DEFAULT_SOURCE_ORDER = ['oauth', 'rss', 'json']


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


def save_config(config):
    with open(get_config_path(), 'w') as f:
        json.dump(config, f, indent=4)


def clean_monitor(monitor):
    """Strip optional fields that are empty/null to keep search.json tidy."""
    for field in OPTIONAL_LIST_FIELDS:
        if field in monitor and not monitor[field]:
            del monitor[field]
    if 'min_upvotes' in monitor and monitor['min_upvotes'] is None:
        del monitor['min_upvotes']
    return monitor


def load_managed_config():
    """Normalizing read used by the API: ensures ids/fields, creates a default
    file when missing, and persists any fields it had to add."""
    path = get_config_path()
    try:
        with open(path, 'r') as f:
            config = json.load(f)

        monitors = config.get('subreddits_to_search', [])
        updated = False
        for i, monitor in enumerate(monitors):
            if 'id' not in monitor:
                monitor['id'] = str(uuid.uuid4())
                updated = True
            if 'name' not in monitor:
                monitor['name'] = f"r/{monitor.get('subreddit', 'unknown')}"
                updated = True
            if 'color' not in monitor:
                monitor['color'] = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
                updated = True
            if 'enabled' not in monitor:
                monitor['enabled'] = True
                updated = True
            if 'cooldown_minutes' not in monitor:
                monitor['cooldown_minutes'] = 10
                updated = True
            if 'max_post_age_hours' not in monitor:
                monitor['max_post_age_hours'] = 12
                updated = True

        if updated:
            config['subreddits_to_search'] = monitors
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
