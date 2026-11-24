import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import {
  LayoutDashboard,
  Terminal,
  Video,
  Cpu,
  AlertTriangle,
  FileText,
  FileSpreadsheet,
  Settings
} from 'lucide-react';

export const Sidebar = ({ isOpen = true }) => {
  const { isAdmin } = useAuth();

  const links = [
    { to: '/', label: 'Overview', icon: LayoutDashboard },
    { to: '/command', label: 'AI Command Center', icon: Terminal, highlight: true },
    { to: '/live', label: 'Live Monitoring', icon: Video },
    { to: '/devices', label: 'IoT Devices', icon: Cpu },
    { to: '/events', label: 'Events & Alerts', icon: AlertTriangle },
    { to: '/reports', label: 'Reports & Audits', icon: FileSpreadsheet },
    ...(isAdmin ? [{ to: '/audit', label: 'Audit Logs', icon: FileText }] : []),
    { to: '/settings', label: 'Settings', icon: Settings },
  ];


  return (
    <aside
      className={`border-slate-200 bg-white flex flex-col justify-between shrink-0 shadow-sm transition-all duration-300 ease-in-out ${
        isOpen
          ? 'w-64 border-r py-6 px-3 opacity-100'
          : 'w-0 border-r-0 py-6 px-0 opacity-0 overflow-hidden pointer-events-none'
      }`}
      aria-hidden={!isOpen}
    >
      <div className="space-y-6">
        <div className="px-3">
          <p className="text-[10px] font-mono font-semibold uppercase tracking-wider text-slate-400">
            Navigation Menu
          </p>
        </div>

        <nav className="space-y-1.5">
          {links.map((link) => {
            const Icon = link.icon;
            return (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all ${
                    isActive
                      ? 'bg-slate-900 text-white shadow-sm'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  } ${link.highlight && !link.isActive ? 'ring-1 ring-emerald-500/30 text-emerald-700 bg-emerald-50/50' : ''}`
                }
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span>{link.label}</span>
                {link.highlight && (
                  <span className="ml-auto text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-semibold">
                    CORE
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* System Integrity Chip */}
      <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 text-[11px] font-mono space-y-1 text-slate-500">
        <div className="flex items-center justify-between text-slate-700">
          <span>AI Engine</span>
          <span className="text-emerald-700 font-bold">Universal VLM</span>
        </div>
        <div className="flex items-center justify-between text-slate-700">
          <span>Broker</span>
          <span className="text-indigo-600 font-bold">MQTT Live</span>
        </div>
        <p className="text-[9px] text-slate-400 pt-1 border-t border-slate-200">Privacy rule: No biometric ID</p>
      </div>
    </aside>
  );
};
