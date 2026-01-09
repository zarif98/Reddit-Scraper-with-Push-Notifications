'use client';

import { useState, useEffect } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001';

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
    pushover_app_token: string;
    pushover_user_key: string;
}

const DEFAULT_CREDENTIALS: Credentials = {
    reddit_client_id: '',
    reddit_client_secret: '',
    reddit_username: '',
    reddit_password: '',
    reddit_user_agent: '',
    pushover_app_token: '',
    pushover_user_key: '',
};

export default function SettingsModal({ onClose, onSave }: SettingsModalProps) {
    const [credentials, setCredentials] = useState<Credentials>(DEFAULT_CREDENTIALS);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    useEffect(() => {
        fetchCredentials();
    }, []);

    const fetchCredentials = async () => {
        try {
            const response = await fetch(`${API_URL}/api/credentials`);
            const data = await response.json();
            setCredentials(data);
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

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setSaving(true);

        try {
            const response = await fetch(`${API_URL}/api/credentials`, {
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
                            <p className="text-sm text-white/60 mt-1">Configure Reddit & Pushover credentials</p>
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

                                {/* Pushover Section */}
                                <div>
                                    <h3 className="text-sm font-semibold text-white/80 mb-3 flex items-center gap-2">
                                        🔔 Pushover Notifications
                                    </h3>
                                    <div className="space-y-3">
                                        <div>
                                            <label className="text-xs text-white/60 block mb-1">App Token</label>
                                            <input
                                                type="password"
                                                value={credentials.pushover_app_token}
                                                onChange={(e) => handleChange('pushover_app_token', e.target.value)}
                                                placeholder="Enter Pushover App Token"
                                                className="input-field text-sm"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs text-white/60 block mb-1">User Key</label>
                                            <input
                                                type="password"
                                                value={credentials.pushover_user_key}
                                                onChange={(e) => handleChange('pushover_user_key', e.target.value)}
                                                placeholder="Enter Pushover User Key"
                                                className="input-field text-sm"
                                            />
                                        </div>
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
