"""Unit tests for api.py functionality."""
import json
import os
import tempfile
from unittest.mock import patch

import pytest


class TestAPIEndpoints:
    """Tests for Flask API endpoints."""

    @pytest.fixture
    def client(self):
        """Create Flask test client."""
        # Set up temp data directory
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'DATA_DIR': tmpdir}):
                # Create empty config files
                config_path = os.path.join(tmpdir, 'search.json')
                creds_path = os.path.join(tmpdir, 'credentials.json')

                with open(config_path, 'w') as f:
                    json.dump({'subreddits_to_search': [], 'iteration_time_minutes': 5}, f)
                with open(creds_path, 'w') as f:
                    json.dump({}, f)

                # Import after patching
                import importlib

                import api
                importlib.reload(api)

                api.app.config['TESTING'] = True
                with api.app.test_client() as client:
                    yield client

    def test_get_monitors_empty(self, client):
        """Test getting monitors when none exist."""
        response = client.get('/api/monitors')
        assert response.status_code == 200
        data = response.get_json()
        assert 'monitors' in data
        assert len(data['monitors']) == 0

    def test_create_monitor(self, client):
        """Test creating a new monitor."""
        monitor_data = {
            'subreddit': 'hardwareswap',
            'keywords': ['4090', '4080'],
            'name': 'GPU Hunt',
            'enabled': True,
        }

        response = client.post('/api/monitors',
                               data=json.dumps(monitor_data),
                               content_type='application/json')

        assert response.status_code == 201
        data = response.get_json()
        assert 'id' in data
        assert data['subreddit'] == 'hardwareswap'
        assert data['name'] == 'GPU Hunt'

    def test_update_monitor(self, client):
        """Test updating an existing monitor."""
        # First create a monitor
        monitor_data = {
            'subreddit': 'hardwareswap',
            'keywords': ['4090'],
            'name': 'GPU Hunt',
        }
        create_response = client.post('/api/monitors',
                                      data=json.dumps(monitor_data),
                                      content_type='application/json')
        monitor_id = create_response.get_json()['id']

        # Update it
        update_data = {
            'name': 'GPU Hunt Updated',
            'keywords': ['4090', '4080', '3090'],
        }
        response = client.put(f'/api/monitors/{monitor_id}',
                              data=json.dumps(update_data),
                              content_type='application/json')

        assert response.status_code == 200
        data = response.get_json()
        assert data['name'] == 'GPU Hunt Updated'
        assert '3090' in data['keywords']

    def test_delete_monitor(self, client):
        """Test deleting a monitor."""
        # First create a monitor
        monitor_data = {
            'subreddit': 'hardwareswap',
            'keywords': ['4090'],
        }
        create_response = client.post('/api/monitors',
                                      data=json.dumps(monitor_data),
                                      content_type='application/json')
        monitor_id = create_response.get_json()['id']

        # Delete it
        response = client.delete(f'/api/monitors/{monitor_id}')
        assert response.status_code == 200

        # Verify it's gone
        get_response = client.get('/api/monitors')
        assert len(get_response.get_json()['monitors']) == 0

    def test_get_monitor_not_found(self, client):
        """Test getting a non-existent monitor."""
        response = client.get('/api/monitors/nonexistent-id')
        assert response.status_code == 404


class TestCredentialsAPI:
    """Tests for credentials API endpoints."""

    @pytest.fixture
    def client(self):
        """Create Flask test client."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'DATA_DIR': tmpdir}):
                config_path = os.path.join(tmpdir, 'search.json')
                creds_path = os.path.join(tmpdir, 'credentials.json')

                with open(config_path, 'w') as f:
                    json.dump({'subreddits_to_search': []}, f)
                with open(creds_path, 'w') as f:
                    json.dump({
                        'reddit_client_id': 'testid123',
                        'reddit_client_secret': 'testsecret456',
                    }, f)

                import importlib

                import api
                importlib.reload(api)

                api.app.config['TESTING'] = True
                with api.app.test_client() as client:
                    yield client

    def test_credentials_status(self, client):
        """Test checking if credentials are configured."""
        response = client.get('/api/credentials/status')
        assert response.status_code == 200
        data = response.get_json()
        assert 'configured' in data

    def test_get_credentials_masked(self, client):
        """Test that credentials are masked in response."""
        response = client.get('/api/credentials')
        assert response.status_code == 200
        data = response.get_json()

        # Client ID should be partially masked
        if data.get('reddit_client_id'):
            assert '••••' in data['reddit_client_id']

    def test_source_order_defaults_to_reddit(self, client):
        """With no source_order saved, the active source reports as reddit."""
        response = client.get('/api/source-order')
        assert response.status_code == 200
        assert response.get_json()['active_source'] == 'reddit'

    def test_set_source_to_sylvia_persists(self, client):
        """Selecting sylvia writes a sylvia-first order and reads back as sylvia."""
        put = client.put('/api/source-order', json={'active_source': 'sylvia'})
        assert put.status_code == 200
        assert put.get_json()['source_order'] == ['sylvia', 'json', 'rss']
        # persisted + reflected on the next GET
        assert client.get('/api/source-order').get_json()['active_source'] == 'sylvia'

    def test_set_source_back_to_reddit(self, client):
        """Selecting reddit writes an oauth-first order."""
        client.put('/api/source-order', json={'active_source': 'sylvia'})
        put = client.put('/api/source-order', json={'active_source': 'reddit'})
        assert put.get_json()['source_order'] == ['oauth', 'json', 'rss']

    def test_invalid_source_rejected(self, client):
        """An unknown source is rejected with 400."""
        response = client.put('/api/source-order', json={'active_source': 'nope'})
        assert response.status_code == 400

    def test_sylvia_enables_rich_filters(self, client):
        """On Sylvia (with a key), score/domain filters are reported as supported,
        even without a Reddit app — Sylvia returns full post data."""
        client.put('/api/source-order', json={'active_source': 'sylvia'})
        client.put('/api/credentials', json={'sylvia_api_key': 'syl_test'})
        status = client.get('/api/status').get_json()
        assert status['rich_filters_supported'] is True
        assert status['oauth_available'] is False  # no Reddit app configured
