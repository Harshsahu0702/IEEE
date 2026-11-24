import React, { useState } from 'react';
import {
  Settings as SettingsIcon,
  User,
  Shield,
  EyeOff,
  Cpu,
  Radio,
  Sliders,
  CheckCircle2,
  Database,
  Info
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';

export default function Settings() {
  const { user, logout } = useAuth();
  const { addToast } = useToast();

  const [savedSettings, setSavedSettings] = useState(false);

  const handleSaveDefaults = (e) => {
    e.preventDefault();
    setSavedSettings(true);
    addToast('Runtime operational preferences saved', 'success');
    setTimeout(() => setSavedSettings(false), 2500);
  };

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
          <SettingsIcon className="w-6 h-6 text-indigo-400" />
          System Settings & Platform Profile
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Review operator credentials, algorithm configurations, and privacy governance rules.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Left Column: User Profile */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
          <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
            <User className="w-4 h-4 text-indigo-400" />
            Authenticated Operator
          </h2>

          <div className="flex items-center gap-3 pt-2">
            <div className="w-12 h-12 rounded-full bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-300 font-bold text-lg">
              {user?.username?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div>
              <div className="text-base font-semibold text-slate-100">{user?.username}</div>
              <div className="text-xs text-slate-400">{user?.email}</div>
            </div>
          </div>

          <div className="pt-3 border-t border-slate-800 space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-400">Assigned Role:</span>
              <span className="font-semibold text-indigo-400 uppercase font-mono">{user?.role}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Session Status:</span>
              <span className="text-emerald-400 flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" /> Active JWT
              </span>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-800">
            <button
              onClick={logout}
              className="w-full py-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-lg text-xs font-semibold transition"
            >
              Sign Out of Session
            </button>
          </div>
        </div>

        {/* Right 2 Columns: Platform Architecture & Privacy Pledge */}
        <div className="md:col-span-2 space-y-6">
          {/* Privacy & Safety Guarantee */}
          <div className="bg-slate-900 border border-indigo-500/30 rounded-xl p-6 space-y-3 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-6 opacity-10">
              <EyeOff className="w-32 h-32 text-indigo-400" />
            </div>
            <div className="flex items-center gap-2 text-indigo-400 font-semibold text-sm">
              <Shield className="w-4 h-4" />
              OmniSense AI Strict Privacy Architecture
            </div>
            <p className="text-xs text-slate-300 leading-relaxed max-w-xl">
              OmniSense AI operates under hard architectural guarantees to safeguard privacy in all vision tasks:
            </p>
            <ul className="text-xs text-slate-400 space-y-1.5 list-disc list-inside">
              <li><strong className="text-slate-200">Zero Face Recognition:</strong> No face embeddings, landmarks, or identity trackers are instantiated in any vision module.</li>
              <li><strong className="text-slate-200">Ephemeral Buffer:</strong> Raw video frames are processed in-memory and immediately discarded. Only anonymized bounding boxes (class: person) are kept.</li>
              <li><strong className="text-slate-200">Approval Gate:</strong> Every LLM-generated monitoring plan requires explicit human approval before background tasks launch.</li>
              <li><strong className="text-slate-200">Human-in-the-Loop Incidents:</strong> AI detections always enter <code className="text-amber-300 font-mono">pending_review</code> and are never treated as confirmed without human sign-off.</li>
            </ul>
          </div>

          {/* Plugin & Threshold Configurations */}
          <form onSubmit={handleSaveDefaults} className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <Sliders className="w-4 h-4 text-indigo-400" />
                Default Monitoring Thresholds
              </h2>
              <span className="text-xs text-slate-500">Editable at plan approval</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1.5">
                <div className="text-slate-300 font-medium flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5 text-indigo-400" /> Crowd Monitor Default
                </div>
                <div className="text-slate-400">Overcrowding Threshold: <strong className="text-slate-200 font-mono">4 persons</strong></div>
                <div className="text-slate-400">Cooldown Period: <strong className="text-slate-200 font-mono">30 seconds</strong></div>
                <div className="text-slate-400">Inference Target: <strong className="text-slate-200 font-mono">~10 FPS</strong></div>
              </div>

              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1.5">
                <div className="text-slate-300 font-medium flex items-center gap-1.5">
                  <Radio className="w-3.5 h-3.5 text-amber-400" /> Environmental Sensor Defaults
                </div>
                <div className="text-slate-400">Hazardous Gas Alert: <strong className="text-slate-200 font-mono">&gt; 500 ppm</strong></div>
                <div className="text-slate-400">High Temp Alert: <strong className="text-slate-200 font-mono">&gt; 40.0 °C</strong></div>
                <div className="text-slate-400">Watchdog Offline: <strong className="text-slate-200 font-mono">30s heartbeat</strong></div>
              </div>
            </div>

            <div className="pt-2 flex items-center justify-end">
              <button
                type="submit"
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition flex items-center gap-1.5"
              >
                {savedSettings ? (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-300" /> Settings Confirmed
                  </>
                ) : (
                  'Save System Defaults'
                )}
              </button>
            </div>
          </form>

          {/* Infrastructure Specs */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-3">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Database className="w-4 h-4 text-indigo-400" />
              Runtime Infrastructure
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                <div className="text-slate-500">API Server</div>
                <div className="text-slate-200 font-mono mt-0.5">FastAPI 0.115</div>
              </div>
              <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                <div className="text-slate-500">Vision Engine</div>
                <div className="text-slate-200 font-mono mt-0.5">YOLOv8n (0.35 conf)</div>
              </div>
              <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                <div className="text-slate-500">MQTT Broker</div>
                <div className="text-slate-200 font-mono mt-0.5">Mosquitto (1883)</div>
              </div>
              <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                <div className="text-slate-500">Database</div>
                <div className="text-slate-200 font-mono mt-0.5">SQLite WAL</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
