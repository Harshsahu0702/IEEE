/**
 * AdaptiveMonitorPanel.jsx
 *
 * Context-Adaptive Monitoring Widget Panel.
 * Reads the `active_metrics` list from WebSocket payload
 * and dynamically renders only the relevant charts and indicators
 * for the current monitoring goal.
 *
 * No hardcoded scenario panels. All widgets are generic and reuse
 * the same data stream from the universal_monitor_update WS message.
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine
} from 'recharts';
import {
  Thermometer, Flame, Droplets, Activity,
  Users, ShieldAlert, AlertTriangle, CheckCircle2,
  Brain, Gauge, Clock
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Individual Metric Widget Components
// ---------------------------------------------------------------------------

const TimeSeriesChart = ({ title, icon: Icon, data, dataKey, color, unit, referenceValue, referenceLabel }) => (
  <div className="p-5 rounded-2xl bg-dark-900 border border-dark-800 space-y-3">
    <div className="flex items-center justify-between border-b border-dark-800 pb-3">
      <h3 className="text-xs font-mono font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
        {Icon && <Icon className="w-4 h-4" style={{ color }} />}
        <span>{title}</span>
      </h3>
      {referenceValue !== undefined && (
        <span className="text-[11px] font-mono" style={{ color }}>
          Threshold: {referenceValue}{unit}
        </span>
      )}
    </div>
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" />
          <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 10 }} />
          <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
          <Tooltip contentStyle={{ backgroundColor: '#0e1117', borderColor: '#283149', borderRadius: '8px', fontSize: '11px' }} />
          {referenceValue !== undefined && (
            <ReferenceLine y={referenceValue} stroke={color} strokeDasharray="4 4"
              label={{ value: referenceLabel || `${referenceValue}${unit}`, fill: color, fontSize: 10 }} />
          )}
          <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  </div>
);

const StatusCard = ({ label, value, color, icon: Icon, subtext }) => (
  <div className="p-4 rounded-xl bg-dark-950 border border-dark-800 flex flex-col gap-1">
    <div className="flex items-center gap-1.5 text-slate-400 text-xs mb-1">
      {Icon && <Icon className="w-3.5 h-3.5" style={{ color }} />}
      <span>{label}</span>
    </div>
    <span className="text-lg font-bold font-mono" style={{ color }}>{value}</span>
    {subtext && <p className="text-[10px] text-slate-400 font-mono">{subtext}</p>}
  </div>
);

const RiskGauge = ({ score, label }) => {
  const pct = Math.min(100, Math.max(0, score || 0));
  const color = pct >= 70 ? '#f43f5e' : pct >= 40 ? '#f59e0b' : '#10b981';
  return (
    <div className="p-5 rounded-2xl bg-dark-900 border border-dark-800 space-y-3">
      <h3 className="text-xs font-mono font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
        <Gauge className="w-4 h-4 text-amber-400" />
        {label || 'Risk Score'}
      </h3>
      <div className="flex flex-col items-center gap-2 py-4">
        <div className="relative w-32 h-16 overflow-hidden">
          <div className="absolute inset-0 rounded-t-full bg-dark-800" />
          <div
            className="absolute bottom-0 left-0 right-0 rounded-t-full transition-all duration-700"
            style={{ height: `${pct}%`, backgroundColor: color, opacity: 0.85 }}
          />
          <div className="absolute inset-0 flex items-end justify-center pb-1">
            <span className="text-2xl font-bold font-mono" style={{ color }}>{pct}%</span>
          </div>
        </div>
        <span className="text-xs text-slate-400 font-mono">
          {pct >= 70 ? 'HIGH RISK' : pct >= 40 ? 'MEDIUM RISK' : 'LOW RISK'}
        </span>
      </div>
    </div>
  );
};

const SafetyStatusCard = ({ incident_detected, explanation }) => (
  <div className={`p-5 rounded-2xl border flex items-start gap-4 ${
    incident_detected
      ? 'bg-rose-950/30 border-rose-800'
      : 'bg-emerald-950/30 border-emerald-800'
  }`}>
    {incident_detected
      ? <AlertTriangle className="w-8 h-8 text-rose-400 flex-shrink-0 mt-0.5" />
      : <CheckCircle2 className="w-8 h-8 text-emerald-400 flex-shrink-0 mt-0.5" />
    }
    <div>
      <p className={`font-semibold text-sm ${incident_detected ? 'text-rose-300' : 'text-emerald-300'}`}>
        {incident_detected ? 'Anomaly Detected' : 'Scene is Safe'}
      </p>
      <p className="text-xs text-slate-400 mt-1">{explanation || 'AI is monitoring the scene.'}</p>
    </div>
  </div>
);

const IncidentTimeline = ({ events }) => (
  <div className="p-5 rounded-2xl bg-dark-900 border border-dark-800 space-y-3">
    <h3 className="text-xs font-mono font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
      <Clock className="w-4 h-4 text-purple-400" />
      Incident Timeline
    </h3>
    <div className="space-y-2 max-h-48 overflow-y-auto">
      {events.length === 0 ? (
        <p className="text-xs text-slate-500 font-mono">No incidents recorded yet.</p>
      ) : (
        events.map((ev, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span className="text-slate-500 font-mono whitespace-nowrap">{ev.time}</span>
            <span className={`font-medium ${ev.action === 'alarm' ? 'text-rose-400' : 'text-amber-400'}`}>
              {ev.explanation}
            </span>
          </div>
        ))
      )}
    </div>
  </div>
);

const MotionScoreBar = ({ score }) => {
  const pct = Math.round((score || 0) * 100);
  return (
    <div className="p-4 rounded-xl bg-dark-950 border border-dark-800">
      <div className="flex items-center gap-1.5 text-slate-400 text-xs mb-2">
        <Activity className="w-3.5 h-3.5 text-blue-400" />
        <span>Motion Activity</span>
        <span className="ml-auto text-blue-400 font-mono">{pct}%</span>
      </div>
      <div className="w-full h-2 rounded-full bg-dark-800">
        <div
          className="h-2 rounded-full bg-blue-500 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main Adaptive Panel
// ---------------------------------------------------------------------------

const AdaptiveMonitorPanel = ({ wsData, goal }) => {
  const [history, setHistory] = useState([]);
  const [incidentLog, setIncidentLog] = useState([]);
  const historyRef = useRef([]);

  useEffect(() => {
    if (!wsData) return;

    // Append time-series data point
    const now = new Date();
    const timeLabel = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`;

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
    setHistory([...updated]);

    // Log incidents
    if (wsData.incident_detected) {
      const incident = {
        time: timeLabel,
        explanation: wsData.explanation,
        action: wsData.action_required,
      };
      setIncidentLog(prev => [incident, ...prev].slice(0, 50));
    }
  }, [wsData]);

  if (!wsData) {
    return (
      <div className="flex items-center justify-center h-32 text-slate-500 text-sm">
        <Brain className="w-5 h-5 mr-2 animate-pulse" />
        Waiting for monitoring data...
      </div>
    );
  }

  const active = wsData.active_metrics || [];
  const metrics = wsData.metrics || {};

  return (
    <div className="space-y-5">
      {/* Goal banner */}
      {goal && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-950/40 border border-indigo-800 text-sm">
          <Brain className="w-4 h-4 text-indigo-400 flex-shrink-0" />
          <span className="text-indigo-200 font-medium">Monitoring: </span>
          <span className="text-slate-300">{goal}</span>
        </div>
      )}

      {/* Safety / Incident status (always shown if data is present) */}
      <SafetyStatusCard
        incident_detected={wsData.incident_detected}
        explanation={wsData.explanation}
      />

      {/* Quick stat cards row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {active.includes('person_count') && (
          <StatusCard label="People in Frame" icon={Users}
            value={metrics.person_count ?? '—'} color="#6366f1"
            subtext="YOLOv8 vision count" />
        )}
        {active.includes('temperature') && metrics.temperature != null && (
          <StatusCard label="Temperature" icon={Thermometer}
            value={`${metrics.temperature}°C`}
            color={metrics.temperature > 32 ? '#f43f5e' : '#fbbf24'}
            subtext="DHT22 Arduino sensor" />
        )}
        {active.includes('gas_level') && metrics.gas_level != null && (
          <StatusCard label="Gas / Smoke" icon={Flame}
            value={`${metrics.gas_level} ppm`}
            color={metrics.gas_level > 400 ? '#f43f5e' : '#10b981'}
            subtext="MQ-2 sensor" />
        )}
        {active.includes('humidity') && metrics.humidity != null && (
          <StatusCard label="Humidity" icon={Droplets}
            value={`${metrics.humidity}%`} color="#22d3ee"
            subtext="DHT22 sensor" />
        )}
        {active.includes('pir_motion') && (
          <StatusCard label="PIR Motion" icon={Activity}
            value={metrics.motion_detected ? 'Active' : 'Clear'}
            color={metrics.motion_detected ? '#10b981' : '#64748b'}
            subtext="Digital pin sensor" />
        )}
      </div>

      {/* Motion score bar */}
      {active.includes('motion_score') && (
        <MotionScoreBar score={wsData.motion_score} />
      )}

      {/* Risk Gauge (for exam cheating, behavior analysis, etc.) */}
      {active.includes('risk_score') && (
        <RiskGauge score={metrics.risk_score} label="Behavioral Risk Score" />
      )}

      {/* Time-series charts — only render if the metric is in active list */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {active.includes('person_count') && (
          <TimeSeriesChart
            title="Person Count Over Time" icon={Users}
            data={history} dataKey="person_count"
            color="#6366f1" unit="" />
        )}
        {active.includes('temperature') && (
          <TimeSeriesChart
            title="Temperature (°C)" icon={Thermometer}
            data={history} dataKey="temperature"
            color="#fbbf24" unit="°C"
            referenceValue={32} referenceLabel="MAX 32°C" />
        )}
        {active.includes('gas_level') && (
          <TimeSeriesChart
            title="Gas / Smoke (ppm)" icon={Flame}
            data={history} dataKey="gas_level"
            color="#f43f5e" unit=" ppm"
            referenceValue={400} referenceLabel="HAZARD 400 ppm" />
        )}
        {active.includes('motion_score') && (
          <TimeSeriesChart
            title="Motion Activity (%)" icon={Activity}
            data={history} dataKey="motion_score"
            color="#3b82f6" unit="%" />
        )}
      </div>

      {/* Incident Timeline (for exam, safety, security scenarios) */}
      {active.includes('incident_timeline') && (
        <IncidentTimeline events={incidentLog} />
      )}
    </div>
  );
};

export default AdaptiveMonitorPanel;
