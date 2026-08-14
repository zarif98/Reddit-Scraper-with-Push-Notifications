'use client';

interface Props {
    urls: string[];
    newUrl: string;
    onNewUrlChange: (value: string) => void;
    onAdd: () => void;
    onRemove: (index: number) => void;
    onTest: () => void;
    testing: boolean;
    testSuccess: boolean | null;
}

// Get a friendly service name from an Apprise URL for display.
function getServiceName(url: string) {
    if (url.startsWith('discord://')) return '📱 Discord';
    if (url.startsWith('slack://')) return '💬 Slack';
    if (url.startsWith('tgram://')) return '✈️ Telegram';
    if (url.startsWith('pover://')) return '📲 Pushover';
    if (url.startsWith('ntfy://')) return '🔔 ntfy';
    if (url.startsWith('mailto://')) return '📧 Email';
    if (url.startsWith('msteams://')) return '👥 Teams';
    if (url.includes('://')) return url.split('://')[0];
    return 'Custom';
}

export default function NotificationSection({
    urls, newUrl, onNewUrlChange, onAdd, onRemove, onTest, testing, testSuccess,
}: Props) {
    return (
        <div>
            <h3 className="text-sm font-semibold text-white/80 mb-3 flex items-center gap-2">
                🔔 Notification Services
            </h3>

            {/* Existing URLs */}
            <div className="space-y-2 mb-3">
                {urls.map((url, index) => (
                    <div key={index} className="flex items-center gap-2 bg-white/5 rounded-lg p-2">
                        <span className="text-sm text-white flex-1 truncate">
                            {getServiceName(url)}
                        </span>
                        <code className="text-xs text-white/40 flex-1 truncate">
                            {url.length > 25 ? url.substring(0, 25) + '...' : url}
                        </code>
                        <button
                            type="button"
                            onClick={() => onRemove(index)}
                            className="text-red-400 hover:text-red-300 p-1"
                        >
                            🗑️
                        </button>
                    </div>
                ))}
                {urls.length === 0 && (
                    <p className="text-sm text-white/40 italic">No notification services configured</p>
                )}
            </div>

            {/* Add new URL */}
            <div className="flex gap-2 mb-3">
                <input
                    type="text"
                    value={newUrl}
                    onChange={(e) => onNewUrlChange(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), onAdd())}
                    placeholder="discord://webhook_id/token"
                    className="input-field text-sm flex-1"
                />
                <button
                    type="button"
                    onClick={onAdd}
                    className="px-3 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-white"
                >
                    +
                </button>
            </div>

            {/* Test button */}
            {urls.length > 0 && (
                <button
                    type="button"
                    onClick={onTest}
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
    );
}
