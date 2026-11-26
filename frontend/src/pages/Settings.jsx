
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
  Info,
  LogOut,
  Activity,
  Server,
  LockKeyhole,
  Users,
  Clock,
  Wifi,
} from 'lucide-react';

import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';

const initialDefaults = {
  crowdThreshold: 4,
  cooldown: 30,
  inferenceFPS: 10,
  gasThreshold: 500,
  temperatureThreshold: 40,
  heartbeat: 30,
};

function SectionHeader({ icon: Icon, title, description }) {
  return (
    <div className="flex items-start gap-3 mb-6">
      <div className="p-2.5 rounded-xl bg-indigo-50 text-indigo-600">
        <Icon size={19} />
      </div>

      <div>
        <h2 className="text-sm font-bold text-slate-800">
          {title}
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          {description}
        </p>
      </div>
    </div>
  );
}

function ThresholdInput({ label, value, unit, onChange, min = 1, step = 1 }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500 mb-2">
        {label}
      </label>

      <div className="relative">
        <input
          type="number"
          min={min}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 pr-14 text-sm font-semibold text-slate-800 outline-none transition focus:border-indigo-400 focus:bg-white focus:ring-2 focus:ring-indigo-100"
        />

        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">
          {unit}
        </span>
      </div>
    </div>
  );
}

const infrastructure = [
  {
    name: 'API Server',
    version: 'FastAPI 0.115',
    icon: Server,
  },
  {
    name: 'Vision Engine',
    version: 'YOLOv8n (0.35 conf)',
    icon: EyeOff,
  },
  {
    name: 'MQTT Broker',
    version: 'Mosquitto (1883)',
    icon: Radio,
  },
  {
    name: 'Database',
    version: 'SQLite WAL',
    icon: Database,
  },
];

const privacyFeatures = [
  {
    title: 'Zero Face Recognition',
    description:
      'No face embeddings, landmarks, or identity trackers are instantiated in any vision module.',
    icon: EyeOff,
  },
  {
    title: 'Ephemeral Buffer',
    description:
      'Raw video frames are processed in-memory and immediately discarded. Only anonymized bounding boxes are retained.',
    icon: Database,
  },
  {
    title: 'Approval Gate',
    description:
      'Every LLM-generated monitoring plan requires explicit human approval before background tasks launch.',
    icon: LockKeyhole,
  },
  {
    title: 'Human-in-the-Loop Incidents',
    description:
      'AI detections enter pending_review and require human sign-off before being treated as confirmed.',
    icon: Users,
  },
];

