'use client';

import { useState, useEffect } from 'react';
import MonitorCard from '@/components/MonitorCard';
import MonitorModal from '@/components/MonitorModal';
import SettingsModal from '@/components/SettingsModal';
import SetupRequired from '@/components/SetupRequired';
import { Monitor } from '@/types/monitor';
import { getApiUrl } from '@/lib/api';

export default function Home() {
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedMonitor, setSelectedMonitor] = useState<Monitor | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isConfigured, setIsConfigured] = useState<boolean | null>(null);

  const checkCredentials = async () => {
    try {
      const response = await fetch(`${getApiUrl()}/api/credentials/status`);
      const data = await response.json();
      setIsConfigured(data.configured);
    } catch (err) {
      // If API is down, assume configured (use env vars)
      setIsConfigured(true);
    }
  };

  const fetchMonitors = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${getApiUrl()}/api/monitors`);
      if (!response.ok) throw new Error('Failed to fetch monitors');
      const data = await response.json();
      setMonitors(data.monitors || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load monitors');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkCredentials();
    fetchMonitors();
  }, []);

  const handleToggle = async (id: string, enabled: boolean) => {
    try {
      const response = await fetch(`${getApiUrl()}/api/monitors/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      if (!response.ok) throw new Error('Failed to update monitor');

      setMonitors(monitors.map(m =>
        m.id === id ? { ...m, enabled } : m
      ));
    } catch (err) {
      console.error('Toggle error:', err);
    }
  };

  const handleSelectMonitor = (monitor: Monitor) => {
    setSelectedMonitor(monitor);
    setIsCreating(false);
    setIsModalOpen(true);
  };

  const handleCreateNew = () => {
    setSelectedMonitor(null);
    setIsCreating(true);
    setIsModalOpen(true);
  };

  const handleSave = async (monitor: Partial<Monitor>) => {
    try {
      if (isCreating) {
        const response = await fetch(`${getApiUrl()}/api/monitors`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(monitor),
        });
        if (!response.ok) throw new Error('Failed to create monitor');
      } else if (selectedMonitor) {
        const response = await fetch(`${getApiUrl()}/api/monitors/${selectedMonitor.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(monitor),
        });
        if (!response.ok) throw new Error('Failed to update monitor');
      }

      setIsModalOpen(false);
      fetchMonitors();
    } catch (err) {
      console.error('Save error:', err);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const response = await fetch(`${getApiUrl()}/api/monitors/${id}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to delete monitor');

      setIsModalOpen(false);
      fetchMonitors();
    } catch (err) {
      console.error('Delete error:', err);
    }
  };

  const handleSettingsSave = () => {
    checkCredentials();
    fetchMonitors();
    setShowSetupScreen(false);
  };

  const [showSetupScreen, setShowSetupScreen] = useState(true);

  // Show setup screen if not configured and not dismissed
  if (isConfigured === false && showSetupScreen) {
    return (
      <>
        <SetupRequired
          onOpenSettings={() => setIsSettingsOpen(true)}
          onDismiss={() => setShowSetupScreen(false)}
        />
        {isSettingsOpen && (
          <SettingsModal
            onClose={() => setIsSettingsOpen(false)}
            onSave={handleSettingsSave}
          />
        )}
      </>
    );
  }

  return (
    <main className="min-h-screen pb-20">
      {/* Header */}
      <header className="sticky top-0 z-50 backdrop-blur-md bg-[#1a1a2e]/90 border-b border-white/10">
        <div className="max-w-lg mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold">Monitors</h1>
          <div className="flex gap-2">
            <button
              className="btn-icon"
              onClick={() => setIsSettingsOpen(true)}
              aria-label="Settings"
              title="Settings"
            >
              ⚙️
            </button>
            <button
              className="add-btn"
              onClick={handleCreateNew}
              aria-label="Add new monitor"
            >
              +
            </button>
          </div>
        </div>
      </header>

      {/* Warning Banner - when credentials not configured */}
      {isConfigured === false && (
        <div className="bg-yellow-500/20 border-b border-yellow-500/30">
          <div className="max-w-lg mx-auto px-4 py-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-yellow-200 text-sm">
              <span>⚠️</span>
              <span>Bot won't work without credentials configured</span>
            </div>
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="text-xs bg-yellow-500/30 hover:bg-yellow-500/50 px-3 py-1 rounded-full text-yellow-100 whitespace-nowrap"
            >
              Configure
            </button>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="max-w-lg mx-auto px-4 py-6">
        {loading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="skeleton h-20 w-full" />
            ))}
          </div>
        ) : error ? (
          <div className="bg-red-500/20 text-red-300 p-4 rounded-lg text-center">
            <p>{error}</p>
            <button
              className="mt-2 underline"
              onClick={fetchMonitors}
            >
              Try again
            </button>
          </div>
        ) : monitors.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📡</div>
            <h2 className="text-xl font-semibold mb-2">No Monitors Yet</h2>
            <p className="text-sm mb-4">Create your first Reddit monitor to get started</p>
            <button
              className="btn-primary mx-auto"
              onClick={handleCreateNew}
            >
              + Add Monitor
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {monitors.map((monitor, index) => (
              <div
                key={monitor.id}
                className="animate-slide-in"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <MonitorCard
                  monitor={monitor}
                  onToggle={handleToggle}
                  onClick={handleSelectMonitor}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Monitor Modal */}
      {isModalOpen && (
        <MonitorModal
          monitor={selectedMonitor}
          isCreating={isCreating}
          onClose={() => setIsModalOpen(false)}
          onSave={handleSave}
          onDelete={handleDelete}
        />
      )}

      {/* Settings Modal */}
      {isSettingsOpen && (
        <SettingsModal
          onClose={() => setIsSettingsOpen(false)}
          onSave={handleSettingsSave}
        />
      )}
    </main>
  );
}
