import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  ShieldAlert,
  Filter,
  Eye,
  RefreshCw,
  Search,
  ExternalLink,
  MessageSquare,
  Sparkles,
  Info
} from 'lucide-react';
import { eventsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';

export default function EventsAlerts() {
  const { user } = useAuth();
  const { addToast } = useToast();

  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  // Review Form
  const [reviewStatus, setReviewStatus] = useState('confirmed');
  const [reviewerNotes, setReviewerNotes] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);

  const canReview = user?.role === 'admin' || user?.role === 'operator';
  const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  const fetchEvents = async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const data = await eventsApi.list({
        status: statusFilter || undefined,
        severity: severityFilter || undefined,
        limit: 100
      });
      setEvents(data);
      if (selectedEvent) {
        const updated = data.find((e) => e.id === selectedEvent.id);
        if (updated) setSelectedEvent(updated);
      }
    } catch (err) {
      addToast(err.message || 'Failed to fetch incident events', 'error');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchEvents();
  }, [statusFilter, severityFilter]);

  const handleReviewSubmit = async (e) => {
    e.preventDefault();
    if (!selectedEvent) return;
    if (!canReview) {
      addToast('Viewer accounts cannot review or resolve events.', 'error');
      return;
    }

    setSubmittingReview(true);
    try {
      const updated = await eventsApi.review(selectedEvent.id, {
        status: reviewStatus,
        reviewer_notes: reviewerNotes.trim() || undefined
      });
      addToast(`Incident #${selectedEvent.id} marked as ${reviewStatus.replace('_', ' ')}`, 'success');
      setSelectedEvent(updated);
      setReviewerNotes('');
      fetchEvents(true);
    } catch (err) {
      addToast(err.message || 'Failed to submit event review', 'error');
    } finally {
      setSubmittingReview(false);
    }
  };

  const filteredEvents = events.filter((evt) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      evt.event_type.toLowerCase().includes(term) ||
      evt.description.toLowerCase().includes(term) ||
      evt.source.toLowerCase().includes(term) ||
      String(evt.id).includes(term)
    );
  });

  const getSeverityBadge = (sev) => {
    switch (sev) {
      case 'critical':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/40">Critical</span>;
      case 'high':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/40">High</span>;
      case 'medium':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/20 text-blue-400 border border-blue-500/40">Medium</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-500/20 text-slate-400 border border-slate-500/40">Low</span>;
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'pending_review':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/50 animate-pulse">
            <Clock className="w-3 h-3" /> AI-detected, needs human review
          </span>
        );
      case 'confirmed':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
            <CheckCircle className="w-3 h-3" /> Confirmed Incident
          </span>
        );
      case 'false_positive':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-500/20 text-slate-400 border border-slate-500/40">
            <XCircle className="w-3 h-3" /> False Positive
          </span>
        );
      case 'resolved':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-cyan-500/20 text-cyan-400 border border-cyan-500/40">
            <CheckCircle className="w-3 h-3" /> Resolved
          </span>
        );
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-400">{status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-indigo-400" />
            Events & Incident Alerts
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Human-in-the-loop oversight. All detections require operator verification.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchEvents(true)}
            disabled={refreshing}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Notice Banner */}
      <div className="bg-amber-950/20 border border-amber-500/30 rounded-xl p-4 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-amber-200/90 leading-relaxed">
          <strong className="text-amber-300 font-semibold">Strict AIoT Safety Protocol:</strong> AI vision and environmental algorithms never flag incidents as confirmed automatically. All alerts are tagged <code className="bg-amber-900/40 px-1 py-0.5 rounded text-amber-300 font-mono">pending_review</code> until an authorized operator inspects the evidence screenshot and sensor telemetry.
        </div>
      </div>

      {/* Filters & Search */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row gap-3 items-center justify-between">
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by ID, type, source..."
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 w-full md:w-auto">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="">All Statuses</option>
              <option value="pending_review">Pending Review</option>
              <option value="confirmed">Confirmed</option>
              <option value="false_positive">False Positive</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>

          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
      </div>

      {/* Main Grid: Event List & Details Drawer */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Event List (Left 7 cols or full) */}
        <div className={`space-y-3 ${selectedEvent ? 'lg:col-span-7' : 'lg:col-span-12'}`}>
          {loading ? (
            <div className="py-20 text-center text-slate-500 flex flex-col items-center gap-3">
              <RefreshCw className="w-8 h-8 animate-spin text-indigo-400" />
              <span>Loading incident alerts...</span>
            </div>
          ) : filteredEvents.length === 0 ? (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-500">
              <CheckCircle className="w-10 h-10 mx-auto text-emerald-400 mb-2 opacity-60" />
              <p className="text-base text-slate-300 font-medium">No events found matching current criteria</p>
              <p className="text-xs text-slate-500 mt-1">Adjust filters or inject telemetry spikes from the simulator.</p>
            </div>
          ) : (
            filteredEvents.map((evt) => {
              const isSelected = selectedEvent?.id === evt.id;
              return (
                <div
                  key={evt.id}
                  onClick={() => setSelectedEvent(evt)}
                  className={`bg-slate-900 border rounded-xl p-4 transition cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                    isSelected
                      ? 'border-indigo-500 bg-indigo-950/20 ring-1 ring-indigo-500/40'
                      : 'border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-mono text-slate-500">#{evt.id}</span>
                      {getSeverityBadge(evt.severity)}
                      {getStatusBadge(evt.status)}
                      <span className="text-xs font-mono text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                        {evt.source}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-slate-200 truncate">
                      {evt.description}
                    </h3>
                    <div className="flex items-center gap-4 text-xs text-slate-400">
                      <span>Confidence: <strong className="text-slate-300 font-mono">{(evt.confidence * 100).toFixed(0)}%</strong></span>
                      <span>{new Date(evt.created_at).toLocaleString()}</span>
                      {evt.evidence_screenshot_path && (
                        <span className="text-indigo-400 flex items-center gap-1">
                          <Eye className="w-3 h-3" /> Snapshot attached
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex sm:flex-col items-center sm:items-end justify-between gap-2 border-t sm:border-t-0 pt-2 sm:pt-0 border-slate-800">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedEvent(evt);
                      }}
                      className="px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 flex items-center gap-1.5"
                    >
                      Inspect <Eye className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Selected Event Detail Drawer (Right 5 cols) */}
        {selectedEvent && (
          <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6 sticky top-6 max-h-[calc(100vh-6rem)] overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-slate-500">INCIDENT #{selectedEvent.id}</span>
                  {getSeverityBadge(selectedEvent.severity)}
                </div>
                <h2 className="text-lg font-bold text-slate-100 mt-1">
                  {selectedEvent.event_type}
                </h2>
              </div>
              <button
                onClick={() => setSelectedEvent(null)}
                className="text-slate-400 hover:text-slate-200 text-sm p-1 rounded-lg hover:bg-slate-800"
              >
                ✕
              </button>
            </div>

            {/* Status callout */}
            <div className="bg-slate-950 border border-slate-800 rounded-lg p-3">
              <div className="text-xs text-slate-400 mb-1">Current Review Status</div>
              {getStatusBadge(selectedEvent.status)}
              {selectedEvent.reviewer_notes && (
                <div className="mt-2 text-xs text-slate-300 bg-slate-900 p-2 rounded border border-slate-800">
                  <span className="text-slate-500 font-semibold block mb-0.5">Operator Notes:</span>
                  {selectedEvent.reviewer_notes}
                </div>
              )}
            </div>

            {/* Evidence Snapshot */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                Evidence Record
              </label>
              {selectedEvent.evidence_screenshot_path ? (
                <div className="space-y-2">
                  <div className="relative rounded-lg overflow-hidden border border-slate-800 bg-black aspect-video flex items-center justify-center">
                    <img
                      src={`${apiBase}${selectedEvent.evidence_screenshot_path}`}
                      alt="Incident Evidence"
                      className="w-full h-full object-contain"
                      onError={(e) => {
                        e.target.onerror = null;
                        e.target.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60" viewBox="0 0 100 60"><rect width="100%" height="100%" fill="%231e293b"/><text x="50%" y="50%" fill="%2394a3b8" dominant-baseline="middle" text-anchor="middle" font-size="9">Snapshot unavailable</text></svg>';
                      }}
                    />
                  </div>
                  <a
                    href={`${apiBase}${selectedEvent.evidence_screenshot_path}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300"
                  >
                    Open full snapshot <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              ) : (
                <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-500 text-center">
                  Telemetry trigger — no visual snapshot attached (IoT sensor detection)
                </div>
              )}
            </div>

            {/* Confidence & Metrics */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                Detection Telemetry
              </label>
              <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-400">Model Confidence:</span>
                  <span className="font-mono text-emerald-400 font-bold">
                    {(selectedEvent.confidence * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-emerald-500 h-full rounded-full transition-all"
                    style={{ width: `${selectedEvent.confidence * 100}%` }}
                  />
                </div>
                <div className="pt-2 border-t border-slate-800">
                  <div className="text-xs text-slate-400 mb-1">Payload Metrics:</div>
                  <pre className="text-[11px] font-mono text-slate-300 bg-slate-900 p-2 rounded overflow-x-auto">
                    {JSON.stringify(selectedEvent.metrics, null, 2)}
                  </pre>
                </div>
              </div>
            </div>

            {/* Human-in-the-Loop Review Controls */}
            <div className="space-y-3 pt-2 border-t border-slate-800">
              <label className="text-xs font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles className="w-4 h-4 text-indigo-400" />
                Human Review Gate
              </label>

              {!canReview ? (
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-400 flex items-center gap-2">
                  <Info className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  Operator or Admin role required to confirm or dismiss incident alerts.
                </div>
              ) : (
                <form onSubmit={handleReviewSubmit} className="space-y-3">
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Verification Decision:</label>
                    <div className="grid grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => setReviewStatus('confirmed')}
                        className={`py-2 px-1 text-xs rounded-lg border font-medium transition flex flex-col items-center gap-1 ${
                          reviewStatus === 'confirmed'
                            ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50 ring-1 ring-emerald-500/30'
                            : 'bg-slate-950 text-slate-400 border-slate-800 hover:border-slate-700'
                        }`}
                      >
                        <CheckCircle className="w-4 h-4 text-emerald-400" />
                        Confirm
                      </button>
                      <button
                        type="button"
                        onClick={() => setReviewStatus('false_positive')}
                        className={`py-2 px-1 text-xs rounded-lg border font-medium transition flex flex-col items-center gap-1 ${
                          reviewStatus === 'false_positive'
                            ? 'bg-rose-500/20 text-rose-300 border-rose-500/50 ring-1 ring-rose-500/30'
                            : 'bg-slate-950 text-slate-400 border-slate-800 hover:border-slate-700'
                        }`}
                      >
                        <XCircle className="w-4 h-4 text-rose-400" />
                        False Alert
                      </button>
                      <button
                        type="button"
                        onClick={() => setReviewStatus('resolved')}
                        className={`py-2 px-1 text-xs rounded-lg border font-medium transition flex flex-col items-center gap-1 ${
                          reviewStatus === 'resolved'
                            ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50 ring-1 ring-cyan-500/30'
                            : 'bg-slate-950 text-slate-400 border-slate-800 hover:border-slate-700'
                        }`}
                      >
                        <CheckCircle className="w-4 h-4 text-cyan-400" />
                        Resolve
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="text-xs text-slate-400 block mb-1">
                      Reviewer Notes / Action Taken:
                    </label>
                    <textarea
                      rows={2}
                      value={reviewerNotes}
                      onChange={(e) => setReviewerNotes(e.target.value)}
                      placeholder="e.g. Visual confirmation of crowd threshold breach; notified security team."
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={submittingReview}
                    className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-1.5"
                  >
                    {submittingReview ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Saving Review...
                      </>
                    ) : (
                      'Save Review Decision'
                    )}
                  </button>
                </form>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
