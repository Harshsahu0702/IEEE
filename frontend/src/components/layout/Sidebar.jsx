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

export const Sidebar = () => {
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
    <aside className="w-64 border-r border-dark-800 bg-dark-900/90 flex flex-col justify-between py-6 px-3 shrink-0">
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
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 shadow-sm shadow-emerald-950'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
                  } ${link.highlight && !link.isActive ? 'ring-1 ring-cyan-500/20 text-cyan-300' : ''}`
                }
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span>{link.label}</span>
                {link.highlight && (
                  <span className="ml-auto text-[9px] font-mono px-1.5 py-0.2 rounded bg-cyan-500/20 text-cyan-300">
                    CORE
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* System Integrity Chip */}
      <div className="p-3.5 rounded-xl border border-dark-800 bg-dark-850/60 text-[11px] font-mono space-y-1 text-slate-400">
        <div className="flex items-center justify-between text-slate-300">
          <span>AI Engine</span>
          <span className="text-emerald-400 font-bold">YOLOv8n</span>
        </div>
        <div className="flex items-center justify-between text-slate-300">
          <span>Broker</span>
          <span className="text-cyan-400 font-bold">Mosquitto</span>
        </div>
        <p className="text-[9px] text-slate-400 pt-1 border-t border-dark-800">Privacy rule: No biometric ID</p>
      </div>
    </aside>
  );
};
