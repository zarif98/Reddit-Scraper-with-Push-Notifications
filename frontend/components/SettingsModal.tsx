'use client';

import { useState, useEffect } from 'react';
import { getApiUrl } from '@/lib/api';
import { Credentials, DEFAULT_CREDENTIALS, DataSource } from './settings/types';
import DataSourceSection from './settings/DataSourceSection';
import NotificationSection from './settings/NotificationSection';

interface SettingsModalProps {
    onClose: () => void;
    onSave: () => void;
}

export default function SettingsModal({ onClose, onSave }: SettingsModalProps) {
    const [credentials, setCredentials] = useState<Credentials>(DEFAULT_CREDENTIALS);
    const [dataSource, setDataSource] = useState<DataSource>('reddit');
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
            const [credRes, orderRes] = await Promise.all([
                fetch(`${getApiUrl()}/api/credentials`),
                fetch(`${getApiUrl()}/api/source-order`),
            ]);
            const data = await credRes.json();
            setCredentials({
                ...DEFAULT_CREDENTIALS,
                ...data,
                notification_urls: data.notification_urls || [],
            });
            const order = await orderRes.json();
            if (order.active_source === 'sylvia') setDataSource('sylvia');
        } catch (err) {
            console.error('Failed to fetch settings:', err);
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
            // Persist the selected data source (writes the bot's source order).
            await fetch(`${getApiUrl()}/api/source-order`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ active_source: dataSource }),
            });

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
                            <p className="text-sm text-white/60 mt-1">Choose your data source & notifications</p>
                        </div>

                        {loading ? (
                            <div className="p-8 text-center">
                                <div className="animate-spin w-8 h-8 border-2 border-white/30 border-t-white rounded-full mx-auto"></div>
                            </div>
                        ) : (
                            <div className="p-4 space-y-6">
                                <DataSourceSection
                                    credentials={credentials}
                                    dataSource={dataSource}
                                    onDataSourceChange={(s) => { setDataSource(s); setError(null); setSuccess(false); }}
                                    onChange={handleChange}
                                />

                                <NotificationSection
                                    urls={credentials.notification_urls}
                                    newUrl={newUrl}
                                    onNewUrlChange={setNewUrl}
                                    onAdd={addNotificationUrl}
                                    onRemove={removeNotificationUrl}
                                    onTest={testNotifications}
                                    testing={testing}
                                    testSuccess={testSuccess}
                                />
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
