'use client';

import { useState, useEffect, useRef } from 'react';
import { Monitor, DEFAULT_MONITOR, DEFAULT_COLORS } from '@/types/monitor';
import ColorPicker from './ColorPicker';
import { getApiUrl } from '@/lib/api';

interface SubredditSuggestion {
    name: string;
    title: string;
    subscribers: number;
    public_description: string;
}

interface MonitorModalProps {
    monitor: Monitor | null;
    isCreating: boolean;
    onClose: () => void;
    onSave: (monitor: Partial<Monitor>) => void;
    onDelete: (id: string) => void;
}

type TabType = 'filters' | 'alerts' | 'settings';

export default function MonitorModal({
    monitor,
    isCreating,
    onClose,
    onSave,
    onDelete
}: MonitorModalProps) {
    const [activeTab, setActiveTab] = useState<TabType>('filters');
    const [formData, setFormData] = useState<Partial<Monitor>>(DEFAULT_MONITOR);
    const [newKeyword, setNewKeyword] = useState('');
    const [newExcludeKeyword, setNewExcludeKeyword] = useState('');
    const [newDomainContains, setNewDomainContains] = useState('');
    const [newDomainExcludes, setNewDomainExcludes] = useState('');
    const [newFlairContains, setNewFlairContains] = useState('');
    const [newAuthorIncludes, setNewAuthorIncludes] = useState('');
    const [newAuthorExcludes, setNewAuthorExcludes] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [confirmDelete, setConfirmDelete] = useState(false);

    // Subreddit autocomplete state
    const [subredditQuery, setSubredditQuery] = useState('');
    const [suggestions, setSuggestions] = useState<SubredditSuggestion[]>([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const [isSearching, setIsSearching] = useState(false);
    const suggestionRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (monitor) {
            setFormData(monitor);
            setSubredditQuery(monitor.subreddit || '');
        } else {
            setFormData({
                ...DEFAULT_MONITOR,
                color: DEFAULT_COLORS[Math.floor(Math.random() * DEFAULT_COLORS.length)],
            });
            setSubredditQuery('');
        }
    }, [monitor]);

    // Debounced subreddit search
    useEffect(() => {
        if (!subredditQuery || subredditQuery.length < 2) {
            setSuggestions([]);
            return;
        }

        const timer = setTimeout(async () => {
            setIsSearching(true);
            try {
                const response = await fetch(`${getApiUrl()}/api/subreddits/search?q=${encodeURIComponent(subredditQuery)}`);
                const data = await response.json();
                setSuggestions(data.subreddits || []);
                setShowSuggestions(true);
            } catch (err) {
                console.error('Failed to search subreddits:', err);
                setSuggestions([]);
            } finally {
                setIsSearching(false);
            }
        }, 300);

        return () => clearTimeout(timer);
    }, [subredditQuery]);

    // Close suggestions when clicking outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (suggestionRef.current && !suggestionRef.current.contains(e.target as Node)) {
                setShowSuggestions(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const selectSubreddit = (name: string) => {
        setSubredditQuery(name);
        handleInputChange('subreddit', name);
        handleInputChange('name', `r/${name}`);
        setShowSuggestions(false);
        setSuggestions([]);
    };

    const handleInputChange = (field: keyof Monitor, value: unknown) => {
        setFormData(prev => ({ ...prev, [field]: value }));
    };

    const addKeyword = () => {
        if (newKeyword.trim()) {
            const keywords = [...(formData.keywords || []), newKeyword.trim().toLowerCase()];
            handleInputChange('keywords', keywords);
            setNewKeyword('');
        }
    };

    const removeKeyword = (index: number) => {
        const keywords = (formData.keywords || []).filter((_, i) => i !== index);
        handleInputChange('keywords', keywords);
    };

    const addExcludeKeyword = () => {
        if (newExcludeKeyword.trim()) {
            const keywords = [...(formData.exclude_keywords || []), newExcludeKeyword.trim().toLowerCase()];
            handleInputChange('exclude_keywords', keywords);
            setNewExcludeKeyword('');
        }
    };

    const removeExcludeKeyword = (index: number) => {
        const keywords = (formData.exclude_keywords || []).filter((_, i) => i !== index);
        handleInputChange('exclude_keywords', keywords);
    };

    // Domain filters
    const addDomainContains = () => {
        if (newDomainContains.trim()) {
            const domains = [...(formData.domain_contains || []), newDomainContains.trim().toLowerCase()];
            handleInputChange('domain_contains', domains);
            setNewDomainContains('');
        }
    };
    const removeDomainContains = (index: number) => {
        const domains = (formData.domain_contains || []).filter((_, i) => i !== index);
        handleInputChange('domain_contains', domains);
    };
    const addDomainExcludes = () => {
        if (newDomainExcludes.trim()) {
            const domains = [...(formData.domain_excludes || []), newDomainExcludes.trim().toLowerCase()];
            handleInputChange('domain_excludes', domains);
            setNewDomainExcludes('');
        }
    };
    const removeDomainExcludes = (index: number) => {
        const domains = (formData.domain_excludes || []).filter((_, i) => i !== index);
        handleInputChange('domain_excludes', domains);
    };

    // Flair filter
    const addFlairContains = () => {
        if (newFlairContains.trim()) {
            const flairs = [...(formData.flair_contains || []), newFlairContains.trim()];
            handleInputChange('flair_contains', flairs);
            setNewFlairContains('');
        }
    };
    const removeFlairContains = (index: number) => {
        const flairs = (formData.flair_contains || []).filter((_, i) => i !== index);
        handleInputChange('flair_contains', flairs);
    };

    // Author filters
    const addAuthorIncludes = () => {
        if (newAuthorIncludes.trim()) {
            const authors = [...(formData.author_includes || []), newAuthorIncludes.trim().toLowerCase()];
            handleInputChange('author_includes', authors);
            setNewAuthorIncludes('');
        }
    };
    const removeAuthorIncludes = (index: number) => {
        const authors = (formData.author_includes || []).filter((_, i) => i !== index);
        handleInputChange('author_includes', authors);
    };
    const addAuthorExcludes = () => {
        if (newAuthorExcludes.trim()) {
            const authors = [...(formData.author_excludes || []), newAuthorExcludes.trim().toLowerCase()];
            handleInputChange('author_excludes', authors);
            setNewAuthorExcludes('');
        }
    };
    const removeAuthorExcludes = (index: number) => {
        const authors = (formData.author_excludes || []).filter((_, i) => i !== index);
        handleInputChange('author_excludes', authors);
    };

    const [isSaving, setIsSaving] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        if (!formData.subreddit) {
            setError('Please enter a subreddit');
            return;
        }

        // Check that at least one positive filter is set
        const hasKeywords = (formData.keywords || []).length > 0;
        const hasDomainFilter = (formData.domain_contains || []).length > 0;
        const hasFlairFilter = (formData.flair_contains || []).length > 0;
        const hasAuthorFilter = (formData.author_includes || []).length > 0;

        if (!hasKeywords && !hasDomainFilter && !hasFlairFilter && !hasAuthorFilter) {
            setError('Please add at least one filter: Keywords, Domain, Flair, or Author');
            setActiveTab('filters');
            return;
        }

        // Validate subreddit exists
        setIsSaving(true);
        try {
            const response = await fetch(`${getApiUrl()}/api/subreddits/validate/${encodeURIComponent(formData.subreddit)}`);
            const data = await response.json();

            if (!data.valid) {
                setError(`Subreddit "r/${formData.subreddit}" doesn't exist. Please select from suggestions.`);
                setIsSaving(false);
                return;
            }
        } catch (err) {
            console.error('Failed to validate subreddit:', err);
            // On error, allow save (don't block on network issues)
        }
        setIsSaving(false);

        onSave(formData);
    };

    const handleKeyDown = (e: React.KeyboardEvent, action: () => void) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            action();
        }
    };

    const backgroundColor = formData.color || DEFAULT_COLORS[0];

    return (
        <div className="modal-overlay animate-fade-in" onClick={onClose}>
            <div
                className="modal-content animate-slide-in relative"
                onClick={e => e.stopPropagation()}
                style={{ backgroundColor }}
            >
                <form onSubmit={handleSubmit}>
                    {/* Scrollable Content */}
                    <div className="modal-scrollable">
                        {/* Header */}
                        <div className="p-4 pb-2">
                            {/* Close button for mobile */}
                            <button
                                type="button"
                                onClick={onClose}
                                className="absolute top-2 right-2 w-8 h-8 flex items-center justify-center rounded-full bg-black/20 hover:bg-black/40 text-white/70 hover:text-white transition-colors z-10"
                                aria-label="Close"
                            >
                                ✕
                            </button>
                            <div className="flex justify-between items-start mb-4 pr-8">
                                <div className="flex-1">
                                    <input
                                        type="text"
                                        value={formData.name || ''}
                                        onChange={(e) => handleInputChange('name', e.target.value)}
                                        placeholder="Monitor Name"
                                        className="input-field bg-transparent border-none text-xl font-semibold p-0 mb-2"
                                        style={{ background: 'transparent' }}
                                    />
                                    <div className="flex items-center gap-2 relative" ref={suggestionRef}>
                                        <span className="text-white/80">r/</span>
                                        <div className="relative flex-1">
                                            <input
                                                type="text"
                                                value={subredditQuery}
                                                onChange={(e) => {
                                                    const value = e.target.value.replace('r/', '');
                                                    setSubredditQuery(value);
                                                    handleInputChange('subreddit', value);
                                                }}
                                                onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                                                placeholder="subreddit"
                                                className="input-field bg-white/10 text-sm py-2 px-3 w-full"
                                                required
                                                autoComplete="off"
                                            />
                                            {isSearching && (
                                                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                                                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                                                </div>
                                            )}
                                            {showSuggestions && suggestions.length > 0 && (
                                                <div className="absolute top-full left-0 right-0 mt-1 bg-gray-800 rounded-lg shadow-xl z-50 max-h-48 overflow-y-auto border border-white/10">
                                                    {suggestions.map((sub, index) => (
                                                        <div
                                                            key={index}
                                                            className="px-3 py-2 hover:bg-white/10 cursor-pointer border-b border-white/5 last:border-0"
                                                            onClick={() => selectSubreddit(sub.name)}
                                                        >
                                                            <div className="font-medium text-white">r/{sub.name}</div>
                                                            <div className="text-xs text-white/60 truncate">{sub.title}</div>
                                                            <div className="text-xs text-white/40">{sub.subscribers?.toLocaleString()} members</div>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                                <div
                                    className={`toggle-switch ${formData.enabled ? 'active' : ''}`}
                                    onClick={() => handleInputChange('enabled', !formData.enabled)}
                                    role="switch"
                                    aria-checked={formData.enabled}
                                />
                            </div>

                            {/* Color Picker */}
                            <ColorPicker
                                selectedColor={formData.color || DEFAULT_COLORS[0]}
                                onChange={(color) => handleInputChange('color', color)}
                            />
                        </div>

                        {/* Tabs */}
                        <div className="tabs mt-4">
                            <button
                                type="button"
                                className={`tab ${activeTab === 'filters' ? 'active' : ''}`}
                                onClick={() => setActiveTab('filters')}
                            >
                                Filters
                            </button>
                            <button
                                type="button"
                                className={`tab ${activeTab === 'alerts' ? 'active' : ''}`}
                                onClick={() => setActiveTab('alerts')}
                            >
                                Alerts
                            </button>
                            <button
                                type="button"
                                className={`tab ${activeTab === 'settings' ? 'active' : ''}`}
                                onClick={() => setActiveTab('settings')}
                            >
                                Settings
                            </button>
                        </div>

                        {/* Tab Content */}
                        <div className="p-4" style={{ backgroundColor: 'rgba(0,0,0,0.2)' }}>
                            {activeTab === 'filters' && (
                                <div className="space-y-4">
                                    {/* Include Keywords */}
                                    <div>
                                        <label className="text-sm text-white/70 mb-2 block">Title Contains (all required)</label>
                                        <div className="flex flex-wrap gap-2 mb-2">
                                            {(formData.keywords || []).map((keyword, index) => (
                                                <span key={index} className="filter-chip">
                                                    🔍 {keyword}
                                                    <button
                                                        type="button"
                                                        onClick={() => removeKeyword(index)}
                                                        className="ml-1 text-white/60 hover:text-white"
                                                    >
                                                        ×
                                                    </button>
                                                </span>
                                            ))}
                                        </div>
                                        <div className="flex gap-2">
                                            <input
                                                type="text"
                                                value={newKeyword}
                                                onChange={(e) => setNewKeyword(e.target.value)}
                                                onKeyDown={(e) => handleKeyDown(e, addKeyword)}
                                                placeholder="Add keyword..."
                                                className="input-field flex-1"
                                            />
                                            <button
                                                type="button"
                                                onClick={addKeyword}
                                                className="btn-icon"
                                            >
                                                +
                                            </button>
                                        </div>
                                    </div>

                                    {/* Exclude Keywords */}
                                    <div>
                                        <label className="text-sm text-white/70 mb-2 block">Title Excludes</label>
                                        <div className="flex flex-wrap gap-2 mb-2">
                                            {(formData.exclude_keywords || []).map((keyword, index) => (
                                                <span key={index} className="filter-chip exclude">
                                                    🚫 {keyword}
                                                    <button
                                                        type="button"
                                                        onClick={() => removeExcludeKeyword(index)}
                                                        className="ml-1 text-white/60 hover:text-white"
                                                    >
                                                        ×
                                                    </button>
                                                </span>
                                            ))}
                                        </div>
                                        <div className="flex gap-2">
                                            <input
                                                type="text"
                                                value={newExcludeKeyword}
                                                onChange={(e) => setNewExcludeKeyword(e.target.value)}
                                                onKeyDown={(e) => handleKeyDown(e, addExcludeKeyword)}
                                                placeholder="Add exclusion..."
                                                className="input-field flex-1"
                                            />
                                            <button
                                                type="button"
                                                onClick={addExcludeKeyword}
                                                className="btn-icon"
                                            >
                                                +
                                            </button>
                                        </div>
                                    </div>

                                    {/* Min Upvotes */}
                                    <div>
                                        <label className="text-sm text-white/70 mb-2 block">Minimum Upvotes</label>
                                        <input
                                            type="number"
                                            value={formData.min_upvotes || ''}
                                            onChange={(e) => handleInputChange('min_upvotes', e.target.value ? parseInt(e.target.value) : null)}
                                            placeholder="Any"
                                            className="input-field w-32"
                                            min="0"
                                        />
                                    </div>

                                    {/* Domain Contains */}
                                    <div>
                                        <label className="text-sm text-white/70 mb-2 block">🌐 Domain Contains</label>
                                        <div className="flex flex-wrap gap-2 mb-2">
                                            {(formData.domain_contains || []).map((domain, index) => (
                                                <span key={index} className="filter-chip">
                                                    🔗 {domain}
                                                    <button
                                                        type="button"
                                                        onClick={() => removeDomainContains(index)}
                                                        className="ml-1 text-white/60 hover:text-white"
                                                    >
                                                        ×
                                                    </button>
                                                </span>
                                            ))}
                                        </div>
                                        <div className="flex gap-2">
                                            <input
                                                type="text"
                                                value={newDomainContains}
                                                onChange={(e) => setNewDomainContains(e.target.value)}
                                                onKeyDown={(e) => handleKeyDown(e, addDomainContains)}
                                                placeholder="e.g. amazon.com"
                                                className="input-field flex-1"
                                            />
                                            <button
                                                type="button"
                                                onClick={addDomainContains}
                                                className="btn-icon"
                                            >
                                                +
                                            </button>
                                        </div>
                                    </div>

                                    {/* Domain Excludes */}
                                    <div>
                                        <label className="text-sm text-white/70 mb-2 block">🚫 Domain Excludes</label>
                                        <div className="flex flex-wrap gap-2 mb-2">
                                            {(formData.domain_excludes || []).map((domain, index) => (
                                                <span key={index} className="filter-chip exclude">
                                                    🔗 {domain}
                                                    <button
                                                        type="button"
                                                        onClick={() => removeDomainExcludes(index)}
                                                        className="ml-1 text-white/60 hover:text-white"
                                                    >
                                                        ×
                                                    </button>
                                                </span>
                                            ))}
                                        </div>
                                        <div className="flex gap-2">
                                            <input
                                                type="text"
                                                value={newDomainExcludes}
                                                onChange={(e) => setNewDomainExcludes(e.target.value)}
                                                onKeyDown={(e) => handleKeyDown(e, addDomainExcludes)}
                                                placeholder="Exclude domain..."
                                                className="input-field flex-1"
                                            />
                                            <button
                                                type="button"
                                                onClick={addDomainExcludes}
                                                className="btn-icon"
                                            >
                                                +
                                            </button>
                                        </div>
                                    </div>

                                    {/* Flair Contains */}
                                    <div>
                                        <label className="text-sm text-white/70 mb-2 block">🏷️ Flair Contains</label>
                                        <div className="flex flex-wrap gap-2 mb-2">
                                            {(formData.flair_contains || []).map((flair, index) => (
                                                <span key={index} className="filter-chip">
                                                    🏷️ {flair}
                                                    <button
                                                        type="button"
                                                        onClick={() => removeFlairContains(index)}
                                                        className="ml-1 text-white/60 hover:text-white"
                                                    >
                                                        ×
                                                    </button>
                                                </span>
                                            ))}
                                        </div>
                                        <div className="flex gap-2">
                                            <input
                                                type="text"
                                                value={newFlairContains}
                                                onChange={(e) => setNewFlairContains(e.target.value)}
                                                onKeyDown={(e) => handleKeyDown(e, addFlairContains)}
                                                placeholder="e.g. Sale, Deal"
                                                className="input-field flex-1"
                                            />
                                            <button
                                                type="button"
                                                onClick={addFlairContains}
                                                className="btn-icon"
                                            >
                                                +
                                            </button>
                                        </div>
                                    </div>

                                    {/* Author Includes */}
                                    <div>
                                        <label className="text-sm text-white/70 mb-2 block">👤 Only from Authors</label>
                                        <div className="flex flex-wrap gap-2 mb-2">
                                            {(formData.author_includes || []).map((author, index) => (
                                                <span key={index} className="filter-chip">
                                                    👤 {author}
                                                    <button
                                                        type="button"
                                                        onClick={() => removeAuthorIncludes(index)}
                                                        className="ml-1 text-white/60 hover:text-white"
                                                    >
                                                        ×
                                                    </button>
                                                </span>
                                            ))}
                                        </div>
                                        <div className="flex gap-2">
                                            <input
                                                type="text"
                                                value={newAuthorIncludes}
                                                onChange={(e) => setNewAuthorIncludes(e.target.value)}
                                                onKeyDown={(e) => handleKeyDown(e, addAuthorIncludes)}
                                                placeholder="Username..."
                                                className="input-field flex-1"
                                            />
                                            <button
                                                type="button"
                                                onClick={addAuthorIncludes}
                                                className="btn-icon"
                                            >
                                                +
                                            </button>
                                        </div>
                                    </div>

                                    {/* Author Excludes */}
                                    <div>
                                        <label className="text-sm text-white/70 mb-2 block">🚫 Exclude Authors</label>
                                        <div className="flex flex-wrap gap-2 mb-2">
                                            {(formData.author_excludes || []).map((author, index) => (
                                                <span key={index} className="filter-chip exclude">
                                                    👤 {author}
                                                    <button
                                                        type="button"
                                                        onClick={() => removeAuthorExcludes(index)}
                                                        className="ml-1 text-white/60 hover:text-white"
                                                    >
                                                        ×
                                                    </button>
                                                </span>
                                            ))}
                                        </div>
                                        <div className="flex gap-2">
                                            <input
                                                type="text"
                                                value={newAuthorExcludes}
                                                onChange={(e) => setNewAuthorExcludes(e.target.value)}
                                                onKeyDown={(e) => handleKeyDown(e, addAuthorExcludes)}
                                                placeholder="Username to exclude..."
                                                className="input-field flex-1"
                                            />
                                            <button
                                                type="button"
                                                onClick={addAuthorExcludes}
                                                className="btn-icon"
                                            >
                                                +
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {activeTab === 'alerts' && (
                                <div className="text-center py-8 text-white/60">
                                    <div className="text-4xl mb-4">🔔</div>
                                    <p>Alerts will appear here when posts match your filters.</p>
                                    <p className="text-sm mt-2">Check your Pushover notifications for real-time alerts!</p>
                                </div>
                            )}

                            {activeTab === 'settings' && (
                                <div className="space-y-2">
                                    <div className="settings-row">
                                        <span className="text-white/90">Refresh Interval</span>
                                        <select
                                            value={formData.cooldown_minutes || 10}
                                            onChange={(e) => handleInputChange('cooldown_minutes', parseInt(e.target.value))}
                                            className="input-field w-auto bg-white/10"
                                        >
                                            <option value={1}>1 Minute</option>
                                            <option value={2}>2 Minutes</option>
                                            <option value={5}>5 Minutes</option>
                                            <option value={10}>10 Minutes</option>
                                            <option value={15}>15 Minutes</option>
                                            <option value={30}>30 Minutes</option>
                                            <option value={60}>1 Hour</option>
                                        </select>
                                    </div>

                                    <div className="settings-row">
                                        <span className="text-white/90">Max Post Age</span>
                                        <select
                                            value={formData.max_post_age_hours || 12}
                                            onChange={(e) => handleInputChange('max_post_age_hours', parseInt(e.target.value))}
                                            className="input-field w-auto bg-white/10"
                                        >
                                            <option value={1}>1 Hour</option>
                                            <option value={6}>6 Hours</option>
                                            <option value={12}>12 Hours</option>
                                            <option value={24}>24 Hours</option>
                                            <option value={48}>2 Days</option>
                                            <option value={168}>1 Week</option>
                                        </select>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                    {/* End Scrollable Content */}

                    {/* Error Message */}
                    {error && (
                        <div className="mx-4 mb-2 p-3 bg-red-500/30 border border-red-500/50 rounded-lg text-white text-sm">
                            ⚠️ {error}
                        </div>
                    )}

                    {/* Footer - Always Visible */}
                    <div className="modal-footer p-4 flex gap-3" style={{ backgroundColor }}>
                        {!isCreating && monitor && !confirmDelete && (
                            <button
                                type="button"
                                onClick={() => setConfirmDelete(true)}
                                className="btn-primary bg-red-500/30 hover:bg-red-500/50 flex-1"
                            >
                                🗑️ Delete
                            </button>
                        )}
                        {confirmDelete && (
                            <>
                                <button
                                    type="button"
                                    onClick={() => setConfirmDelete(false)}
                                    className="btn-primary bg-white/20 hover:bg-white/30 flex-1"
                                >
                                    ✕ Cancel
                                </button>
                                <button
                                    type="button"
                                    onClick={() => onDelete(monitor!.id)}
                                    className="btn-primary bg-red-500 hover:bg-red-600 flex-1"
                                >
                                    🗑️ Confirm Delete
                                </button>
                            </>
                        )}
                        {!confirmDelete && (
                            <button
                                type="submit"
                                className="btn-primary flex-1"
                                disabled={isSaving}
                            >
                                {isSaving ? '⏳ Validating...' : '✓ Save'}
                            </button>
                        )}
                    </div>
                </form>
            </div>
        </div>
    );
}
