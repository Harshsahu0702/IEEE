import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import {
  Activity,
  Cpu,
  AlertTriangle,
  Bell,
  Terminal,
  Video,
  Play,
  Square,
  Clock,
  ArrowUpRight,
  ShieldAlert,
  CheckCircle2
} from 'lucide-react';

export const Overview = () => {
  const { canOperate } = useAuth();
  const { addToast } = useToast();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchStats = async () => {
    try {
      const data = await api.overview.getStats();
      setStats(data);
    } catch (err) {
      console.error('Error fetching overview stats:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleStopTask = async (taskId) => {
    if (!canOperate) return;
    setActionLoading(true);
    try {
      await api.tasks.stop(taskId);
      addToast({
        type: 'info',
        title: 'Task Terminated',
        message: `Task #${taskId} was cleanly stopped by operator.`
      });
      fetchStats();
    } catch (err) {
      addToast({ type: 'error', title: 'Error', message: err.message });
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-28 bg-dark-900 border border-dark-800 rounded-2xl" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-32 bg-dark-900 border border-dark-800 rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  const statCards = [
    {
      title: 'Active Tasks',
      value: stats?.active_tasks_count || 0,
      sub: `${stats?.active_tasks_count ? 'Background workers executing' : 'All monitoring idle'}`,
      icon: Activity,
      color: 'text-emerald-400',
      border: 'border-emerald-500/20',
      bg: 'bg-emerald-500/5'
    },
    {
      title: 'Devices Online',
      value: `${stats?.devices_online || 0} / ${stats?.total_devices || 0}`,
      sub: `${stats?.devices_pending ? `${stats.devices_pending} pending approval` : 'All devices trusted'}`,
      icon: Cpu,
      color: 'text-cyan-400',
      border: 'border-cyan-500/20',
      bg: 'bg-cyan-500/5'
    },
    {
      title: 'Open Events',
      value: stats?.open_events || 0,
      sub: 'Status: Pending human review',
      icon: AlertTriangle,
      color: 'text-amber-400',
      border: 'border-amber-500/20',
      bg: 'bg-amber-500/5'
    },
    {
      title: "Today's Alerts",
      value: stats?.today_alerts || 0,
      sub: 'Cumulative incident triggers',
      icon: Bell,
      color: 'text-rose-400',
      border: 'border-rose-500/20',
      bg: 'bg-rose-500/5'
    }
  ];

  return (
    <div className="space-y-7">
      {/* Top Banner / Security Briefing */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-dark-900 via-dark-850 to-dark-900 border border-dark-800 shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 radar-online" />
            <h1 className="text-xl font-bold text-white tracking-tight">Security Operations Command</h1>
          </div>
          <p className="text-xs text-slate-400">
            Real-time optical vision (YOLOv8n person aggregate) & MQTT environmental telemetry engine.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            to="/command"
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-dark-950 font-semibold text-xs tracking-wide transition-all shadow-md shadow-emerald-950"
          >
            <Terminal className="w-4 h-4" />
            <span>AI Command Center</span>
          </Link>
          <Link
            to="/monitoring"
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-dark-800 hover:bg-dark-700 text-slate-200 border border-dark-700 text-xs font-medium transition-colors"
          >
            <Video className="w-4 h-4 text-cyan-400" />
            <span>Live Stream</span>
          </Link>
        </div>
      </div>

      {/* 4 Overview Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((card, idx) => {
          const Icon = card.icon;
          return (
            <div
              key={idx}
              className={`p-5 rounded-2xl border ${card.border} ${card.bg} backdrop-blur-sm transition-all hover:border-opacity-50`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">{card.title}</span>
                <div className={`p-2 rounded-lg bg-dark-900 border border-dark-800 ${card.color}`}>
                  <Icon className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-3">
                <span className="text-2xl font-bold font-mono text-white tracking-tight">{card.value}</span>
                <p className="text-[11px] text-slate-400 mt-1 font-mono">{card.sub}</p>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Active Monitoring Tasks (1 Column) */}
        <div className="p-5 rounded-2xl bg-dark-900/90 border border-dark-800 space-y-4">
          <div className="flex items-center justify-between border-b border-dark-800 pb-3">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-400" />
              <span>Active Monitoring Tasks</span>
            </h2>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              {stats?.active_tasks?.length || 0} RUNNING
            </span>
          </div>

          {stats?.active_tasks && stats.active_tasks.length > 0 ? (
            <div className="space-y-3">
              {stats.active_tasks.map((task) => (
                <div
                  key={task.id}
                  className="p-3.5 rounded-xl border border-dark-750 bg-dark-950/80 flex items-center justify-between gap-3 text-xs"
                >
                  <div>
                    <span className="font-semibold text-slate-200 uppercase font-mono tracking-wide">
                      {task.plugin_name.replace('_', ' ')}
                    </span>
                    <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                      Source: <span className="text-cyan-400">{task.target_source}</span>
                    </p>
                  </div>
                  {canOperate && (
                    <button
                      onClick={() => handleStopTask(task.id)}
                      disabled={actionLoading}
                      className="px-2.5 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 font-mono text-[11px] flex items-center gap-1.5 transition-colors"
                    >
                      <Square className="w-3 h-3 fill-current" />
                      <span>Stop</span>
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="py-8 text-center text-xs text-slate-400 space-y-2">
              <p>No active monitoring tasks running.</p>
              <Link to="/command" className="text-emerald-400 hover:underline inline-block text-xs">
                Launch via AI Command Center &rarr;
              </Link>
            </div>
          )}
        </div>

        {/* Recent Incident Alerts (2 Columns) */}
        <div className="lg:col-span-2 p-5 rounded-2xl bg-dark-900/90 border border-dark-800 space-y-4">
          <div className="flex items-center justify-between border-b border-dark-800 pb-3">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-amber-400" />
              <span>Recent Incident Detections</span>
            </h2>
            <Link to="/events" className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1 font-mono">
              View All Events <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {stats?.recent_events && stats.recent_events.length > 0 ? (
            <div className="space-y-2.5">
              {stats.recent_events.map((evt) => (
                <div
                  key={evt.id}
                  className="p-3.5 rounded-xl border border-dark-800 bg-dark-950/60 flex items-start justify-between gap-4 text-xs hover:border-dark-700 transition-colors"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold uppercase ${
                        evt.severity === 'critical' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' :
                        evt.severity === 'high' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' :
                        'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                      }`}>
                        {evt.severity}
                      </span>
                      <span className="font-medium text-slate-200">{evt.event_type.replace('_', ' ').toUpperCase()}</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">{evt.description}</p>
                    <p className="text-[10px] font-mono text-slate-400">
                      Confidence: {Math.round((evt.confidence || 0) * 100)}% &bull; Source: {evt.source}
                    </p>
                  </div>

                  <div className="text-right shrink-0">
                    <span className="px-2 py-1 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] font-mono">
                      PENDING REVIEW
                    </span>
                    <p className="text-[10px] text-slate-400 font-mono mt-2">
                      {evt.created_at ? new Date(evt.created_at).toLocaleTimeString() : ''}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-10 text-center text-xs text-slate-400 flex flex-col items-center gap-2">
              <CheckCircle2 className="w-6 h-6 text-emerald-400" />
              <span>No alerts recorded. System running clear.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Overview;

