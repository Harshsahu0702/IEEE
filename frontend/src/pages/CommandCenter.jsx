import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import {
  Terminal,
  Mic,
  MicOff,
  Sparkles,
  CheckCircle,
  XCircle,
  AlertOctagon,
  Clock,
  Shield,
  Layers,
  ArrowRight,
  Activity,
  Square,
  Sliders,
  ShieldAlert,
  KeyRound,
  Maximize2,
  Lock,
  Video
} from 'lucide-react';

export const CommandCenter = () => {
  const navigate = useNavigate();
  const { user, canOperate } = useAuth();

  const { addToast } = useToast();

  const [command, setCommand] = useState('');
  const [loading, setLoading] = useState(false);
  const [planResult, setPlanResult] = useState(null);
  const [activeTasks, setActiveTasks] = useState([]);
  const [actionLoading, setActionLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);

  // Profiles
  const [profiles, setProfiles] = useState([]);
  const [profileLoading, setProfileLoading] = useState(false);

  // Editable rules state
  const [editableRules, setEditableRules] = useState({});

  // Zone editor state
  const [zoneRect, setZoneRect] = useState({ x1: 0.2, y1: 0.2, x2: 0.8, y2: 0.8 });
  const [isDrawing, setIsDrawing] = useState(false);
  const canvasRef = useRef(null);

  // Password change modal state
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);

  const exampleChips = [
    "Alert if any person comes in frame",
    "Alert if fan comes to the frame",
    "Monitor if fan is moving or stopped",
    "Watch for exam cheating — alert if students look sideways or talk",
    "Detect falls or elderly accidents in the room",
    "Alert if someone enters restricted zone",
    "stop monitoring"
  ];

  const fetchActiveTasks = async () => {
    try {
      const tasks = await api.tasks.list();
      setActiveTasks(tasks.filter((t) => t.status === 'running'));
    } catch (e) {
      console.error('Failed to fetch tasks:', e);
    }
  };

  const fetchProfiles = async () => {
    try {
      const data = await api.profiles.list();
      setProfiles(data);
    } catch (e) {
      console.error('Failed to fetch profiles:', e);
    }
  };

  useEffect(() => {
    fetchActiveTasks();
    fetchProfiles();
    const interval = setInterval(fetchActiveTasks, 5000);
    return () => clearInterval(interval);
  }, []);

  // Web Speech API Voice Input
  const toggleVoiceInput = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      addToast('Your browser does not support the Web Speech API. Please type your command.', 'warning');
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => setIsListening(true);
      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setCommand(transcript);
        setIsListening(false);
      };
      recognition.onerror = () => setIsListening(false);
      recognition.onend = () => setIsListening(false);
      recognition.start();
    } catch (e) {
      setIsListening(false);
    }
  };

  const handleSendCommand = async (e) => {
    e?.preventDefault();
    if (!command.trim()) return;

    setLoading(true);
    setPlanResult(null);

    try {
      const res = await api.agent.sendCommand(command);
      setPlanResult(res);
      if (res.plan?.rules) {
        setEditableRules({ ...res.plan.rules });
        if (res.plan.rules.zones && res.plan.rules.zones[0]?.polygon) {
          const poly = res.plan.rules.zones[0].polygon;
          if (poly.length >= 4) {
            setZoneRect({
              x1: Math.min(...poly.map(p => p[0])),
              y1: Math.min(...poly.map(p => p[1])),
              x2: Math.max(...poly.map(p => p[0])),
              y2: Math.max(...poly.map(p => p[1])),
            });
          }
        }
      }
      if (res.status === 'blocked') {
        addToast(res.explanation?.safety_reason || 'Command blocked by policy', 'error');
      }
    } catch (err) {
      addToast(err.message || 'Command processing failed', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleActivateProfile = async (profileId) => {
    setProfileLoading(true);
    try {
      const res = await api.profiles.activate(profileId);
      setPlanResult({
        plan_id: res.plan_id,
        status: 'pending_approval',
        plan: res.plan,
        explanation: {
          what_i_understood: res.message,
          why: `Activated via profile preset '${res.profile_name}'.`,
          modules_chosen: res.plan.modules,
          confidence: 0.98
        },
        safety: {
          decision: 'approved',
          risk_level: 'safe'
        }
      });
      setEditableRules(res.plan.rules || {});
      if (res.plan.rules?.zones?.[0]?.polygon) {
        const poly = res.plan.rules.zones[0].polygon;
        setZoneRect({
          x1: Math.min(...poly.map(p => p[0])),
          y1: Math.min(...poly.map(p => p[1])),
          x2: Math.max(...poly.map(p => p[0])),
          y2: Math.max(...poly.map(p => p[1])),
        });
      }
      addToast(`Profile staged. Review thresholds and click Approve.`, 'info');
    } catch (err) {
      addToast(err.message || 'Failed to activate profile', 'error');
    } finally {
      setProfileLoading(false);
    }
  };

  const handleApprovePlan = async (approved) => {
    if (!planResult?.plan_id) return;
    setActionLoading(true);

    try {
      // Merge updated editable rules before approval
      const finalRules = { ...editableRules };
      if (planResult.plan?.modules?.includes('security_monitoring')) {
        finalRules.zones = [
          {
            name: "Restricted Zone A",
            polygon: [
              [zoneRect.x1, zoneRect.y1],
              [zoneRect.x2, zoneRect.y1],
              [zoneRect.x2, zoneRect.y2],
              [zoneRect.x1, zoneRect.y2]
            ]
          }
        ];
      }

      await api.agent.approvePlan(planResult.plan_id, approved, 'Approved via SOC Command Center');
      addToast(
        approved ? 'Plan Approved! Autonomous workers started.' : 'Plan Rejected by operator.',
        approved ? 'success' : 'info'
      );
      setPlanResult(null);
      setCommand('');
      fetchActiveTasks();
    } catch (err) {
      addToast(err.message || 'Approval error', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleStopTask = async (taskId) => {
    try {
      await api.tasks.stop(taskId);
      addToast(`Task #${taskId} terminated.`, 'info');
      fetchActiveTasks();
    } catch (err) {
      addToast(err.message || 'Failed to stop task', 'error');
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setChangingPassword(true);
    try {
      await api.auth.changePassword(oldPassword, newPassword);
      addToast('Password updated! Default credential alert resolved.', 'success');
      setShowPasswordModal(false);
      setOldPassword('');
      setNewPassword('');
    } catch (err) {
      addToast(err.message || 'Failed to update password', 'error');
    } finally {
      setChangingPassword(false);
    }
  };

  const isSecurityPlan = planResult?.plan?.modules?.includes('security_monitoring');

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Default Password Security Warning */}
      {user?.is_default_password && (
        <div className="bg-amber-950/30 border border-amber-500/50 rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-lg shadow-amber-950/20">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0" />
            <div>
              <div className="text-sm font-semibold text-amber-200">
                Default Administrator Password Detected ('admin123')
              </div>
              <p className="text-xs text-amber-300/80">
                System hardening policy recommends immediately replacing the default credential.
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowPasswordModal(true)}
            className="px-3 py-1.5 text-xs bg-amber-500 hover:bg-amber-400 text-dark-950 font-bold rounded-lg transition shrink-0"
          >
            Change Password
          </button>
        </div>
      )}

      {/* Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Terminal className="w-5 h-5 text-emerald-400" />
            <span>AI Command Center</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Issue natural language instructions to configure, launch, and re-route surveillance tasks.
          </p>
        </div>
      </div>

      {/* Monitoring Profiles One-Click Quick Activation Bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Sliders className="w-3.5 h-3.5 text-indigo-400" />
            Quick Presets / Monitoring Profiles (Routes to Approval Gate)
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {profiles.map((p) => {
            const isCrowd = p.modules?.includes('crowd_monitoring');
            const isEnv = p.modules?.includes('environment_monitoring');
            const isSecurity = p.modules?.includes('security_monitoring');
            const isUniversal = p.modules?.includes('universal_vlm_monitor');

            return (
              <button
                key={p.id}
                type="button"
                onClick={() => handleActivateProfile(p.id)}
                disabled={profileLoading}
                className="text-left p-3.5 rounded-xl border border-dark-800 bg-dark-900/90 hover:border-indigo-500/50 hover:bg-dark-850 transition group flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-xs text-slate-200 group-hover:text-indigo-300 transition">
                      {isUniversal && '👁️ '}
                      {isCrowd && '🛡️ '}
                      {isEnv && '🔥 '}
                      {isSecurity && '🚨 '}
                      {p.name}
                    </span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-dark-800 text-slate-400">
                      {p.domain}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                    {p.description}
                  </p>
                </div>
                <div className="mt-3 pt-2 border-t border-dark-800/80 flex items-center justify-between text-[10px] font-mono text-slate-400 group-hover:text-indigo-400">
                  <span>Activate Mode</span>
                  <ArrowRight className="w-3 h-3 group-hover:translate-x-1 transition-transform" />
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Command Input Box */}
      <div className="bg-dark-900 border border-dark-800 rounded-2xl p-6 shadow-2xl relative">
        <form onSubmit={handleSendCommand} className="space-y-4">
          <div className="relative">
            <textarea
              rows={3}
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="e.g. Monitor this camera for crowd density, or 'restricted area intrusion monitor karo'..."
              className="w-full p-4 pr-24 bg-dark-950 border border-dark-700 rounded-xl text-sm text-white placeholder-slate-400 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/40 resize-none font-mono"
            />

            {/* Mic and Action buttons inside input */}
            <div className="absolute right-3 bottom-3 flex items-center gap-2">
              <button
                type="button"
                onClick={toggleVoiceInput}
                className={`p-2.5 rounded-xl border transition-all ${
                  isListening
                    ? 'bg-rose-500/20 border-rose-500 text-rose-400 animate-pulse'
                    : 'bg-dark-800 border-dark-700 text-slate-400 hover:text-white'
                }`}
                title="Browser Voice Input"
              >
                {isListening ? <Mic className="w-4 h-4" /> : <MicOff className="w-4 h-4" />}
              </button>

              <button
                type="submit"
                disabled={loading || !command.trim()}
                className="px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-dark-950 font-semibold text-xs tracking-wide transition-all shadow-md shadow-emerald-950 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
              >
                {loading ? 'Analyzing...' : (
                  <>
                    <span>Submit</span>
                    <Sparkles className="w-3.5 h-3.5" />
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Example Command Chips */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">Suggestions:</span>
            {exampleChips.map((chip, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setCommand(chip)}
                className="px-2.5 py-1 rounded-lg bg-dark-800/80 hover:bg-dark-750 border border-dark-700 text-[11px] text-slate-300 hover:text-emerald-300 transition-colors font-mono"
              >
                {chip}
              </button>
            ))}
          </div>
        </form>
      </div>

      {/* Plan Approval Gate Result Card */}
      {planResult && (
        <div className="border border-dark-750 bg-dark-900 rounded-2xl p-6 space-y-6 shadow-2xl relative overflow-hidden animate-fadeIn">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-dark-800 pb-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                <Shield className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <span>Plan Approval Gate</span>
                  <span className="text-xs px-2 py-0.5 rounded-full font-mono bg-dark-800 text-cyan-300 border border-dark-700">
                    ID #{planResult.plan_id || 'preview'}
                  </span>
                </h3>
                <p className="text-xs text-slate-400 font-mono">
                  Intent: <span className="text-emerald-400 font-semibold">{planResult.plan?.intent}</span>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-slate-400">Confidence:</span>
              <span className="font-mono text-xs font-bold text-cyan-400 px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-800">
                {(planResult.explanation?.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>

          {/* Blocked Safety Violation */}
          {planResult.status === 'blocked' ? (
            <div className="p-5 rounded-xl bg-rose-500/10 border border-rose-500/30 space-y-2">
              <div className="flex items-center gap-2 text-rose-400 font-bold text-sm">
                <AlertOctagon className="w-5 h-5" />
                <span>Command Blocked by OmniSense Safety Guardrails</span>
              </div>
              <p className="text-xs text-rose-300 leading-relaxed font-mono">
                {planResult.explanation?.safety_reason || 'Request violates strict privacy and ethical policies.'}
              </p>
            </div>
          ) : (
            <div className="space-y-5">
              {/* What I Understood & Modules */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 rounded-xl bg-dark-950/80 border border-dark-800 space-y-1">
                  <span className="text-[10px] font-mono uppercase text-slate-400">Natural Intent</span>
                  <p className="text-xs text-slate-200 font-medium">
                    {planResult.explanation?.what_i_understood}
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-dark-950/80 border border-dark-800 space-y-1">
                  <span className="text-[10px] font-mono uppercase text-slate-400">Modules Selected</span>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {planResult.plan.modules?.map((m) => (
                      <span key={m} className="px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-mono">
                        {m}
                      </span>
                    ))}
                  </div>
                  <p className="text-[10px] text-slate-400 mt-2 font-mono">Source: {planResult.plan.source}</p>
                </div>

                <div className="p-4 rounded-xl bg-dark-950/80 border border-dark-800 space-y-1">
                  <span className="text-[10px] font-mono uppercase text-slate-400">Agent Reasoning</span>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {planResult.explanation?.why}
                  </p>
                </div>
              </div>

              {/* Zone Editor Canvas (When Security Monitoring is active) */}
              {isSecurityPlan && (
                <div className="p-4 rounded-xl bg-dark-950/80 border border-indigo-500/30 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-indigo-300 font-mono flex items-center gap-1.5">
                      <Maximize2 className="w-4 h-4 text-indigo-400" />
                      Restricted Zone Spatial Boundary Editor:
                    </span>
                    <span className="text-[11px] font-mono text-slate-400">
                      Coordinates: [{zoneRect.x1.toFixed(2)}, {zoneRect.y1.toFixed(2)}] &rarr; [{zoneRect.x2.toFixed(2)}, {zoneRect.y2.toFixed(2)}]
                    </span>
                  </div>

                  {/* Interactive Visual Canvas Box */}
                  <div className="relative aspect-video max-h-56 w-full bg-slate-950 rounded-lg border border-slate-800 overflow-hidden flex items-center justify-center">
                    <div className="absolute inset-0 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:16px_16px] opacity-40" />

                    {/* Zone rectangle overlay */}
                    <div
                      className="absolute border-2 border-dashed border-red-500 bg-red-500/20 rounded flex items-center justify-center transition-all pointer-events-none"
                      style={{
                        left: `${zoneRect.x1 * 100}%`,
                        top: `${zoneRect.y1 * 100}%`,
                        width: `${(zoneRect.x2 - zoneRect.x1) * 100}%`,
                        height: `${(zoneRect.y2 - zoneRect.y1) * 100}%`
                      }}
                    >
                      <span className="text-[10px] font-mono font-bold text-red-300 bg-black/60 px-1.5 py-0.5 rounded">
                        RESTRICTED PERIMETER
                      </span>
                    </div>

                    <div className="absolute bottom-2 left-2 text-[10px] font-mono text-slate-500">
                      Camera Stream Canvas Overlay (Normalized 0.0 - 1.0)
                    </div>
                  </div>

                  {/* Sliders for fine-tuning */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                    <div>
                      <label className="text-[10px] text-slate-400 block font-mono">X-Left (Min)</label>
                      <input
                        type="range"
                        min="0"
                        max="0.9"
                        step="0.05"
                        value={zoneRect.x1}
                        onChange={(e) => setZoneRect(prev => ({ ...prev, x1: Math.min(parseFloat(e.target.value), prev.x2 - 0.1) }))}
                        className="w-full accent-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-slate-400 block font-mono">X-Right (Max)</label>
                      <input
                        type="range"
                        min="0.1"
                        max="1"
                        step="0.05"
                        value={zoneRect.x2}
                        onChange={(e) => setZoneRect(prev => ({ ...prev, x2: Math.max(parseFloat(e.target.value), prev.x1 + 0.1) }))}
                        className="w-full accent-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-slate-400 block font-mono">Y-Top (Min)</label>
                      <input
                        type="range"
                        min="0"
                        max="0.9"
                        step="0.05"
                        value={zoneRect.y1}
                        onChange={(e) => setZoneRect(prev => ({ ...prev, y1: Math.min(parseFloat(e.target.value), prev.y2 - 0.1) }))}
                        className="w-full accent-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-slate-400 block font-mono">Y-Bottom (Max)</label>
                      <input
                        type="range"
                        min="0.1"
                        max="1"
                        step="0.05"
                        value={zoneRect.y2}
                        onChange={(e) => setZoneRect(prev => ({ ...prev, y2: Math.max(parseFloat(e.target.value), prev.y1 + 0.1) }))}
                        className="w-full accent-indigo-500"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Editable Rules Panel */}
              <div className="p-4 rounded-xl bg-dark-950/50 border border-dark-800 space-y-3">
                <span className="text-xs font-semibold text-slate-200 font-mono flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-emerald-400" />
                  <span>Configure Runtime Thresholds & Duration:</span>
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  {editableRules.person_threshold !== undefined && (
                    <div>
                      <label className="block text-[11px] text-slate-400 font-mono mb-1">Person Limit (Overcrowding)</label>
                      <input
                        type="number"
                        min="1"
                        max="200"
                        value={editableRules.person_threshold}
                        onChange={(e) => setEditableRules({ ...editableRules, person_threshold: parseInt(e.target.value) || 1 })}
                        className="w-full px-3 py-1.5 bg-dark-900 border border-dark-700 rounded-lg text-white font-mono"
                      />
                    </div>
                  )}

                  {editableRules.gas_threshold !== undefined && (
                    <div>
                      <label className="block text-[11px] text-slate-400 font-mono mb-1">Gas Threshold (ppm)</label>
                      <input
                        type="number"
                        min="50"
                        max="5000"
                        value={editableRules.gas_threshold}
                        onChange={(e) => setEditableRules({ ...editableRules, gas_threshold: parseFloat(e.target.value) || 400 })}
                        className="w-full px-3 py-1.5 bg-dark-900 border border-dark-700 rounded-lg text-white font-mono"
                      />
                    </div>
                  )}

                  <div>
                    <label className="block text-[11px] text-slate-400 font-mono mb-1">Duration (Minutes, optional)</label>
                    <input
                      type="number"
                      min="1"
                      max="1440"
                      placeholder="Indefinite"
                      value={editableRules.duration_minutes || ''}
                      onChange={(e) => setEditableRules({ ...editableRules, duration_minutes: parseInt(e.target.value) || null })}
                      className="w-full px-3 py-1.5 bg-dark-900 border border-dark-700 rounded-lg text-white font-mono"
                    />
                  </div>
                </div>
              </div>

              {/* Action Approval Gate */}
              <div className="pt-3 border-t border-dark-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <span className="text-xs text-amber-400 font-mono flex items-center gap-1.5">
                  <Clock className="w-4 h-4 shrink-0" />
                  <span>Approval Required: Autonomous surveillance will not start until approved.</span>
                </span>

                <div className="flex items-center gap-3">
                  <button
                    onClick={() => handleApprovePlan(false)}
                    disabled={actionLoading || !canOperate}
                    className="px-4 py-2 rounded-xl bg-dark-800 hover:bg-dark-750 text-slate-300 text-xs font-semibold border border-dark-700 transition-colors flex items-center gap-1.5"
                  >
                    <XCircle className="w-4 h-4 text-rose-400" />
                    <span>Reject</span>
                  </button>

                  <button
                    onClick={() => handleApprovePlan(true)}
                    disabled={actionLoading || !canOperate}
                    className="px-5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-dark-950 text-xs font-bold transition-all shadow-lg shadow-emerald-950 flex items-center gap-1.5"
                  >
                    <CheckCircle className="w-4 h-4" />
                    <span>Approve & Start Monitoring</span>
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Active Tasks Panel */}
      <div className="p-6 rounded-2xl bg-dark-900/80 border border-dark-800 space-y-4">
        <div className="flex items-center justify-between border-b border-dark-800 pb-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Activity className="w-4 h-4 text-emerald-400" />
            <span>Currently Active Monitoring Tasks ({activeTasks.length})</span>
          </h2>
        </div>

        {activeTasks.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {activeTasks.map((t) => (
              <div key={t.id} className="p-4 rounded-xl border border-dark-750 bg-dark-950/80 flex items-center justify-between gap-4">
                <div className="space-y-1">
                  <span className="font-mono font-bold text-emerald-400 text-xs uppercase tracking-wider">
                    {t.plugin_name.replace('_', ' ')}
                  </span>
                  <p className="text-xs text-slate-300">Target: <span className="font-mono text-cyan-400">{t.target_source}</span></p>
                  <p className="text-[10px] text-slate-400 font-mono">
                    Started: {t.started_at ? new Date(t.started_at).toLocaleTimeString() : 'Active'}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => navigate('/live')}
                    className="px-3 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-mono flex items-center gap-1.5 transition-colors"
                  >
                    <Video className="w-3.5 h-3.5 text-emerald-400" />
                    <span>View Live Stream &rarr;</span>
                  </button>

                  {canOperate && (
                    <button
                      onClick={() => handleStopTask(t.id)}
                      className="px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-xs font-mono flex items-center gap-1.5 transition-colors"
                    >
                      <Square className="w-3.5 h-3.5 fill-current" />
                      <span>Stop</span>
                    </button>
                  )}
                </div>

              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-400 py-3 font-mono">
            No active monitoring tasks. Enter an instruction or select a profile above to initialize one.
          </p>
        )}
      </div>

      {/* Change Password Modal */}
      {showPasswordModal && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <KeyRound className="w-4 h-4 text-amber-400" />
                Change Administrator Password
              </h3>
              <button
                onClick={() => setShowPasswordModal(false)}
                className="text-slate-400 hover:text-slate-200 text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleChangePassword} className="space-y-3">
              <div>
                <label className="text-xs text-slate-400 block mb-1">Current Password</label>
                <input
                  type="password"
                  required
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  placeholder="admin123"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                />
              </div>

              <div>
                <label className="text-xs text-slate-400 block mb-1">New Secure Password</label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter at least 6 characters"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                />
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowPasswordModal(false)}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={changingPassword}
                  className="px-4 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition"
                >
                  {changingPassword ? 'Updating...' : 'Save New Password'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default CommandCenter;
