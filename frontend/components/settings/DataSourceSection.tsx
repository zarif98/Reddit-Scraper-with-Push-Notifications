'use client';

import type { Credentials, DataSource } from './types';

interface Props {
    credentials: Credentials;
    dataSource: DataSource;
    onDataSourceChange: (source: DataSource) => void;
    onChange: (field: keyof Credentials, value: string) => void;
}

export default function DataSourceSection({ credentials, dataSource, onDataSourceChange, onChange }: Props) {
    return (
        <div>
            <h3 className="text-sm font-semibold text-white/80 mb-3 flex items-center gap-2">
                📡 Data Source
            </h3>
            <div className="space-y-3">
                <div>
                    <label className="text-xs text-white/60 block mb-1">Fetch posts using</label>
                    <select
                        value={dataSource}
                        onChange={(e) => onDataSourceChange(e.target.value as DataSource)}
                        className="input-field text-sm"
                    >
                        <option value="reddit">🤖 Reddit API</option>
                        <option value="sylvia">🛰️ Sylvia Gateway</option>
                    </select>
                    <p className="text-xs text-white/40 mt-1">
                        {dataSource === 'reddit'
                            ? 'Official Reddit API. Falls back to the free RSS/JSON feeds if unavailable.'
                            : 'Third-party gateway that fetches from its own IP. Falls back to the free RSS/JSON feeds if unavailable.'}
                    </p>
                </div>

                {dataSource === 'reddit' ? (
                    <>
                        <div>
                            <label className="text-xs text-white/60 block mb-1">Client ID</label>
                            <input
                                type="text"
                                value={credentials.reddit_client_id}
                                onChange={(e) => onChange('reddit_client_id', e.target.value)}
                                placeholder="Enter Client ID"
                                className="input-field text-sm"
                            />
                        </div>
                        <div>
                            <label className="text-xs text-white/60 block mb-1">Client Secret</label>
                            <input
                                type="password"
                                value={credentials.reddit_client_secret}
                                onChange={(e) => onChange('reddit_client_secret', e.target.value)}
                                placeholder="Enter Client Secret"
                                className="input-field text-sm"
                            />
                        </div>
                        <div>
                            <label className="text-xs text-white/60 block mb-1">Username</label>
                            <input
                                type="text"
                                value={credentials.reddit_username}
                                onChange={(e) => onChange('reddit_username', e.target.value)}
                                placeholder="Your Reddit username"
                                className="input-field text-sm"
                            />
                        </div>
                        <div>
                            <label className="text-xs text-white/60 block mb-1">Password</label>
                            <input
                                type="password"
                                value={credentials.reddit_password}
                                onChange={(e) => onChange('reddit_password', e.target.value)}
                                placeholder="Your Reddit password"
                                className="input-field text-sm"
                            />
                        </div>
                        <div>
                            <label className="text-xs text-white/60 block mb-1">User Agent</label>
                            <input
                                type="text"
                                value={credentials.reddit_user_agent}
                                onChange={(e) => onChange('reddit_user_agent', e.target.value)}
                                placeholder="e.g. RedditMonitor by u/username"
                                className="input-field text-sm"
                            />
                        </div>
                    </>
                ) : (
                    <div>
                        <label className="text-xs text-white/60 block mb-1">API Key</label>
                        <input
                            type="password"
                            value={credentials.sylvia_api_key}
                            onChange={(e) => onChange('sylvia_api_key', e.target.value)}
                            placeholder="syl_..."
                            className="input-field text-sm"
                        />
                    </div>
                )}
            </div>
        </div>
    );
}
