'use client';

interface SetupRequiredProps {
    onOpenSettings: () => void;
    onDismiss?: () => void;
}

export default function SetupRequired({ onOpenSettings, onDismiss }: SetupRequiredProps) {
    return (
        <div className="min-h-screen flex items-center justify-center p-4">
            <div className="bg-[#16213e] rounded-2xl p-8 max-w-md w-full text-center shadow-2xl relative">
                {onDismiss && (
                    <button
                        onClick={onDismiss}
                        className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full bg-white/10 hover:bg-white/20 text-white/60 hover:text-white transition-colors"
                        aria-label="Dismiss"
                    >
                        ✕
                    </button>
                )}
                <div className="text-6xl mb-4">🔧</div>
                <h1 className="text-2xl font-bold text-white mb-2">Setup Required</h1>
                <p className="text-white/70 mb-6">
                    Before you can use Reddit Monitor, you need to configure your Reddit API and Pushover credentials.
                </p>

                <div className="bg-white/5 rounded-lg p-4 mb-6 text-left">
                    <h3 className="text-sm font-semibold text-white/80 mb-2">You'll need:</h3>
                    <ul className="text-sm text-white/60 space-y-1">
                        <li>• Reddit API credentials (Client ID & Secret)</li>
                        <li>• Reddit account (username & password)</li>
                        <li>• Pushover App Token & User Key</li>
                    </ul>
                </div>

                <a
                    href="https://www.reddit.com/prefs/apps"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-400 hover:text-blue-300 block mb-4"
                >
                    📖 Get Reddit API credentials →
                </a>

                <button
                    onClick={onOpenSettings}
                    className="btn-primary bg-green-500/30 hover:bg-green-500/50 w-full text-lg"
                >
                    ⚙️ Configure Settings
                </button>

                {onDismiss && (
                    <button
                        onClick={onDismiss}
                        className="mt-3 text-sm text-white/40 hover:text-white/60 transition-colors"
                    >
                        Skip for now →
                    </button>
                )}
            </div>
        </div>
    );
}
