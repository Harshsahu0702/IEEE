import React, { useState, useEffect } from 'react';
import {
  FileText,
  Download,
  Calendar,
  Filter,
  RefreshCw,
  Trash2,
  CheckCircle,
  FileSpreadsheet,
  AlertCircle,
  Clock,
  Sparkles
} from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export default function Reports() {
  const { addToast } = useToast();

  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  // Form state
  const [format, setFormat] = useState('pdf');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const fetchReports = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await api.reports.list();
      setReports(data);
    } catch (err) {
      addToast(err.message || 'Failed to fetch reports list', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  const handleGenerate = async (e) => {
    e.preventDefault();
    setGenerating(true);
    try {
      const payload = {
        format,
        start_date: startDate ? new Date(startDate).toISOString() : undefined,
        end_date: endDate ? new Date(endDate).toISOString() : undefined,
      };
      const result = await api.reports.generate(payload);
      addToast(`Report ${result.report_id} generated successfully!`, 'success');
      fetchReports(true);
    } catch (err) {
      addToast(err.message || 'Failed to generate report', 'error');
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async (id, reportId) => {
    if (!window.confirm(`Delete report ${reportId}?`)) return;
    try {
      await api.reports.delete(id);
      addToast(`Report deleted`, 'success');
      setReports((prev) => prev.filter((r) => r.id !== id));
    } catch (err) {
      addToast(err.message || 'Failed to delete report', 'error');
    }
  };

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <FileText className="w-6 h-6 text-indigo-400" />
            Operational & Incident Reports
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Generate formal PDF analytics and CSV audit records for security and environmental events.
          </p>
        </div>

        <button
          onClick={() => fetchReports(true)}
          className="flex items-center gap-2 px-3 py-2 text-sm bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition w-fit"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Report Generator Card */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-4 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-indigo-400" />
          Generate New Report
        </h2>

        <form onSubmit={handleGenerate} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
          {/* Format selection */}
          <div>
            <label className="text-xs text-slate-400 block mb-1.5 font-medium">Export Format</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setFormat('pdf')}
                className={`py-2 px-3 text-xs rounded-lg border font-semibold flex items-center justify-center gap-1.5 transition ${
                  format === 'pdf'
                    ? 'bg-rose-500/20 text-rose-300 border-rose-500/50 ring-1 ring-rose-500/30'
                    : 'bg-slate-950 text-slate-400 border-slate-800 hover:border-slate-700'
                }`}
              >
                <FileText className="w-3.5 h-3.5 text-rose-400" />
                PDF Document
              </button>
              <button
                type="button"
                onClick={() => setFormat('csv')}
                className={`py-2 px-3 text-xs rounded-lg border font-semibold flex items-center justify-center gap-1.5 transition ${
                  format === 'csv'
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50 ring-1 ring-emerald-500/30'
                    : 'bg-slate-950 text-slate-400 border-slate-800 hover:border-slate-700'
                }`}
              >
                <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
                CSV Ledger
              </button>
            </div>
          </div>

          {/* Start Date */}
          <div>
            <label className="text-xs text-slate-400 block mb-1.5 font-medium">From Date (Optional)</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* End Date */}
          <div>
            <label className="text-xs text-slate-400 block mb-1.5 font-medium">To Date (Optional)</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* Submit */}
          <div>
            <button
              type="submit"
              disabled={generating}
              className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2"
            >
              {generating ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" /> Compiling...
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" /> Generate & Compile
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Reports Ledger */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200">Generated Reports Archive</h3>
          <span className="text-xs text-slate-500">{reports.length} report(s) available</span>
        </div>

        {loading ? (
          <div className="py-20 text-center text-slate-500 flex flex-col items-center gap-3">
            <RefreshCw className="w-8 h-8 animate-spin text-indigo-400" />
            <span>Loading historical reports...</span>
          </div>
        ) : reports.length === 0 ? (
          <div className="py-16 text-center text-slate-500">
            <FileText className="w-10 h-10 mx-auto text-slate-600 mb-2" />
            <p className="text-sm text-slate-300">No reports generated yet.</p>
            <p className="text-xs text-slate-500 mt-1">Use the panel above to generate your first incident analysis report.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/50 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                  <th className="py-3 px-4">Report Identifier</th>
                  <th className="py-3 px-4">Format</th>
                  <th className="py-3 px-4">Generated At</th>
                  <th className="py-3 px-4">Date Filter Scope</th>
                  <th className="py-3 px-4">Events Captured</th>
                  <th className="py-3 px-4">Size</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-xs">
                {reports.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-800/40 transition">
                    <td className="py-3 px-4 font-mono font-medium text-slate-200">
                      {r.report_id}
                    </td>
                    <td className="py-3 px-4">
                      {r.format === 'pdf' ? (
                        <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40 uppercase">
                          PDF
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 uppercase">
                          CSV
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-400 whitespace-nowrap">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-4 text-slate-400 text-[11px]">
                      {r.start_date || r.end_date
                        ? `${r.start_date ? new Date(r.start_date).toLocaleDateString() : 'Start'} → ${r.end_date ? new Date(r.end_date).toLocaleDateString() : 'Now'}`
                        : 'Complete History'}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-300">
                      {r.summary_metrics?.total_events ?? 0} events
                    </td>
                    <td className="py-3 px-4 text-slate-400 font-mono">
                      {formatBytes(r.file_size_bytes)}
                    </td>
                    <td className="py-3 px-4 text-right space-x-2">
                      <a
                        href={api.reports.downloadUrl(r.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 rounded border border-indigo-500/40 transition"
                      >
                        <Download className="w-3.5 h-3.5" /> Download
                      </a>
                      <button
                        onClick={() => handleDelete(r.id, r.report_id)}
                        className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 rounded border border-rose-500/30 transition"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
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