export default function Settings() {
  const { user, logout } = useAuth();
  const { addToast } = useToast();

  const [settings, setSettings] = useState(() => {
    try {
      const stored = localStorage.getItem('omnisense-settings');
      return stored
        ? { ...initialDefaults, ...JSON.parse(stored) }
        : initialDefaults;
    } catch {
      return initialDefaults;
    }
  });

  const [savedSettings, setSavedSettings] = useState(false);

  const updateSetting = (key, value) => {
    setSettings((prev) => ({
      ...prev,
      [key]: value,
    }));

    setSavedSettings(false);
  };

  const handleSaveDefaults = (e) => {
    e.preventDefault();

    if (Object.values(settings).some(
      (value) => !Number.isFinite(value) || value <= 0
    )) {
      addToast('Please enter valid positive values', 'error');
      return;
    }

    localStorage.setItem(
      'omnisense-settings',
      JSON.stringify(settings)
    );

    setSavedSettings(true);
    addToast('Runtime operational preferences saved', 'success');
  };

  const username = user?.username || 'Operator';

  return (
    <div className="w-full min-h-screen space-y-7 pb-10">

      {/* PAGE HEADER */}
      <div className="flex flex-wrap items-center justify-between gap-4">

        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
              <SettingsIcon size={22} />
            </div>

            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              System Settings
            </h1>
          </div>

          <p className="text-sm text-slate-500 mt-2">
            Manage platform configurations, operator credentials,
            and privacy governance.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-100">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span className="text-xs font-semibold text-emerald-700">
              System Online
            </span>
          </div>

          <button
            onClick={logout}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-slate-200 bg-white text-sm font-medium text-slate-600 hover:text-rose-600 hover:border-rose-200 transition"
          >
            <LogOut size={16} />
            Sign Out
          </button>
        </div>
      </div>

      {/* OVERVIEW CARDS */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">

        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <div className="flex justify-between items-center">
            <span className="text-xs font-medium text-slate-500">
              Authenticated Operator
            </span>
            <User size={18} className="text-indigo-500" />
          </div>

          <h3 className="text-xl font-bold text-slate-900 mt-4">
            {username}
          </h3>

          <p className="text-xs text-slate-400 mt-1">
            {user?.role?.toUpperCase() || 'USER'}
          </p>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <div className="flex justify-between items-center">
            <span className="text-xs font-medium text-slate-500">
              Crowd Threshold
            </span>
            <Users size={18} className="text-indigo-500" />
          </div>

          <h3 className="text-xl font-bold text-slate-900 mt-4">
            {settings.crowdThreshold} Persons
          </h3>

          <p className="text-xs text-slate-400 mt-1">
            Overcrowding detection limit
          </p>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <div className="flex justify-between items-center">
            <span className="text-xs font-medium text-slate-500">
              Inference Target
            </span>
            <Activity size={18} className="text-indigo-500" />
          </div>

          <h3 className="text-xl font-bold text-slate-900 mt-4">
            ~{settings.inferenceFPS} FPS
          </h3>

          <p className="text-xs text-slate-400 mt-1">
            Vision processing target
          </p>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <div className="flex justify-between items-center">
            <span className="text-xs font-medium text-slate-500">
              Privacy Architecture
            </span>
            <Shield size={18} className="text-emerald-500" />
          </div>

          <h3 className="text-xl font-bold text-slate-900 mt-4">
            Protected
          </h3>

          <p className="text-xs text-slate-400 mt-1">
            Privacy safeguards configured
          </p>
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

        {/* LEFT COLUMN */}
        <div className="xl:col-span-2 space-y-6">

          {/* MONITORING CONFIGURATION */}
          <form
            onSubmit={handleSaveDefaults}
            className="bg-white border border-slate-200 rounded-xl p-6 sm:p-7 shadow-sm"
          >
            <SectionHeader
              icon={Sliders}
              title="Monitoring Configuration"
              description="Configure default algorithm and environmental sensor thresholds."
            />

            {/* CROWD MONITOR */}
            <div className="mb-7">
              <div className="flex items-center gap-2 mb-5">
                <Cpu size={17} className="text-indigo-600" />
                <h3 className="text-sm font-semibold text-slate-800">
                  Crowd Monitoring
                </h3>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                <ThresholdInput
                  label="Overcrowding Threshold"
                  value={settings.crowdThreshold}
                  unit="Persons"
                  onChange={(v) => updateSetting('crowdThreshold', v)}
                />

                <ThresholdInput
                  label="Cooldown Period"
                  value={settings.cooldown}
                  unit="Seconds"
                  onChange={(v) => updateSetting('cooldown', v)}
                />

                <ThresholdInput
                  label="Inference Target"
                  value={settings.inferenceFPS}
                  unit="FPS"
                  onChange={(v) => updateSetting('inferenceFPS', v)}
                />
              </div>
            </div>

            <div className="border-t border-slate-100 pt-7">

              {/* ENVIRONMENTAL SENSORS */}
              <div className="flex items-center gap-2 mb-5">
                <Radio size={17} className="text-amber-500" />
                <h3 className="text-sm font-semibold text-slate-800">
                  Environmental Sensors
                </h3>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                <ThresholdInput
                  label="Hazardous Gas Alert"
                  value={settings.gasThreshold}
                  unit="PPM"
                  onChange={(v) => updateSetting('gasThreshold', v)}
                />

                <ThresholdInput
                  label="High Temperature Alert"
                  value={settings.temperatureThreshold}
                  unit="°C"
                  step={0.1}
                  onChange={(v) => updateSetting('temperatureThreshold', v)}
                />

                <ThresholdInput
                  label="Watchdog Heartbeat"
                  value={settings.heartbeat}
                  unit="Seconds"
                  onChange={(v) => updateSetting('heartbeat', v)}
                />
              </div>
            </div>

            {/* SAVE */}
            <div className="flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 mt-7 pt-5">

              <p className="text-xs text-slate-400">
                Defaults are stored locally in this browser.
              </p>

              <button
                type="submit"
                className="flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition shadow-sm"
              >
                {savedSettings ? (
                  <>
                    <CheckCircle2 size={16} />
                    Settings Saved
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={16} />
                    Save System Defaults
                  </>
                )}
              </button>
            </div>
          </form>

          {/* PRIVACY ARCHITECTURE */}
          <section className="bg-white border border-slate-200 rounded-xl p-6 sm:p-7 shadow-sm">

            <SectionHeader
              icon={Shield}
              title="Privacy & Governance"
              description="Architectural safeguards protecting users across all vision monitoring tasks."
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

              {privacyFeatures.map((feature) => {
                const Icon = feature.icon;

                return (
                  <div
                    key={feature.title}
                    className="flex gap-3 p-4 rounded-xl border border-slate-100 bg-slate-50/70 hover:bg-white hover:border-indigo-100 transition"
                  >
                    <div className="w-9 h-9 shrink-0 flex items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                      <Icon size={18} />
                    </div>

                    <div>
                      <h3 className="text-sm font-semibold text-slate-800">
                        {feature.title}
                      </h3>

                      <p className="text-xs text-slate-500 leading-relaxed mt-1.5">
                        {feature.description}
                      </p>
                    </div>
                  </div>
                );
              })}

            </div>
          </section>

        </div>

        {/* RIGHT COLUMN */}
        <div className="space-y-6">

          {/* OPERATOR PROFILE */}
          <section className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">

            <SectionHeader
              icon={User}
              title="Operator Profile"
              description="Authenticated account information."
            />

            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center text-xl font-bold text-indigo-600">
                {username.charAt(0).toUpperCase()}
              </div>

              <div className="min-w-0">
                <h3 className="font-semibold text-slate-900">
                  {username}
                </h3>

                <p className="text-xs text-slate-400 truncate">
                  {user?.email}
                </p>
              </div>
            </div>

            <div className="border-t border-slate-100 mt-6 pt-5 space-y-4">

              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-500">Assigned Role</span>
                <span className="text-xs font-bold text-indigo-600 uppercase">
                  {user?.role || 'USER'}
                </span>
              </div>

              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-500">Session Status</span>

                <span className="flex items-center gap-2 text-xs font-medium text-emerald-600">
                  <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  Active JWT
                </span>
              </div>

            </div>
          </section>

          {/* INFRASTRUCTURE */}
          <section className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">

            <SectionHeader
              icon={Database}
              title="Runtime Infrastructure"
              description="Technology stack powering OmniSense AI."
            />

            <div className="space-y-4">
              {infrastructure.map((item) => {
                const Icon = item.icon;

                return (
                  <div
                    key={item.name}
                    className="flex items-center gap-3"
                  >
                    <div className="w-10 h-10 shrink-0 flex items-center justify-center rounded-lg bg-slate-50 border border-slate-100 text-slate-500">
                      <Icon size={18} />
                    </div>

                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-semibold text-slate-800">
                        {item.name}
                      </h3>

                      <p className="text-xs text-slate-400 mt-0.5">
                        {item.version}
                      </p>
                    </div>

                    <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                  </div>
                );
              })}
            </div>
          </section>

          {/* SYSTEM INFORMATION */}
          <section className="bg-indigo-50/60 border border-indigo-100 rounded-xl p-5">

            <div className="flex items-center gap-2 text-indigo-700">
              <Info size={17} />
              <h3 className="text-sm font-semibold">
                Platform Information
              </h3>
            </div>

            <p className="text-xs text-slate-500 leading-relaxed mt-3">
              OmniSense AI uses privacy-first computer vision
              architecture with human-supervised monitoring
              and local data processing.
            </p>

            <div className="flex items-center gap-2 mt-4 text-xs text-indigo-600 font-medium">
              <Wifi size={14} />
              Local Deployment
            </div>
          </section>

        </div>
      </div>

      {/* FOOTER */}
      <footer className="border-t border-slate-200 pt-5 flex flex-wrap justify-between gap-3 text-xs text-slate-400">
        <span>© 2026 OmniSense AI</span>
        <span>Intelligent Monitoring · Privacy First</span>
      </footer>

    </div>
  );
}
