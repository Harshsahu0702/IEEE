import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { wsService } from '../../services/websocket';
import { Shield, Radio, Wifi, WifiOff, LogOut, Bell, User } from 'lucide-react';

export const Navbar = ({ systemStatus = 'operational', openEventsCount = 0 }) => {
  const { user, logout } = useAuth();
  const [wsStatus, setWsStatus] = useState('disconnected');

  useEffect(() => {
    const unsub = wsService.onStatusChange((status) => {
      setWsStatus(status);
    });
    return unsub;
  }, []);

  const statusConfig = {
    operational: { label: 'OPERATIONAL', bg: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' },
    elevated: { label: 'ELEVATED ALERTS', bg: 'bg-amber-500/10 text-amber-400 border-amber-500/30' },
    hazard_alert: { label: 'CRITICAL HAZARD', bg: 'bg-rose-500/20 text-rose-400 border-rose-500/40 animate-pulse' }
  };

  const currentStatus = statusConfig[systemStatus] || statusConfig.operational;

  return (
    <header className="h-16 border-b border-dark-800 bg-dark-900/80 backdrop-blur-md px-6 flex items-center justify-between z-20 sticky top-0">
      {/* Brand & Mode */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <span className="font-bold tracking-tight text-white flex items-center gap-1.5 text-base">
              OmniSense <span className="text-emerald-400 font-mono text-xs px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">AI</span>
            </span>
            <p className="text-[10px] text-slate-400 font-mono tracking-wider uppercase">Security & AIoT Operations</p>
          </div>
        </div>

        <div className="h-5 w-px bg-dark-800 hidden sm:block" />

        {/* Global Security Status Indicator */}
        <div className={`hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-full border text-xs font-mono font-semibold ${currentStatus.bg}`}>
          <span className="w-2 h-2 rounded-full bg-current radar-online" />
          {currentStatus.label}
        </div>
      </div>

      {/* Right Controls: WebSocket, User Profile, Logout */}
      <div className="flex items-center gap-4">
        {/* WebSocket Heartbeat Indicator */}
        <div className="flex items-center gap-1.5 text-xs font-mono text-slate-400 bg-dark-850 px-2.5 py-1 rounded-lg border border-dark-800">
          {wsStatus === 'connected' ? (
            <>
              <Wifi className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-emerald-400">WS LIVE</span>
            </>
          ) : (
            <>
              <WifiOff className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
              <span className="text-amber-400 uppercase">RECONNECTING...</span>
            </>
          )}
        </div>

        {/* Operator Badge */}
        <div className="flex items-center gap-2.5 pl-2 border-l border-dark-800">
          <div className="w-8 h-8 rounded-full bg-dark-800 border border-dark-700 flex items-center justify-center text-slate-300">
            <User className="w-4 h-4" />
          </div>
          <div className="hidden md:block text-left text-xs">
            <p className="font-medium text-slate-200">{user?.username || 'Operator'}</p>
            <p className="text-[10px] text-emerald-400 font-mono uppercase tracking-wider">{user?.role || 'viewer'}</p>
          </div>

          <button
            onClick={logout}
            title="Log out of session"
            className="p-2 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors ml-1"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
