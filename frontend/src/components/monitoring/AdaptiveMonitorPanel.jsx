/**
 * AdaptiveMonitorPanel.jsx
 *
 * Context-Adaptive Monitoring Widget Panel (Sentinel Light Theme).
 * Reads the `active_metrics` list from WebSocket payload
 * and dynamically renders only the relevant charts and indicators
 * for the current monitoring goal beneath the live video feed.
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine
} from 'recharts';
import {
  Thermometer, Flame, Droplets, Activity,
  Users, ShieldAlert, AlertTriangle, CheckCircle2,
  Brain, Gauge, Clock
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Individual Metric Widget Components (Sentinel Light Palette)
// ---------------------------------------------------------------------------

const TimeSeriesChart = React.memo(({ title, icon: Icon, data, dataKey, color, unit, referenceValue, referenceLabel }) => (
  <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-sm space-y-3">
    <div className="flex items-center justify-between border-b border-slate-100 pb-3">
      <h3 className="text-xs font-mono font-semibold text-slate-800 uppercase tracking-wider flex items-center gap-2">
        {Icon && <Icon className="w-4 h-4" style={{ color }} />}
        <span>{title}</span>
      </h3>
      {referenceValue !== undefined && (
        <span className="text-[11px] font-mono font-semibold" style={{ color }}>
          Threshold: {referenceValue}{unit}
        </span>
      )}
    </div>
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="time" stroke="#94a3b8" tick={{ fontSize: 10 }} />
          <YAxis stroke="#94a3b8" tick={{ fontSize: 10 }} />
          <Tooltip
            contentStyle={{
              backgroundColor: '#ffffff',
              borderColor: '#e2e8f0',
              borderRadius: '8px',
              fontSize: '11px',
              color: '#0f172a',
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)'
            }}
          />
          {referenceValue !== undefined && (
            <ReferenceLine
              y={referenceValue}
              stroke={color}
              strokeDasharray="4 4"
              label={{ value: referenceLabel || `${referenceValue}${unit}`, fill: color, fontSize: 10 }}
            />
          )}
          <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  </div>
));

const StatusCard = React.memo(({ label, value, color, icon: Icon, subtext }) => (
  <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm flex flex-col gap-1">
    <div className="flex items-center gap-1.5 text-slate-500 text-xs mb-1">
      {Icon && <Icon className="w-3.5 h-3.5" style={{ color }} />}
      <span>{label}</span>
    </div>
    <span className="text-xl font-bold font-mono text-slate-900" style={{ color }}>{value}</span>
    {subtext && <p className="text-[10px] text-slate-400 font-mono">{subtext}</p>}
  </div>
));

const RiskGauge = React.memo(({ score, label }) => {
  const pct = Math.min(100, Math.max(0, score || 0));
  const color = pct >= 70 ? '#ef4444' : pct >= 40 ? '#f59e0b' : '#10b981';
  return (
    <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-sm space-y-3">
      <h3 className="text-xs font-mono font-semibold text-slate-800 uppercase tracking-wider flex items-center gap-2">
        <Gauge className="w-4 h-4 text-amber-500" />
        {label || 'Risk Score'}
      </h3>
      <div className="flex flex-col items-center gap-2 py-4">
        <div className="relative w-32 h-16 overflow-hidden">
          <div className="absolute inset-0 rounded-t-full bg-slate-100" />
          <div
            className="absolute bottom-0 left-0 right-0 rounded-t-full transition-all duration-700"
            style={{ height: `${pct}%`, backgroundColor: color, opacity: 0.85 }}
          />
          <div className="absolute inset-0 flex items-end justify-center pb-1">
            <span className="text-2xl font-bold font-mono" style={{ color }}>{pct}%</span>
          </div>
        </div>
        <span className="text-xs font-mono font-semibold" style={{ color }}>
          {pct >= 70 ? 'HIGH RISK' : pct >= 40 ? 'MEDIUM RISK' : 'LOW RISK / NORMAL'}
        </span>
      </div>
    </div>
  );
});

const SafetyStatusCard = React.memo(({ incident_detected, explanation }) => (
  <div className={`p-5 rounded-2xl border shadow-sm flex items-start gap-4 ${
    incident_detected
      ? 'bg-rose-50 border-rose-200 text-rose-900'
      : 'bg-emerald-50 border-emerald-200 text-emerald-900'
  }`}>
    {incident_detected
      ? <AlertTriangle className="w-8 h-8 text-rose-600 flex-shrink-0 mt-0.5" />
      : <CheckCircle2 className="w-8 h-8 text-emerald-600 flex-shrink-0 mt-0.5" />
    }
    <div>
      <p className={`font-bold text-sm ${incident_detected ? 'text-rose-900' : 'text-emerald-900'}`}>
        {incident_detected ? 'Anomaly / Incident Flagged' : 'Scene Status: Normal'}
      </p>
      <p className="text-xs text-slate-600 mt-1">{explanation || 'AI is actively monitoring the scene.'}</p>
    </div>
  </div>
));

const IncidentTimeline = React.memo(({ events }) => (
  <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-sm space-y-3">
    <h3 className="text-xs font-mono font-semibold text-slate-800 uppercase tracking-wider flex items-center gap-2">
      <Clock className="w-4 h-4 text-indigo-500" />
      Incident Timeline
    </h3>
    <div className="space-y-2 max-h-48 overflow-y-auto">
      {events.length === 0 ? (
        <p className="text-xs text-slate-400 font-mono">No incidents recorded yet.</p>
      ) : (
        events.map((ev, i) => (
          <div key={i} className="flex items-start gap-2.5 text-xs p-2 rounded-lg bg-slate-50 border border-slate-100">
            <span className="text-slate-500 font-mono whitespace-nowrap">{ev.time}</span>
            <span className={`font-semibold ${ev.action === 'alarm' ? 'text-rose-600' : 'text-amber-600'}`}>
              {ev.explanation}
            </span>
          </div>
        ))
      )}
    </div>
  </div>
));

const MotionScoreBar = React.memo(({ score }) => {
  const pct = Math.round((score || 0) * 100);
  return (
    <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm">
      <div className="flex items-center gap-1.5 text-slate-600 text-xs mb-2">
        <Activity className="w-3.5 h-3.5 text-blue-500" />
        <span className="font-medium">Motion Activity Score</span>
        <span className="ml-auto text-blue-600 font-mono font-bold">{pct}%</span>
      </div>
      <div className="w-full h-2 rounded-full bg-slate-100">
        <div
          className="h-2 rounded-full bg-blue-500 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
});

// ---------------------------------------------------------------------------
// Main Adaptive Panel (Two-Speed Architecture: Fast HUD + 1 Hz Slow Chart)
// ---------------------------------------------------------------------------

const AdaptiveMonitorPanel = ({ wsData, goal, sideBySide = false }) => {
  const [history, setHistory] = useState([]);
  const [incidentLog, setIncidentLog] = useState([]);
  const historyRef = useRef([]);
  const lastChartTickRef = useRef(0);
  const lastIncidentKeyRef = useRef('');

  useEffect(() => {
    if (!wsData) return;

    const nowMs = Date.now();
    const now = new Date(nowMs);
    const timeLabel = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`;

    // Slow Lane (1 Hz): Only update Recharts SVG history once per second
    if (nowMs - lastChartTickRef.current >= 1000) {
      lastChartTickRef.current = nowMs;
      const point = {
        time: timeLabel,
        person_count: wsData.metrics?.person_count ?? null,
        temperature: wsData.metrics?.temperature ?? null,
        gas_level: wsData.metrics?.gas_level ?? null,
        humidity: wsData.metrics?.humidity ?? null,
        motion_score: wsData.motion_score ? Math.round(wsData.motion_score * 100) : null,
        risk_score: wsData.metrics?.risk_score ?? null,
      };

      const updated = [...historyRef.current, point].slice(-30);
      historyRef.current = updated;
      setHistory(updated);
    }

    if (wsData.incident_detected) {
      const incidentKey = `${timeLabel}:${wsData.explanation}`;
      if (incidentKey !== lastIncidentKeyRef.current) {
        lastIncidentKeyRef.current = incidentKey;
        const incident = {
          time: timeLabel,
          explanation: wsData.explanation,
          action: wsData.action_required,
        };
        setIncidentLog(prev => [incident, ...prev].slice(0, 50));
      }
    }
  }, [wsData]);

  if (!wsData) {
    return (
      <div className="flex items-center justify-center h-32 text-slate-400 text-sm bg-white border border-slate-200 rounded-2xl">
        <Brain className="w-5 h-5 mr-2 animate-pulse text-indigo-500" />
        Waiting for universal monitoring data...
      </div>
    );
  }

  const active = wsData.active_metrics || [];
  const metrics = wsData.metrics || {};

  return (
    <div className="space-y-5">
      {/* Safety / Incident status */}
      <SafetyStatusCard
        incident_detected={wsData.incident_detected}
        explanation={wsData.explanation}
      />

      {/* Quick stat cards row */}
      <div className={`grid gap-3 ${sideBySide ? 'grid-cols-2' : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4'}`}>
        {active.includes('person_count') && (
          <StatusCard label="Persons Observed" icon={Users}
            value={metrics.person_count ?? '—'} color="#4f46e5"
            subtext="AI visual count" />
        )}
        {active.includes('temperature') && metrics.temperature != null && (
          <StatusCard label="Temperature" icon={Thermometer}
            value={`${metrics.temperature}°C`}
            color={metrics.temperature > 32 ? '#ef4444' : '#d97706'}
            subtext="DHT22 Arduino" />
        )}
        {active.includes('gas_level') && metrics.gas_level != null && (
          <StatusCard label="Gas / Smoke" icon={Flame}
            value={`${metrics.gas_level} ppm`}
            color={metrics.gas_level > 400 ? '#ef4444' : '#059669'}
            subtext="MQ-2 sensor" />
        )}
        {active.includes('humidity') && metrics.humidity != null && (
          <StatusCard label="Humidity" icon={Droplets}
            value={`${metrics.humidity}%`} color="#0891b2"
            subtext="DHT22 sensor" />
        )}
        {active.includes('pir_motion') && (
          <StatusCard label="PIR Motion" icon={Activity}
            value={metrics.motion_detected ? 'Active' : 'Clear'}
            color={metrics.motion_detected ? '#059669' : '#64748b'}
            subtext="Digital hardware pin" />
        )}
        {active.includes('cpu_percent') && metrics.cpu_percent != null && (
          <StatusCard label="Host CPU" icon={Activity}
            value={`${metrics.cpu_percent}%`}
            color={metrics.cpu_percent > 85 ? '#ef4444' : '#2563eb'}
            subtext="Verified OS load" />
        )}
        {active.includes('memory_percent') && metrics.memory_percent != null && (
          <StatusCard label="Host RAM" icon={Activity}
            value={`${metrics.memory_percent}%`}
            color={metrics.memory_percent > 90 ? '#ef4444' : '#0891b2'}
            subtext="System memory" />
        )}
        {active.includes('battery_percent') && metrics.battery_percent != null && (
          <StatusCard label="Battery" icon={Activity}
            value={`${metrics.battery_percent}%`}
            color={metrics.battery_percent < 20 ? '#ef4444' : '#059669'}
            subtext="Laptop power" />
        )}
      </div>

      {/* Motion score bar */}
      {active.includes('motion_score') && (
        <MotionScoreBar score={wsData.motion_score} />
      )}

      {/* Risk Gauge */}
      {active.includes('risk_score') && (
        <RiskGauge score={metrics.risk_score} label="Behavioral Risk Score" />
      )}

      {/* Time-series charts — dynamically rendered based on goal */}
      <div className={`grid gap-5 ${sideBySide ? 'grid-cols-1' : 'grid-cols-1 lg:grid-cols-2'}`}>
        {active.includes('person_count') && (
          <TimeSeriesChart
            title="Person Count Over Time" icon={Users}
            data={history} dataKey="person_count"
            color="#4f46e5" unit="" />
        )}
        {active.includes('temperature') && (
          <TimeSeriesChart
            title="Temperature (°C)" icon={Thermometer}
            data={history} dataKey="temperature"
            color="#d97706" unit="°C"
            referenceValue={32} referenceLabel="MAX 32°C" />
        )}
        {active.includes('gas_level') && (
          <TimeSeriesChart
            title="Gas / Smoke (ppm)" icon={Flame}
            data={history} dataKey="gas_level"
            color="#ef4444" unit=" ppm"
            referenceValue={400} referenceLabel="HAZARD 400 ppm" />
        )}
        {active.includes('motion_score') && (
          <TimeSeriesChart
            title="Motion Activity (%)" icon={Activity}
            data={history} dataKey="motion_score"
            color="#2563eb" unit="%" />
        )}
      </div>

      {/* Incident Timeline */}
      {active.includes('incident_timeline') && (
        <IncidentTimeline events={incidentLog} />
      )}
    </div>
  );
};

export default AdaptiveMonitorPanel;
