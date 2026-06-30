"""Credential loading, sanitization, encoding checks, and PRAW authentication."""
import os
import json
import logging

import praw

from . import config

# Runtime credentials (file + env fallback), populated by detect_auth_capability().
CREDENTIALS = None

# Persistent warning surfaced to the UI when a credential contains characters that
# can't be used for auth (e.g. a pasted Cyrillic lookalike).
CREDENTIAL_WARNING = None


def read_credentials_file():
    """Raw read of credentials.json (used by the API for masking/editing)."""
    try:
        with open(config.get_credentials_path(), 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def save_credentials_file(creds):
    with open(config.get_credentials_path(), 'w') as f:
        json.dump(creds, f, indent=4)


def load_credentials():
    """Runtime credentials: file + env fallback + Pushover migration (used by the bot)."""
    creds = {}
    path = config.get_credentials_path()
    try:
        with open(path, 'r') as f:
            creds = json.load(f)
            logging.info(f"Loaded credentials from: {path}")
    except FileNotFoundError:
        logging.info("No credentials file found, using environment variables")
    except json.JSONDecodeError:
        logging.warning("Invalid credentials file, using environment variables")

    notification_urls = creds.get('notification_urls', [])

    # Auto-migrate old Pushover credentials to Apprise URL format
    if not notification_urls:
        pushover_token = creds.get('pushover_app_token') or os.getenv('PUSHOVER_APP_TOKEN')
        pushover_user = creds.get('pushover_user_key') or os.getenv('PUSHOVER_USER_KEY')
        if pushover_token and pushover_user:
            notification_urls = [f"pover://{pushover_user}@{pushover_token}"]
            logging.info("Auto-migrated Pushover credentials to Apprise format")

    return {
        'notification_urls': notification_urls,
        'reddit_client_id': creds.get('reddit_client_id') or os.getenv('REDDIT_CLIENT_ID'),
        'reddit_client_secret': creds.get('reddit_client_secret') or os.getenv('REDDIT_CLIENT_SECRET'),
        'reddit_user_agent': creds.get('reddit_user_agent') or os.getenv('REDDIT_USER_AGENT'),
        'reddit_username': creds.get('reddit_username') or os.getenv('REDDIT_USERNAME'),
        'reddit_password': creds.get('reddit_password') or os.getenv('REDDIT_PASSWORD'),
    }


def sanitize_credential(value, name):
    """Remove non-ASCII characters from credentials that cause latin-1 encoding errors."""
    if not value:
        return value
    sanitized = value.encode('ascii', 'ignore').decode('ascii')
    if value != sanitized:
        positions = [i for i, c in enumerate(value) if ord(c) > 127]
        logging.warning(f"⚠️ Removed non-ASCII characters from {name}: found Unicode at positions {positions}")
    return sanitized


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
        bad = [i for i, c in enumerate(value) if ord(c) > 127]
        if bad:
            offenders.append(f"{key} (positions {bad})")

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
    """Load credentials into the module global and report which auth pathway is available.

    Credentials are optional: the bot can run on RSS/JSON alone. Full OAuth (login)
    is used when username+password are present; app-only read-only OAuth when only
    client id+secret are present; otherwise no API auth.
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

    return CREDENTIALS


def authenticate_reddit():
    """Build a PRAW client for the 'oauth' pathway.

    Returns a logged-in client if username+password are set, a read-only (app-only)
    client if only client id+secret are set, or None if no app credentials exist
    (the bot then relies on the RSS/JSON pathways).
    """
    creds = CREDENTIALS or {}
    client_id = sanitize_credential(creds.get('reddit_client_id'), 'client_id')
    client_secret = sanitize_credential(creds.get('reddit_client_secret'), 'client_secret')
    user_agent = sanitize_credential(creds.get('reddit_user_agent'), 'user_agent') or 'reddit-scraper/1.0'
    username = sanitize_credential(creds.get('reddit_username'), 'username')
    password = sanitize_credential(creds.get('reddit_password'), 'password')

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
