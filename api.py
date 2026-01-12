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

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE_PATH = os.path.join(DATA_DIR, 'search.json')

# Default color palette (matching Pager app)
DEFAULT_COLORS = [
    '#8B5CF6',  # Purple
    '#3B82F6',  # Blue
    '#22C55E',  # Green
    '#EF4444',  # Red
    '#F97316',  # Orange
    '#EC4899',  # Pink
    '#06B6D4',  # Cyan
    '#EAB308',  # Yellow
]


def load_config():
    """Load configuration from search.json file."""
    try:
        with open(CONFIG_FILE_PATH, 'r') as f:
            config = json.load(f)
        
        # Ensure all monitors have IDs and new fields
        monitors = config.get('subreddits_to_search', [])
        updated = False
        
        for i, monitor in enumerate(monitors):
            if 'id' not in monitor:
                monitor['id'] = str(uuid.uuid4())
                updated = True
            if 'name' not in monitor:
                # Generate name from subreddit
                monitor['name'] = f"r/{monitor.get('subreddit', 'unknown')}"
                updated = True
            if 'color' not in monitor:
                monitor['color'] = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
                updated = True
            if 'enabled' not in monitor:
                monitor['enabled'] = True
                updated = True
            if 'exclude_keywords' not in monitor:
                monitor['exclude_keywords'] = []
                updated = True
            if 'cooldown_minutes' not in monitor:
                monitor['cooldown_minutes'] = 10
                updated = True
            if 'max_post_age_hours' not in monitor:
                monitor['max_post_age_hours'] = 12
                updated = True
            # New filter fields
            if 'domain_contains' not in monitor:
                monitor['domain_contains'] = []
                updated = True
            if 'domain_excludes' not in monitor:
                monitor['domain_excludes'] = []
                updated = True
            if 'flair_contains' not in monitor:
                monitor['flair_contains'] = []
                updated = True
            if 'author_includes' not in monitor:
                monitor['author_includes'] = []
                updated = True
            if 'author_excludes' not in monitor:
                monitor['author_excludes'] = []
                updated = True
        
        # Save if we added any fields
        if updated:
            config['subreddits_to_search'] = monitors
            save_config(config)
        
        return config
    except FileNotFoundError:
        # Create default config
        default_config = {
            'subreddits_to_search': []
        }
        save_config(default_config)
        return default_config
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON in config file: {e}")


def save_config(config):
    """Save configuration to search.json file."""
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump(config, f, indent=4)


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'config_path': CONFIG_FILE_PATH
    })


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
CREDENTIALS_FILE_PATH = os.path.join(DATA_DIR, 'credentials.json')


def load_credentials():
    """Load credentials from credentials.json file."""
    try:
        with open(CREDENTIALS_FILE_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def save_credentials(credentials):
    """Save credentials to credentials.json file."""
    with open(CREDENTIALS_FILE_PATH, 'w') as f:
        json.dump(credentials, f, indent=4)


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
        'notification_urls': notification_urls,  # Return full URLs for editing
        'notification_urls_masked': masked_urls,  # Masked for display
    })


def mask_value(value):
    """Mask a sensitive value, showing only first 4 chars."""
    if not value or len(value) < 8:
        return '••••••••' if value else ''
    return value[:4] + '••••••••'


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
                  'reddit_password', 'reddit_user_agent']
        
        for field in fields:
            if field in data:
                value = data[field]
                # Don't save masked values
                if value and '••••' not in value:
                    creds[field] = value
        
        # Handle notification_urls array
        if 'notification_urls' in data:
            # Filter out empty strings
            urls = [url.strip() for url in data['notification_urls'] if url and url.strip()]
            creds['notification_urls'] = urls
        
        save_credentials(creds)
        
        return jsonify({
            'success': True,
            'configured': is_configured(),
            'notification_count': len(creds.get('notification_urls', []))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
