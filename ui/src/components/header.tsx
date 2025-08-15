import React, { useState } from 'react';
import { 
  Menu, 
  X, 
  Settings, 
  Download, 
  Brain, 
  Zap,
  Moon,
  Sun,
  Monitor
} from 'lucide-react';
import { useAppStore, useSettings } from '../lib/store';
import { apiClient } from '../lib/api';

const Header: React.FC = () => {
  const { settings, updateSettings } = useSettings();
  const currentSession = useAppStore((state) => state.currentSession);
  const toggleSidebar = useAppStore((state) => state.toggleSidebar);
  const sidebarOpen = useAppStore((state) => state.sidebarOpen);
  
  const [showSettings, setShowSettings] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const handleExportSession = async () => {
    if (!currentSession) return;
    
    setIsExporting(true);
    try {
      const data = await apiClient.exportSession(currentSession.id);
      
      // Create and download JSON file
      const blob = new Blob([JSON.stringify(data, null, 2)], { 
        type: 'application/json' 
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `session-${currentSession.id}-${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Export failed:', error);
    } finally {
      setIsExporting(false);
    }
  };

  const toggleTheme = () => {
    const themes = ['light', 'dark', 'auto'] as const;
    const currentIndex = themes.indexOf(settings.theme);
    const nextTheme = themes[(currentIndex + 1) % themes.length];
    updateSettings({ theme: nextTheme });
  };

  const ThemeIcon = () => {
    switch (settings.theme) {
      case 'light': return <Sun className="w-4 h-4" />;
      case 'dark': return <Moon className="w-4 h-4" />;
      default: return <Monitor className="w-4 h-4" />;
    }
  };

  return (
    <header className="bg-white dark:bg-dark-800 border-b border-gray-200 dark:border-dark-700 px-4 py-3">
      <div className="flex items-center justify-between">
        {/* Left side */}
        <div className="flex items-center space-x-4">
          <button
            onClick={toggleSidebar}
            className="p-2 hover:bg-gray-100 dark:hover:bg-dark-700 rounded-md transition-colors"
            aria-label="Toggle sidebar"
          >
            {sidebarOpen ? (
              <X className="w-5 h-5" />
            ) : (
              <Menu className="w-5 h-5" />
            )}
          </button>
          
          <div className="flex items-center space-x-2">
            <Brain className="w-6 h-6 text-primary-600 dark:text-primary-400" />
            <h1 className="text-xl font-bold bg-gradient-to-r from-primary-600 to-purple-600 bg-clip-text text-transparent">
              GOD-MODE Agent
            </h1>
            <span className="text-xs bg-primary-100 dark:bg-primary-900 text-primary-700 dark:text-primary-300 px-2 py-1 rounded-full">
              v3.2 ULTRA
            </span>
          </div>
        </div>

        {/* Center - Session status */}
        {currentSession && (
          <div className="flex items-center space-x-2 text-sm text-gray-600 dark:text-gray-400">
            <div className="flex items-center space-x-1">
              <Zap className="w-4 h-4" />
              <span>Step {currentSession.currentStep}/{currentSession.maxSteps}</span>
            </div>
            <div className={`w-2 h-2 rounded-full ${
              currentSession.status === 'executing' ? 'bg-yellow-500 animate-pulse' :
              currentSession.status === 'completed' ? 'bg-green-500' :
              currentSession.status === 'error' ? 'bg-red-500' :
              'bg-gray-400'
            }`} />
            <span className="capitalize">{currentSession.status}</span>
          </div>
        )}

        {/* Right side */}
        <div className="flex items-center space-x-2">
          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            className="p-2 hover:bg-gray-100 dark:hover:bg-dark-700 rounded-md transition-colors"
            aria-label="Toggle theme"
          >
            <ThemeIcon />
          </button>

          {/* Export session */}
          {currentSession && (
            <button
              onClick={handleExportSession}
              disabled={isExporting}
              className="p-2 hover:bg-gray-100 dark:hover:bg-dark-700 rounded-md transition-colors disabled:opacity-50"
              aria-label="Export session"
            >
              <Download className={`w-4 h-4 ${isExporting ? 'animate-spin' : ''}`} />
            </button>
          )}

          {/* Settings */}
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 hover:bg-gray-100 dark:hover:bg-dark-700 rounded-md transition-colors"
            aria-label="Settings"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Settings dropdown */}
      {showSettings && (
        <div className="absolute right-4 top-16 w-80 bg-white dark:bg-dark-800 border border-gray-200 dark:border-dark-700 rounded-lg shadow-lg z-50">
          <div className="p-4 space-y-4">
            <h3 className="font-semibold text-lg">Settings</h3>
            
            {/* Backend URL */}
            <div>
              <label className="block text-sm font-medium mb-1">Backend URL</label>
              <input
                type="text"
                value={settings.backendUrl}
                onChange={(e) => updateSettings({ backendUrl: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-dark-600 rounded-md bg-white dark:bg-dark-700 text-sm"
                placeholder="http://127.0.0.1:8000"
              />
            </div>

            {/* Font size */}
            <div>
              <label className="block text-sm font-medium mb-1">Font Size</label>
              <select
                value={settings.fontSize}
                onChange={(e) => updateSettings({ fontSize: e.target.value as any })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-dark-600 rounded-md bg-white dark:bg-dark-700 text-sm"
              >
                <option value="small">Small</option>
                <option value="medium">Medium</option>
                <option value="large">Large</option>
              </select>
            </div>

            {/* Language */}
            <div>
              <label className="block text-sm font-medium mb-1">Language</label>
              <select
                value={settings.language}
                onChange={(e) => updateSettings({ language: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-dark-600 rounded-md bg-white dark:bg-dark-700 text-sm"
              >
                <option value="en">English</option>
                <option value="es">Español</option>
                <option value="fr">Français</option>
                <option value="de">Deutsch</option>
                <option value="zh">中文</option>
              </select>
            </div>

            {/* Toggle options */}
            <div className="space-y-2">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={settings.showThinkingPanel}
                  onChange={(e) => updateSettings({ showThinkingPanel: e.target.checked })}
                  className="rounded border-gray-300 dark:border-dark-600"
                />
                <span className="text-sm">Show Thinking Panel</span>
              </label>
              
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={settings.showMetricsBar}
                  onChange={(e) => updateSettings({ showMetricsBar: e.target.checked })}
                  className="rounded border-gray-300 dark:border-dark-600"
                />
                <span className="text-sm">Show Metrics Bar</span>
              </label>
              
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={settings.autoScroll}
                  onChange={(e) => updateSettings({ autoScroll: e.target.checked })}
                  className="rounded border-gray-300 dark:border-dark-600"
                />
                <span className="text-sm">Auto Scroll</span>
              </label>
              
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={settings.ecoMode}
                  onChange={(e) => updateSettings({ ecoMode: e.target.checked })}
                  className="rounded border-gray-300 dark:border-dark-600"
                />
                <span className="text-sm">Eco Mode</span>
              </label>
            </div>

            {/* Close button */}
            <button
              onClick={() => setShowSettings(false)}
              className="w-full mt-4 px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {/* Click outside to close settings */}
      {showSettings && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setShowSettings(false)}
        />
      )}
    </header>
  );
};

export default Header;