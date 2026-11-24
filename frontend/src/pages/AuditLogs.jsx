import React, { useState, useEffect } from 'react';
import {
  FileText,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Search,
  Filter,
  RefreshCw,
  Clock,
  User,
  AlertOctagon,
  Info
} from 'lucide-react';
import { agentApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';

export default function AuditLogs() {
  const { user } = useAuth();
  const { addToast } = useToast();

  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');

  const isAdmin = user?.role === 'admin';

  const fetchLogs = async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const data = await agentApi.getAuditLogs({ limit: 100 });
      setLogs(data);
    } catch (err) {
      addToast(err.message || 'Failed to fetch audit records', 'error');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (isAdmin) {
      fetchLogs();
    } else {
      setLoading(false);
    }
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center max-w-lg mx-auto mt-12">
        <ShieldAlert className="w-12 h-12 text-amber-400 mx-auto mb-3" />
        <h2 className="text-xl font-bold text-slate-100">Restricted Access</h2>
        <p className="text-sm text-slate-400 mt-2">
          The Master Agent Audit Log contains immutable security records of all AI command interpretations, safety evaluations, and privacy enforcement actions.
        </p>
        <div className="mt-4 p-3 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-500">
          Administrator privileges are required to view this ledger.
        </div>
      </div>
    );
  }

  const filteredLogs = logs.filter((log) => {
    if (decisionFilter && log.decision !== decisionFilter) return false;
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      log.user_command.toLowerCase().includes(term) ||
      (log.reasoning && log.reasoning.toLowerCase().includes(term)) ||
      (log.username && log.username.toLowerCase().includes(term)) ||
      String(log.id).includes(term)
    );
  });

  const getDecisionBadge = (decision) => {
    switch (decision) {
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
            <ShieldCheck className="w-3 h-3" /> Approved
          </span>
        );
      case 'blocked':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/40">
            <AlertOctagon className="w-3 h-3" /> Blocked
          </span>
        );
      case 'requires_review':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/40">
            <ShieldAlert className="w-3 h-3" /> Requires Review
          </span>
        );
      default:
        return <span className="px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-400">{decision}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <FileText className="w-6 h-6 text-indigo-400" />
            AI Master Agent Audit Ledger
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Immutable log of all user prompts, LLM plan extractions, and privacy safety gate checks.
          </p>
        </div>
        <button
          onClick={() => fetchLogs(true)}
          disabled={refreshing}
          className="flex items-center gap-2 px-3 py-2 text-sm bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition w-fit"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Filter / Search Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row gap-3 items-center justify-between">
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search commands, reasoning, user..."
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div className="flex items-center gap-2 w-full md:w-auto">
          <Filter className="w-4 h-4 text-slate-400" />
          <select
            value={decisionFilter}
            onChange={(e) => setDecisionFilter(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="">All Decisions</option>
            <option value="approved">Approved</option>
            <option value="blocked">Blocked</option>
            <option value="requires_review">Requires Review</option>
          </select>
        </div>
      </div>

      {/* Audit Log Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        {loading ? (
          <div className="py-20 text-center text-slate-500 flex flex-col items-center gap-3">
            <RefreshCw className="w-8 h-8 animate-spin text-indigo-400" />
            <span>Loading audit records...</span>
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="py-16 text-center text-slate-500">
            <Shield className="w-10 h-10 mx-auto text-slate-600 mb-2" />
            <p className="text-sm">No audit logs found matching criteria.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/50 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                  <th className="py-3 px-4">Log ID</th>
                  <th className="py-3 px-4">Timestamp</th>
                  <th className="py-3 px-4">Operator</th>
                  <th className="py-3 px-4">User Prompt</th>
                  <th className="py-3 px-4">Decision</th>
                  <th className="py-3 px-4">Risk Level</th>
                  <th className="py-3 px-4">Safety Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-xs">
                {filteredLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-800/40 transition">
                    <td className="py-3 px-4 font-mono text-slate-500">#{log.id}</td>
                    <td className="py-3 px-4 text-slate-400 whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleString()}
                    </td>
                    <td className="py-3 px-4 text-slate-300 font-medium whitespace-nowrap">
                      <span className="flex items-center gap-1.5">
                        <User className="w-3.5 h-3.5 text-slate-500" />
                        {log.username || 'system'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-200 font-mono max-w-xs truncate">
                      "{log.user_command}"
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      {getDecisionBadge(log.decision)}
                    </td>
                    <td className="py-3 px-4 text-slate-400 font-mono">
                      {log.risk_level || 'standard'}
                    </td>
                    <td className="py-3 px-4 text-slate-400 max-w-sm truncate" title={log.reasoning}>
                      {log.reasoning || 'No violations detected'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
