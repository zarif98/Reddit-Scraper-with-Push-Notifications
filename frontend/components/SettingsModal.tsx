'use client';

import { useState, useEffect } from 'react';
import { getApiUrl } from '@/lib/api';

interface SettingsModalProps {
    onClose: () => void;
    onSave: () => void;
}

interface Credentials {
    reddit_client_id: string;
    reddit_client_secret: string;
    reddit_username: string;
    reddit_password: string;
    reddit_user_agent: string;
    notification_urls: string[];
}

const DEFAULT_CREDENTIALS: Credentials = {
    reddit_client_id: '',
    reddit_client_secret: '',
    reddit_username: '',
    reddit_password: '',
    reddit_user_agent: '',
    notification_urls: [],
};

export default function SettingsModal({ onClose, onSave }: SettingsModalProps) {
    const [credentials, setCredentials] = useState<Credentials>(DEFAULT_CREDENTIALS);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);
    const [testSuccess, setTestSuccess] = useState<boolean | null>(null);
    const [newUrl, setNewUrl] = useState('');

    useEffect(() => {
        fetchCredentials();
    }, []);

    const fetchCredentials = async () => {
        try {
            const response = await fetch(`${getApiUrl()}/api/credentials`);
            const data = await response.json();
            setCredentials({
                ...DEFAULT_CREDENTIALS,
                ...data,
                notification_urls: data.notification_urls || [],
            });
        } catch (err) {
            console.error('Failed to fetch credentials:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleChange = (field: keyof Credentials, value: string) => {
        setCredentials(prev => ({ ...prev, [field]: value }));
        setError(null);
        setSuccess(false);
    };

    const addNotificationUrl = () => {
        if (newUrl.trim()) {
            setCredentials(prev => ({
                ...prev,
                notification_urls: [...prev.notification_urls, newUrl.trim()],
            }));
            setNewUrl('');
            setError(null);
        }
    };

    const removeNotificationUrl = (index: number) => {
        setCredentials(prev => ({
            ...prev,
            notification_urls: prev.notification_urls.filter((_, i) => i !== index),
        }));
    };

    const testNotifications = async () => {
        setTesting(true);
        setTestSuccess(null);
        try {
            const response = await fetch(`${getApiUrl()}/api/notifications/test`, {
                method: 'POST',
            });
            const data = await response.json();
            setTestSuccess(data.success);
            if (!data.success && data.error) {
                setError(data.error);
            }
        } catch (err) {
            setTestSuccess(false);
            setError('Failed to send test notification');
        } finally {
            setTesting(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setSaving(true);

        try {
            const response = await fetch(`${getApiUrl()}/api/credentials`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(credentials),
            });

            const data = await response.json();

            if (data.success) {
                setSuccess(true);
                setTimeout(() => {
                    onSave();
                    onClose();
                }, 1000);
            } else {
                setError(data.error || 'Failed to save credentials');
            }
        } catch (err) {
            setError('Failed to save credentials');
        } finally {
            setSaving(false);
        }
    };

    // Get service name from URL for display
    const getServiceName = (url: string) => {
        if (url.startsWith('discord://')) return '📱 Discord';
        if (url.startsWith('slack://')) return '💬 Slack';
        if (url.startsWith('tgram://')) return '✈️ Telegram';
        if (url.startsWith('pover://')) return '📲 Pushover';
        if (url.startsWith('ntfy://')) return '🔔 ntfy';
        if (url.startsWith('mailto://')) return '📧 Email';
        if (url.startsWith('msteams://')) return '👥 Teams';
        if (url.includes('://')) return url.split('://')[0];
        return 'Custom';
    };

    return (
        <div className="modal-overlay animate-fade-in" onClick={onClose}>
            <div
                className="modal-content animate-slide-in relative bg-[#16213e]"
                onClick={e => e.stopPropagation()}
                style={{ maxWidth: '500px' }}
            >
                <form onSubmit={handleSubmit}>
                    <div className="modal-scrollable">
                        {/* Header */}
                        <div className="p-4 pb-2 border-b border-white/10">
                            <button
                                type="button"
                                onClick={onClose}
                                className="absolute top-2 right-2 w-8 h-8 flex items-center justify-center rounded-full bg-black/20 hover:bg-black/40 text-white/70 hover:text-white transition-colors z-10"
                            >
                                ✕
                            </button>
                            <h2 className="text-xl font-semibold text-white">⚙️ Settings</h2>
                            <p className="text-sm text-white/60 mt-1">Configure Reddit & notification services</p>
                        </div>

                        {loading ? (
                            <div className="p-8 text-center">
                                <div className="animate-spin w-8 h-8 border-2 border-white/30 border-t-white rounded-full mx-auto"></div>
                            </div>
                        ) : (
                            <div className="p-4 space-y-6">
                                {/* Reddit Section */}
                                <div>
                                    <h3 className="text-sm font-semibold text-white/80 mb-3 flex items-center gap-2">
                                        🤖 Reddit API
                                    </h3>
                                    <div className="space-y-3">
                                        <div>
                                            <label className="text-xs text-white/60 block mb-1">Client ID</label>
                                            <input
                                                type="text"
                                                value={credentials.reddit_client_id}
                                                onChange={(e) => handleChange('reddit_client_id', e.target.value)}
                                                placeholder="Enter Client ID"
                                                className="input-field text-sm"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs text-white/60 block mb-1">Client Secret</label>
                                            <input
                                                type="password"
                                                value={credentials.reddit_client_secret}
                                                onChange={(e) => handleChange('reddit_client_secret', e.target.value)}
                                                placeholder="Enter Client Secret"
                                                className="input-field text-sm"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs text-white/60 block mb-1">Username</label>
                                            <input
                                                type="text"
                                                value={credentials.reddit_username}
                                                onChange={(e) => handleChange('reddit_username', e.target.value)}
                                                placeholder="Your Reddit username"
                                                className="input-field text-sm"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs text-white/60 block mb-1">Password</label>
                                            <input
                                                type="password"
                                                value={credentials.reddit_password}
                                                onChange={(e) => handleChange('reddit_password', e.target.value)}
                                                placeholder="Your Reddit password"
                                                className="input-field text-sm"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs text-white/60 block mb-1">User Agent</label>
                                            <input
                                                type="text"
                                                value={credentials.reddit_user_agent}
                                                onChange={(e) => handleChange('reddit_user_agent', e.target.value)}
                                                placeholder="e.g. RedditMonitor by u/username"
                                                className="input-field text-sm"
                                            />
                                        </div>
                                    </div>
                                </div>

                                {/* Notification Services Section */}
                                <div>
                                    <h3 className="text-sm font-semibold text-white/80 mb-3 flex items-center gap-2">
                                        🔔 Notification Services
                                    </h3>

                                    {/* Existing URLs */}
                                    <div className="space-y-2 mb-3">
                                        {credentials.notification_urls.map((url, index) => (
                                            <div key={index} className="flex items-center gap-2 bg-white/5 rounded-lg p-2">
                                                <span className="text-sm text-white flex-1 truncate">
                                                    {getServiceName(url)}
                                                </span>
                                                <code className="text-xs text-white/40 flex-1 truncate">
                                                    {url.length > 25 ? url.substring(0, 25) + '...' : url}
                                                </code>
                                                <button
                                                    type="button"
                                                    onClick={() => removeNotificationUrl(index)}
                                                    className="text-red-400 hover:text-red-300 p-1"
                                                >
                                                    🗑️
                                                </button>
                                            </div>
                                        ))}
                                        {credentials.notification_urls.length === 0 && (
                                            <p className="text-sm text-white/40 italic">No notification services configured</p>
                                        )}
                                    </div>

                                    {/* Add new URL */}
                                    <div className="flex gap-2 mb-3">
                                        <input
                                            type="text"
                                            value={newUrl}
                                            onChange={(e) => setNewUrl(e.target.value)}
                                            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addNotificationUrl())}
                                            placeholder="discord://webhook_id/token"
                                            className="input-field text-sm flex-1"
                                        />
                                        <button
                                            type="button"
                                            onClick={addNotificationUrl}
                                            className="px-3 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-white"
                                        >
                                            +
                                        </button>
                                    </div>

                                    {/* Test button */}
                                    {credentials.notification_urls.length > 0 && (
                                        <button
                                            type="button"
                                            onClick={testNotifications}
                                            disabled={testing}
                                            className="w-full py-2 bg-blue-500/20 hover:bg-blue-500/30 text-blue-300 rounded-lg text-sm transition-colors mb-3"
                                        >
                                            {testing ? '⏳ Testing...' : '🧪 Test Notifications'}
                                        </button>
                                    )}
                                    {testSuccess === true && (
                                        <p className="text-sm text-green-400">✅ Test notification sent!</p>
                                    )}
                                    {testSuccess === false && (
                                        <p className="text-sm text-red-400">❌ Test failed</p>
                                    )}

                                    {/* Help text */}
                                    <div className="bg-white/5 rounded-lg p-3 text-xs text-white/50">
                                        <p className="font-semibold mb-1">Supported services:</p>
                                        <ul className="space-y-0.5">
                                            <li>• Discord: <code>discord://webhook_id/token</code></li>
                                            <li>• Slack: <code>slack://token/channel</code></li>
                                            <li>• Telegram: <code>tgram://bot_token/chat_id</code></li>
                                            <li>• Pushover: <code>pover://user_key@app_token</code></li>
                                            <li>• ntfy: <code>ntfy://topic</code></li>
                                        </ul>
                                        <a
                                            href="https://github.com/caronc/apprise"
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-blue-400 hover:underline mt-2 block"
                                        >
                                            See all 80+ services →
                                        </a>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Error/Success Messages */}
                    {error && (
                        <div className="mx-4 mb-2 p-3 bg-red-500/30 border border-red-500/50 rounded-lg text-white text-sm">
                            ⚠️ {error}
                        </div>
                    )}
                    {success && (
                        <div className="mx-4 mb-2 p-3 bg-green-500/30 border border-green-500/50 rounded-lg text-white text-sm">
                            ✅ Settings saved successfully!
                        </div>
                    )}

                    {/* Footer */}
                    <div className="modal-footer p-4 flex gap-3 border-t border-white/10">
                        <button
                            type="button"
                            onClick={onClose}
                            className="btn-primary bg-white/10 hover:bg-white/20 flex-1"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="btn-primary bg-green-500/30 hover:bg-green-500/50 flex-1"
                            disabled={saving}
                        >
                            {saving ? '⏳ Saving...' : '✓ Save'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
