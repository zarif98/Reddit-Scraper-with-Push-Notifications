"""
Flask API for Reddit Monitor Web UI
Provides REST endpoints to manage search.json configuration
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import os
import uuid
import requests
from datetime import datetime
import apprise

from reddit_scraper import config as rs_config, credentials as rs_credentials

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration (paths + shared helpers come from the reddit_scraper package)
DATA_DIR = rs_config.get_data_dir()
CONFIG_FILE_PATH = rs_config.get_config_path()
BOT_STATUS_FILE_PATH = rs_config.get_bot_status_path()

DEFAULT_COLORS = rs_config.DEFAULT_COLORS
OPTIONAL_LIST_FIELDS = rs_config.OPTIONAL_LIST_FIELDS
clean_monitor = rs_config.clean_monitor


def load_config():
    """Load configuration from search.json (normalizing ids/fields). Delegates to shared package."""
    return rs_config.load_managed_config()


def save_config(config):
    """Save configuration to search.json file."""
    rs_config.save_config(config)


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'config_path': CONFIG_FILE_PATH
    })


def get_source_capability():
    """Report which data-source pathways are configured and whether the OAuth API
    (required for score/domain filters) is available. Used by the UI to hide filters
    that the active pathways can't provide."""
    default_order = rs_config.DEFAULT_SOURCE_ORDER
    try:
        config = load_config() or {}
    except Exception:
        config = {}
    order = [s for s in (config.get('source_order') or default_order) if s in rs_config.VALID_SOURCES]
    if not order:
        order = list(default_order)

    creds = load_credentials()
    client_id = creds.get('reddit_client_id') or os.getenv('REDDIT_CLIENT_ID')
    client_secret = creds.get('reddit_client_secret') or os.getenv('REDDIT_CLIENT_SECRET')
    oauth_available = bool(client_id and client_secret) and 'oauth' in order

    sylvia_key = creds.get('sylvia_api_key') or os.getenv('SYLVIA_API_KEY')
    sylvia_available = bool(sylvia_key) and 'sylvia' in order

    return {
        'source_order': order,
        'oauth_available': oauth_available,
        # score/domain need a full-data source: the authenticated API or the Sylvia
        # gateway both expose them; RSS does not (so filters can't be applied there).
        'rich_filters_supported': oauth_available or sylvia_available,
    }


@app.route('/api/status', methods=['GET'])
def bot_status():
    """Get bot status including fallback mode warning and source capability."""
    status = {'using_json_fallback': False, 'message': None, 'updated_at': None}
    try:
        if os.path.exists(BOT_STATUS_FILE_PATH):
            with open(BOT_STATUS_FILE_PATH, 'r') as f:
                status = json.load(f)
    except Exception as e:
        status['error'] = str(e)

    try:
        status.update(get_source_capability())
    except Exception as e:
        status.setdefault('error', str(e))

    return jsonify(status)


