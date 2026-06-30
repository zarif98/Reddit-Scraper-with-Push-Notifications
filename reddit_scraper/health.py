"""Uptime Kuma push heartbeats.

A standard up/down monitor (e.g. Docker container running) can't tell that the bot
is busy failing. These push heartbeats report real health instead:
- the primary heartbeat reports UP only while Reddit fetches are succeeding;
- the optional fallback heartbeat reports DOWN when OAuth is expected but the bot
  is on an RSS/JSON fallback, so degradation is alerted while the primary stays UP.
"""
import os
import time
import logging

import requests

from . import config, credentials, sources


def send_kuma_heartbeat():
    """Report bot health to the primary Uptime Kuma Push monitor.

    Reports UP only if a Reddit fetch has succeeded within KUMA_FETCH_STALE_SECONDS;
    otherwise DOWN. No-op unless KUMA_PUSH_URL is set.
    """
    push_url = os.getenv('KUMA_PUSH_URL')
    if push_url:
        stale_after = int(os.getenv('KUMA_FETCH_STALE_SECONDS', '1500'))  # 25 min
        now = time.time()
        last = sources._LAST_FETCH_SUCCESS_TS

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
    creds = credentials.CREDENTIALS or {}
    has_app = bool(creds.get('reddit_client_id') and creds.get('reddit_client_secret'))
    return has_app and 'oauth' in config.get_source_order()


def send_kuma_fallback_heartbeat():
    """Report to a SECOND Uptime Kuma Push monitor that tracks API vs fallback usage.
    Reports DOWN when OAuth is expected but the bot is currently on RSS/JSON. No-op
    unless KUMA_FALLBACK_PUSH_URL is set."""
    url = os.getenv('KUMA_FALLBACK_PUSH_URL')
    if not url:
        return

    active = sources._active_source
    if not _oauth_expected():
        status, msg = 'up', f"using {active or 'rss/json'} (by configuration)"
    elif active == 'oauth':
        status, msg = 'up', 'using authenticated API'
    else:
        status, msg = 'down', f"OAuth unavailable - on fallback source ({active or 'none'})"

    try:
        requests.get(url, params={'status': status, 'msg': msg}, timeout=5)
    except requests.RequestException as e:
        logging.warning(f"Failed to send Uptime Kuma fallback heartbeat: {e}")
