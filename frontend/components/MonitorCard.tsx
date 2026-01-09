'use client';

import { Monitor } from '@/types/monitor';

interface MonitorCardProps {
    monitor: Monitor;
    onToggle: (id: string, enabled: boolean) => void;
    onClick: (monitor: Monitor) => void;
}

export default function MonitorCard({ monitor, onToggle, onClick }: MonitorCardProps) {
    const handleToggleClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        onToggle(monitor.id, !monitor.enabled);
    };

    return (
        <div
            className="monitor-card"
            style={{ backgroundColor: monitor.color }}
            onClick={() => onClick(monitor)}
        >
            <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-lg text-white truncate">
                    {monitor.name}
                </h3>
                <p className="text-white/80 text-sm truncate">
                    r/{monitor.subreddit}
                </p>
            </div>

            <div
                className={`toggle-switch ${monitor.enabled ? 'active' : ''}`}
                onClick={handleToggleClick}
                role="switch"
                aria-checked={monitor.enabled}
                aria-label={`${monitor.enabled ? 'Disable' : 'Enable'} ${monitor.name}`}
            />
        </div>
    );
}