@app.route('/api/subreddits/search', methods=['GET'])
def search_subreddits():
    """Search for subreddits using Reddit's API."""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify({'subreddits': []})
    
    try:
        # Use Reddit's search API
        headers = {'User-Agent': 'RedditMonitorWebUI/1.0'}
        response = requests.get(
            f'https://www.reddit.com/subreddits/search.json?q={query}&limit=10',
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            subreddits = []
            for child in data.get('data', {}).get('children', []):
                sub_data = child.get('data', {})
                subreddits.append({
                    'name': sub_data.get('display_name', ''),
                    'title': sub_data.get('title', ''),
                    'subscribers': sub_data.get('subscribers', 0),
                    'public_description': sub_data.get('public_description', '')[:100]
                })
            return jsonify({'subreddits': subreddits})
        else:
            return jsonify({'subreddits': [], 'error': 'Reddit API error'})
    except Exception as e:
        return jsonify({'subreddits': [], 'error': str(e)})


@app.route('/api/subreddits/validate/<subreddit_name>', methods=['GET'])
def validate_subreddit(subreddit_name):
    """Validate that a subreddit exists."""
    if not subreddit_name or len(subreddit_name) < 2:
        return jsonify({'valid': False, 'error': 'Subreddit name too short'})
    
    try:
        headers = {'User-Agent': 'RedditMonitorWebUI/1.0'}
        response = requests.get(
            f'https://www.reddit.com/r/{subreddit_name}/about.json',
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            sub_data = data.get('data', {})
            # Check if it's a valid subreddit (has required fields)
            if sub_data.get('display_name'):
                return jsonify({
                    'valid': True,
                    'name': sub_data.get('display_name'),
                    'title': sub_data.get('title', ''),
                    'subscribers': sub_data.get('subscribers', 0),
                    'nsfw': sub_data.get('over18', False)
                })
        
        # Subreddit doesn't exist or is private
        return jsonify({'valid': False, 'error': 'Subreddit not found'})
    except Exception as e:
        # On error, allow the subreddit (don't block on network issues)
        return jsonify({'valid': True, 'error': f'Could not verify: {str(e)}'})


@app.route('/api/monitors', methods=['GET'])
def get_monitors():
    """Get all monitors."""
    try:
        config = load_config()
        return jsonify({
            'monitors': config.get('subreddits_to_search', [])
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitors', methods=['POST'])
def create_monitor():
    """Create a new monitor."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        if not data.get('subreddit'):
            return jsonify({'error': 'Subreddit is required'}), 400
        
        config = load_config()
        monitors = config.get('subreddits_to_search', [])
        
        # Create new monitor with defaults
        new_monitor = {
            'id': str(uuid.uuid4()),
            'name': data.get('name', f"r/{data['subreddit']}"),
            'subreddit': data['subreddit'].strip().lower().replace('r/', ''),
            'keywords': data.get('keywords', []),
            'exclude_keywords': data.get('exclude_keywords', []),
            'min_upvotes': data.get('min_upvotes'),
            'color': data.get('color', DEFAULT_COLORS[len(monitors) % len(DEFAULT_COLORS)]),
            'enabled': data.get('enabled', True),
            'cooldown_minutes': data.get('cooldown_minutes', 10),
            'max_post_age_hours': data.get('max_post_age_hours', 12),
            'domain_contains': data.get('domain_contains', []),
            'domain_excludes': data.get('domain_excludes', []),
            'flair_contains': data.get('flair_contains', []),
            'author_includes': data.get('author_includes', []),
            'author_excludes': data.get('author_excludes', [])
        }
        
        clean_monitor(new_monitor)
        monitors.append(new_monitor)
        config['subreddits_to_search'] = monitors
        save_config(config)

        return jsonify(new_monitor), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitors/<monitor_id>', methods=['GET'])
def get_monitor(monitor_id):
    """Get a specific monitor by ID."""
    try:
        config = load_config()
        monitors = config.get('subreddits_to_search', [])
        
        for monitor in monitors:
            if monitor.get('id') == monitor_id:
                return jsonify(monitor)
        
        return jsonify({'error': 'Monitor not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitors/<monitor_id>', methods=['PUT'])
def update_monitor(monitor_id):
    """Update an existing monitor."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        config = load_config()
        monitors = config.get('subreddits_to_search', [])
        
        for i, monitor in enumerate(monitors):
            if monitor.get('id') == monitor_id:
                # Update fields
                if 'name' in data:
                    monitors[i]['name'] = data['name']
                if 'subreddit' in data:
                    monitors[i]['subreddit'] = data['subreddit'].strip().lower().replace('r/', '')
                if 'keywords' in data:
                    monitors[i]['keywords'] = data['keywords']
                if 'exclude_keywords' in data:
                    monitors[i]['exclude_keywords'] = data['exclude_keywords']
                if 'min_upvotes' in data:
                    monitors[i]['min_upvotes'] = data['min_upvotes']
                if 'color' in data:
                    monitors[i]['color'] = data['color']
                if 'enabled' in data:
                    monitors[i]['enabled'] = data['enabled']
                if 'cooldown_minutes' in data:
                    monitors[i]['cooldown_minutes'] = data['cooldown_minutes']
                if 'max_post_age_hours' in data:
                    monitors[i]['max_post_age_hours'] = data['max_post_age_hours']
                # New filter fields
                if 'domain_contains' in data:
                    monitors[i]['domain_contains'] = data['domain_contains']
                if 'domain_excludes' in data:
                    monitors[i]['domain_excludes'] = data['domain_excludes']
                if 'flair_contains' in data:
                    monitors[i]['flair_contains'] = data['flair_contains']
                if 'author_includes' in data:
                    monitors[i]['author_includes'] = data['author_includes']
                if 'author_excludes' in data:
                    monitors[i]['author_excludes'] = data['author_excludes']
                
                clean_monitor(monitors[i])
                config['subreddits_to_search'] = monitors
                save_config(config)

                return jsonify(monitors[i])
        
        return jsonify({'error': 'Monitor not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitors/<monitor_id>', methods=['DELETE'])
def delete_monitor(monitor_id):
    """Delete a monitor."""
    try:
        config = load_config()
        monitors = config.get('subreddits_to_search', [])
        
        for i, monitor in enumerate(monitors):
            if monitor.get('id') == monitor_id:
                deleted = monitors.pop(i)
                config['subreddits_to_search'] = monitors
                save_config(config)
                return jsonify({'deleted': deleted})
        
        return jsonify({'error': 'Monitor not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Credentials file path
CREDENTIALS_FILE_PATH = rs_config.get_credentials_path()


def load_credentials():
    """Load credentials from credentials.json file. Delegates to shared package."""
    return rs_credentials.read_credentials_file()


def save_credentials(credentials):
    """Save credentials to credentials.json file."""
    rs_credentials.save_credentials_file(credentials)


def is_configured():
    """Check if essential credentials are configured (Reddit only, notifications optional)."""
    creds = load_credentials()
    required = ['reddit_client_id', 'reddit_client_secret', 'reddit_username', 'reddit_password']
    return all(creds.get(key) for key in required)


@app.route('/api/credentials/status', methods=['GET'])
def get_credentials_status():
    """Check if credentials are configured (without exposing them)."""
    creds = load_credentials()
    notification_urls = creds.get('notification_urls', [])
    return jsonify({
        'configured': is_configured(),
        'has_reddit': bool(creds.get('reddit_client_id') and creds.get('reddit_client_secret')),
        'has_notifications': len(notification_urls) > 0,
        'notification_count': len(notification_urls),
        'has_reddit_username': bool(creds.get('reddit_username')),
        'has_sylvia': bool(creds.get('sylvia_api_key')),
    })


@app.route('/api/credentials', methods=['GET'])
def get_credentials():
    """Get credentials (masked for security)."""
    creds = load_credentials()
    notification_urls = creds.get('notification_urls', [])
    
    # Mask notification URLs (show service type but hide tokens)
    masked_urls = []
    for url in notification_urls:
        # Show the protocol/service type, mask the rest
        if '://' in url:
            protocol = url.split('://')[0]
            masked_urls.append(f"{protocol}://••••••••")
        else:
            masked_urls.append('••••••••')
    
    return jsonify({
        'reddit_client_id': mask_value(creds.get('reddit_client_id', '')),
        'reddit_client_secret': mask_value(creds.get('reddit_client_secret', '')),
        'reddit_username': creds.get('reddit_username', ''),
        'reddit_password': mask_value(creds.get('reddit_password', '')),
        'reddit_user_agent': creds.get('reddit_user_agent', ''),
        'sylvia_api_key': mask_value(creds.get('sylvia_api_key', '')),
        'notification_urls': notification_urls,  # Return full URLs for editing
        'notification_urls_masked': masked_urls,  # Masked for display
    })


def mask_value(value):
    """Mask a sensitive value, showing only first 4 chars."""
    if not value or len(value) < 8:
        return '••••••••' if value else ''
    return value[:4] + '••••••••'


def is_masked(value):
    """True if value is empty or a masked placeholder, so it must not overwrite stored data."""
    return not value or '••••' in value


def resolve_credential(data, creds, key):
    """Pick an incoming credential value, falling back to the stored one when the incoming
    value is missing or still masked (the UI sends masked placeholders for untouched fields)."""
    incoming = data.get(key)
    return incoming if not is_masked(incoming) else creds.get(key, '')


def validate_reddit_credentials(client_id, client_secret, username, password, user_agent):
    """Validate Reddit API credentials by attempting authentication.
    
    Returns (success: bool, error_message: str or None)
    """
    # First, check for non-ASCII characters
    for name, value in [('client_id', client_id), ('client_secret', client_secret),
                        ('username', username), ('password', password), ('user_agent', user_agent)]:
        non_ascii = rs_credentials.find_non_ascii(value)
        if non_ascii:
            i, c = non_ascii[0]
            return False, f"Non-ASCII character found in {name} at position {i}: '{c}' ({hex(ord(c))}). Please re-type the credential."
    
    # Try to authenticate with Reddit
    try:
        auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
        headers = {'User-Agent': user_agent}
        data = {
            'grant_type': 'password',
            'username': username,
            'password': password
        }
        response = requests.post(
            'https://www.reddit.com/api/v1/access_token',
            auth=auth,
            headers=headers,
            data=data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if 'access_token' in result:
                return True, None
            elif 'error' in result:
                return False, f"Reddit API error: {result.get('error')}"
            else:
                return False, "Unexpected response from Reddit API"
        elif response.status_code == 401:
            return False, "Invalid client_id or client_secret"
        elif response.status_code == 400:
            result = response.json()
            if result.get('error') == 'invalid_grant':
                return False, "Invalid username or password"
            return False, f"Bad request: {result.get('error', 'unknown')}"
        else:
            return False, f"Reddit API returned status {response.status_code}"
    except requests.exceptions.Timeout:
        return False, "Connection to Reddit timed out"
    except requests.exceptions.RequestException as e:
        return False, f"Connection error: {str(e)}"


@app.route('/api/credentials', methods=['PUT'])
def update_credentials():
    """Update credentials."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        creds = load_credentials()
        
        # Only update fields that are provided and not masked
        fields = ['reddit_client_id', 'reddit_client_secret', 'reddit_username',
                  'reddit_password', 'reddit_user_agent', 'sylvia_api_key']
        
        for field in fields:
            if field in data and not is_masked(data[field]):
                creds[field] = data[field]
        
        # Handle notification_urls array
        if 'notification_urls' in data:
            # Filter out empty strings
            urls = [url.strip() for url in data['notification_urls'] if url and url.strip()]
            creds['notification_urls'] = urls
        
        # Validate Reddit credentials if requested or if they changed
        validate = data.get('validate', False)
        if validate:
            valid, error = validate_reddit_credentials(
                creds.get('reddit_client_id', ''),
                creds.get('reddit_client_secret', ''),
                creds.get('reddit_username', ''),
                creds.get('reddit_password', ''),
                creds.get('reddit_user_agent', 'RedditMonitor/1.0')
            )
            if not valid:
                return jsonify({
                    'success': False,
                    'error': error,
                    'validation_failed': True
                }), 400
        
        save_credentials(creds)
        
        return jsonify({
            'success': True,
            'configured': is_configured(),
            'notification_count': len(creds.get('notification_urls', []))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Which data source the UI dropdown selects, mapped to the bot's source order.
# The free json/rss pathways are kept as a last-ditch fallback behind the chosen
# primary so a blocked primary still degrades gracefully rather than going dark.
SOURCE_PRESETS = {
    'reddit': ['oauth', 'json', 'rss'],
    'sylvia': ['sylvia', 'json', 'rss'],
}


@app.route('/api/source-order', methods=['GET'])
def get_source_order():
    """Report the active data source (derived from the primary of the saved source order)."""
    try:
        config = load_config() or {}
    except Exception:
        config = {}
    order = config.get('source_order') or []
    active = 'sylvia' if order and order[0] == 'sylvia' else 'reddit'
    return jsonify({'active_source': active, 'source_order': order})


@app.route('/api/source-order', methods=['PUT'])
def update_source_order():
    """Set the active data source. Writes source_order into search.json; the bot
    hot-reloads that file, so the change takes effect without a restart."""
    try:
        data = request.get_json() or {}
        active = data.get('active_source')
        if active not in SOURCE_PRESETS:
            return jsonify({'error': f"active_source must be one of {list(SOURCE_PRESETS)}"}), 400

        config = load_config() or {}
        config['source_order'] = SOURCE_PRESETS[active]
        save_config(config)
        return jsonify({'success': True, 'active_source': active,
                        'source_order': SOURCE_PRESETS[active]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/credentials/test-reddit', methods=['POST'])
def test_reddit_credentials():
    """Test Reddit API credentials without saving them."""
    try:
        data = request.get_json()
        creds = load_credentials()
        
        # Use provided values or fall back to stored ones (masked = untouched)
        client_id = resolve_credential(data, creds, 'reddit_client_id')
        client_secret = resolve_credential(data, creds, 'reddit_client_secret')
        username = resolve_credential(data, creds, 'reddit_username')
        password = resolve_credential(data, creds, 'reddit_password')
        user_agent = data.get('reddit_user_agent') or creds.get('reddit_user_agent', 'RedditMonitor/1.0')
        
        if not all([client_id, client_secret, username, password]):
            return jsonify({
                'success': False,
                'error': 'Missing required Reddit credentials'
            }), 400
        
        valid, error = validate_reddit_credentials(client_id, client_secret, username, password, user_agent)
        
        return jsonify({
            'success': valid,
            'error': error
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/notifications/test', methods=['POST'])
def test_notification():
    """Send a test notification to all configured services."""
    try:
        creds = load_credentials()
        notification_urls = creds.get('notification_urls', [])
        
        if not notification_urls:
            return jsonify({
                'success': False,
                'error': 'No notification services configured'
            }), 400
        
        # Create Apprise instance and add all URLs
        apobj = apprise.Apprise()
        for url in notification_urls:
            apobj.add(url)
        
        # Send test notification
        result = apobj.notify(
            body="This is a test notification from Reddit Monitor. If you see this, notifications are working! 🎉",
            title="🧪 Test Notification"
        )
        
        return jsonify({
            'success': result,
            'services_count': len(notification_urls),
            'message': 'Test notification sent!' if result else 'Some notifications may have failed'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500



if __name__ == '__main__':
    print(f"📡 Reddit Monitor API starting...")
    print(f"📁 Config file: {CONFIG_FILE_PATH}")
    print(f"🔐 Credentials file: {CREDENTIALS_FILE_PATH}")
    print(f"🌐 API available at: http://0.0.0.0:5001")
    print(f"📱 Access from other devices using your local IP")
    # Use debug=False in production for better performance
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=5001, debug=debug_mode)
