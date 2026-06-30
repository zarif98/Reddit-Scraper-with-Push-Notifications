"""Bot status file written for the API/frontend to read."""
import json
import logging
from datetime import datetime, timezone

from . import config, credentials


def save_bot_status(using_fallback, message=None, active_source=None):
    """Persist current bot status (active source, fallback state, credential warning)."""
    try:
        status = {
            'using_json_fallback': using_fallback,
            'active_source': active_source,
            'message': message,
            'credentials_warning': credentials.CREDENTIAL_WARNING,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        with open(config.get_bot_status_path(), 'w') as f:
            json.dump(status, f)
    except Exception as e:
        logging.error(f"Failed to save bot status: {e}")
