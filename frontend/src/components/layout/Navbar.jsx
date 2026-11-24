import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { wsService } from '../../services/websocket';
import { Shield, Radio, Wifi, WifiOff, LogOut, Bell, User, Menu, PanelLeftClose } from 'lucide-react';

export const Navbar = ({ systemStatus = 'operational', openEventsCount = 0, sidebarOpen = true, onToggleSidebar }) => {
  const { user, logout } = useAuth();
  const [wsStatus, setWsStatus] = useState('disconnected');

  useEffect(() => {
    const unsub = wsService.onStatusChange((status) => {
      setWsStatus(status);
    });
    return unsub;
  }, []);

  const statusConfig = {
    operational: { label: 'OPERATIONAL', bg: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
    elevated: { label: 'ELEVATED ALERTS', bg: 'bg-amber-50 text-amber-700 border-amber-200' },
    hazard_alert: { label: 'CRITICAL HAZARD', bg: 'bg-rose-50 text-rose-700 border-rose-300 animate-pulse' }
  };

  const currentStatus = statusConfig[systemStatus] || statusConfig.operational;

  return (
    <header className="h-16 border-b border-slate-200 bg-white/95 backdrop-blur-md px-6 flex items-center justify-between z-20 sticky top-0 shadow-sm">
      {/* Brand & Mode */}
      <div className="flex items-center gap-3.5">
        {onToggleSidebar && (
          <button
            type="button"
            onClick={onToggleSidebar}
            title={sidebarOpen ? 'Close side menu' : 'Open side menu'}
            aria-label={sidebarOpen ? 'Close side menu' : 'Open side menu'}
            className="p-2 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 hover:text-slate-900 transition-colors cursor-pointer"
          >
            {sidebarOpen ? <PanelLeftClose className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
          </button>
        )}
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <span className="font-bold tracking-tight text-slate-900 flex items-center gap-1.5 text-base">
              OmniSense <span className="text-emerald-700 font-mono text-xs px-1.5 py-0.5 rounded bg-emerald-50 border border-emerald-200">AI</span>
            </span>
            <p className="text-[10px] text-slate-500 font-mono tracking-wider uppercase">Security & AIoT Operations</p>
          </div>
        </div>

        <div className="h-5 w-px bg-slate-200 hidden sm:block" />

        {/* Global Security Status Indicator */}
        <div className={`hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-full border text-xs font-mono font-semibold ${currentStatus.bg}`}>
          <span className="w-2 h-2 rounded-full bg-current radar-online" />
          {currentStatus.label}
        </div>
      </div>

      {/* Right Controls: WebSocket, User Profile, Logout */}
      <div className="flex items-center gap-4">
        {/* WebSocket Heartbeat Indicator */}
        <div className="flex items-center gap-1.5 text-xs font-mono text-slate-600 bg-slate-100 px-2.5 py-1 rounded-lg border border-slate-200">
          {wsStatus === 'connected' ? (
            <>
              <Wifi className="w-3.5 h-3.5 text-emerald-600" />
              <span className="text-emerald-700 font-semibold">WS LIVE</span>
            </>
          ) : (
            <>
              <WifiOff className="w-3.5 h-3.5 text-amber-500 animate-pulse" />
              <span className="text-amber-700 uppercase">RECONNECTING...</span>
            </>
          )}
        </div>

        {/* Operator Badge */}
        <div className="flex items-center gap-2.5 pl-2 border-l border-slate-200">
          <div className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-700">
            <User className="w-4 h-4" />
          </div>
          <div className="hidden md:block text-left text-xs">
            <p className="font-semibold text-slate-800">{user?.username || 'Operator'}</p>
            <p className="text-[10px] text-emerald-600 font-mono uppercase tracking-wider">{user?.role || 'viewer'}</p>
          </div>

          <button
            onClick={logout}
            title="Log out of session"
            className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors ml-1"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
