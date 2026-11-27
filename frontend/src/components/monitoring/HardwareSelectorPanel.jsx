import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import {
  Cpu,
  Camera,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Sliders,
  Thermometer,
  Battery,
  Activity,
  Usb
} from 'lucide-react';

/**
 * Dynamic Hardware Discovery & Component Selector.
 * Strictly renders ONLY verified available sensors and camera sources.
 * Never fakes unavailable hardware (e.g. Windows ACPI blocked thermals).
 */
const HardwareSelectorPanel = ({ onCameraSwitched }) => {
  const { addToast } = useToast();
  const [discovery, setDiscovery] = useState(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);

  const [selectedVision, setSelectedVision] = useState('0');
  const [customStreamUrl, setCustomStreamUrl] = useState('http://192.168.1.50:8080/video');
  const [selectedSensors, setSelectedSensors] = useState([]);

  const scanHardware = async () => {
    setLoading(true);
    try {
      const data = await api.devices.discoverHardware();
      setDiscovery(data);
      const currentVs = data.selection?.vision_source || '0';
      if (currentVs.startsWith('http')) {
        setSelectedVision(currentVs.includes('8080') ? 'uno_q_edge' : 'phone_ip');
        setCustomStreamUrl(currentVs);
      } else {
        setSelectedVision(currentVs);
      }
      setSelectedSensors(data.selection?.enabled_sensors || []);
    } catch (err) {
      console.error('Hardware scan failed:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    scanHardware();
  }, []);

  const toggleSensor = (sensorId, isAvailable) => {
    if (!isAvailable) return;
    setSelectedSensors((prev) =>
      prev.includes(sensorId) ? prev.filter((id) => id !== sensorId) : [...prev, sensorId]
    );
  };

  const handleApply = async () => {
    setApplying(true);
    try {
      const visionPayload =
        selectedVision === 'uno_q_edge' || selectedVision === 'phone_ip'
          ? customStreamUrl.trim()
          : selectedVision;

      const res = await api.devices.selectHardware(visionPayload, selectedSensors);
      addToast({
        type: 'success',
        title: 'Hardware Profile Applied',
        message: `Active components updated (${selectedSensors.length} sensors enabled).`,
        duration: 3000,
      });
      if (res.camera_switch) {
        onCameraSwitched?.();
      }
      await scanHardware();
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Update Failed',
        message: err.message || 'Could not update hardware selection.',
      });
    } finally {
      setApplying(false);
    }
  };

  if (loading && !discovery) {
    return (
      <div className="p-4 rounded-xl bg-white border border-slate-200 text-xs text-slate-500 flex items-center gap-2">
        <RefreshCw className="w-4 h-4 animate-spin text-emerald-600" />
        <span>Scanning attached cameras, COM ports, and verified host sensors...</span>
      </div>
    );
  }

  if (!discovery) return null;

  const availableSensors = discovery.sensors.filter((s) => s.available);
  const unavailableSensors = discovery.sensors.filter((s) => !s.available);

  return (
    <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-sm space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
        <div>
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
            <Sliders className="w-4 h-4 text-emerald-600" />
            <span>Active Hardware & Sensor Selector</span>
          </h3>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Only physically detected hardware is selectable. ({discovery.os} Host &bull;{' '}
            {discovery.arduino_attached ? 'Arduino Attached' : 'No Arduino Detected'})
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={scanHardware}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium flex items-center gap-1.5 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Re-scan</span>
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={applying}
            className="px-3.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-medium flex items-center gap-1.5 transition"
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>{applying ? 'Applying...' : 'Apply Selection'}</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Vision Input Selector */}
        <div className="space-y-2.5">
          <h4 className="text-[11px] font-mono font-semibold uppercase text-slate-600 flex items-center gap-1.5">
            <Camera className="w-3.5 h-3.5 text-indigo-600" />
            <span>Vision Input Source</span>
          </h4>
          <div className="space-y-2">
            {discovery.vision_sources.map((vs) => (
              <label
                key={vs.id}
                className={`flex items-center justify-between p-2.5 rounded-xl border cursor-pointer text-xs transition ${
                  selectedVision === vs.id
                    ? 'bg-emerald-50 border-emerald-300 text-emerald-950'
                    : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100'
                }`}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="vision_source"
                    checked={selectedVision === vs.id}
                    onChange={() => {
                      setSelectedVision(vs.id);
                      if (vs.default_url) setCustomStreamUrl(vs.default_url);
                    }}
                    className="accent-emerald-600"
                  />
                  <span className="font-medium">{vs.label}</span>
                </div>
                {vs.active && (
                  <span className="px-1.5 py-0.5 rounded bg-emerald-200 text-emerald-900 text-[10px] font-mono font-bold">
                    ACTIVE
                  </span>
                )}
              </label>
            ))}

            {(selectedVision === 'uno_q_edge' || selectedVision === 'phone_ip') && (
              <input
                type="text"
                value={customStreamUrl}
                onChange={(e) => setCustomStreamUrl(e.target.value)}
                placeholder="http://<DEVICE_IP>:8080/video"
                className="w-full px-3 py-2 rounded-xl bg-white border border-slate-300 text-xs font-mono text-slate-800 focus:outline-none focus:border-emerald-500"
              />
            )}
          </div>
        </div>

        {/* Verified Sensor Selector */}
        <div className="space-y-2.5">
          <h4 className="text-[11px] font-mono font-semibold uppercase text-slate-600 flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-amber-600" />
            <span>Verified Available Sensors ({availableSensors.length})</span>
          </h4>

          <div className="space-y-1.5">
            {availableSensors.map((s) => {
              const checked = selectedSensors.includes(s.id);
              return (
                <label
                  key={s.id}
                  className={`flex items-center justify-between p-2.5 rounded-xl border cursor-pointer text-xs transition ${
                    checked
                      ? 'bg-indigo-50 border-indigo-200 text-indigo-950'
                      : 'bg-slate-50 border-slate-200 text-slate-700'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleSensor(s.id, true)}
                      className="accent-indigo-600 rounded"
                    />
                    <div>
                      <span className="font-medium">{s.label}</span>
                      <span className="ml-2 text-[10px] font-mono text-slate-500">[{s.source}]</span>
                    </div>
                  </div>
                  <span className="font-mono font-bold text-slate-800">
                    {s.value !== null && s.value !== undefined ? `${s.value}${s.unit}` : 'Ready'}
                  </span>
                </label>
              );
            })}

            {unavailableSensors.length > 0 && (
              <div className="pt-2 space-y-1">
                <p className="text-[10px] font-mono uppercase text-slate-400 flex items-center gap-1">
                  <Usb className="w-3 h-3" />
                  <span>Unattached External Sensors (Hidden from active monitoring):</span>
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {unavailableSensors.map((s) => (
                    <span
                      key={s.id}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-[10px] font-mono text-slate-400"
                    >
                      <XCircle className="w-3 h-3 text-slate-400" />
                      {s.label}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {discovery.host_thermal_blocked_reason && (
              <p className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5 mt-2">
                ℹ️ {discovery.host_thermal_blocked_reason}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default React.memo(HardwareSelectorPanel);
