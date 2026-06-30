"""Apprise-based notification dispatch."""
import logging

import apprise

from . import credentials


def _notification_urls():
    return credentials.CREDENTIALS.get('notification_urls', []) if credentials.CREDENTIALS else []


def dispatch(body, title):
    """Send a notification to all configured Apprise services.

    Returns the apprise result (truthy on success), or None if nothing is configured.
    """
    urls = _notification_urls()
    if not urls:
        return None
    try:
        apobj = apprise.Apprise()
        for url in urls:
            apobj.add(url)
        return apobj.notify(body=body, title=title)
    except Exception as e:
        logging.error(f"Error sending notification: {e}")
        return False


def notify_error(message):
    """Send an error notification (used by the source dispatcher and main loop)."""
    if not _notification_urls():
        logging.warning("No notification services configured, cannot send error notification")
        return
    logging.error("Error occurred. Sending error notification...")
    result = dispatch(f"Error in Reddit Scraper: {message}", "⚠️ Reddit Monitor Error")
    if result:
        logging.info("Error notification sent successfully")
    else:
        logging.warning("Error notification may have failed")
