"""Tests for credential validation in api.py."""
import pytest
from unittest.mock import patch


class TestCredentialValidation:
    """Tests for credential validation."""
    
    def test_non_ascii_detection(self):
        """Test that non-ASCII characters are detected in credentials."""
        from api import validate_reddit_credentials
        
        # Cyrillic 'І' looks like Latin 'I' but has different code point
        success, error = validate_reddit_credentials(
            client_id='test123',
            client_secret='IaYQJWІRqNCg',  # Contains Cyrillic І at position 6
            username='testuser',
            password='testpass',
            user_agent='TestAgent/1.0'
        )
        
        assert success is False
        assert 'Non-ASCII' in error or 'non-ASCII' in error.lower()
        assert 'client_secret' in error
    
    def test_empty_credentials_fail(self):
        """Test that empty credentials fail validation."""
        from api import validate_reddit_credentials
        
        success, error = validate_reddit_credentials(
            client_id='',
            client_secret='testsecret',
            username='testuser',
            password='testpass',
            user_agent='TestAgent/1.0'
        )
        
        assert success is False
    
    def test_ascii_credentials_try_oauth(self):
        """Test that pure ASCII credentials attempt OAuth validation."""
        from api import validate_reddit_credentials
        
        with patch('api.requests.post') as mock_post:
            # Simulate OAuth failure (which is expected for fake creds)
            mock_post.return_value.status_code = 401
            mock_post.return_value.json.return_value = {'error': 'invalid_grant'}
            
            success, error = validate_reddit_credentials(
                client_id='validascii123',
                client_secret='validascii456',
                username='testuser',
                password='testpass',
                user_agent='TestAgent/1.0'
            )
            
            # Should fail due to OAuth, not ASCII check
            assert 'Non-ASCII' not in (error or '')
            # OAuth attempt was made
            mock_post.assert_called_once()
