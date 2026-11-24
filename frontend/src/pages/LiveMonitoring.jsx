import React, { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';
import { wsService } from '../services/websocket';
import { useToast } from '../context/ToastContext';
import {
  Video,
  Users,
  Activity,
  Flame,
  Thermometer,
  Droplets,
  Wifi,
  WifiOff,
  RefreshCw,
  ShieldCheck,
  AlertTriangle,
  Smartphone,
  Laptop,
  HelpCircle,
  ExternalLink,
  RotateCw,
  Siren,
  Volume2,
  VolumeX
} from 'lucide-react';

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine
} from 'recharts';

export const LiveMonitoring = () => {
  const { addToast } = useToast();
  const [videoSrc, setVideoSrc] = useState(api.getVideoStreamUrl());
  const [streamError, setStreamError] = useState(false);
  const [wsStatus, setWsStatus] = useState('disconnected');

  // Camera Source Switcher State
  const [cameraSource, setCameraSource] = useState('0');
  const [isSynthetic, setIsSynthetic] = useState(false);
  const [rotation, setRotation] = useState(0);
  const [phoneUrl, setPhoneUrl] = useState('http://192.168.1.15:8080/video');
  const [activeTab, setActiveTab] = useState('laptop'); // 'laptop' or 'phone'
  const [switchingCamera, setSwitchingCamera] = useState(false);
  const [showPhoneHelp, setShowPhoneHelp] = useState(false);

  // Vision Real-time Stats
  const [visionStats, setVisionStats] = useState({
    person_count: 0,
    density_level: 'low',
    fps: 0,
    timestamp: Date.now()
  });

  // IoT Sensor Telemetry Buffer for Recharts (keep last 20 points)
  const [sensorHistory, setSensorHistory] = useState([
    { time: '00:00', temperature: 24.0, gas_level: 110, humidity: 50 },
    { time: '00:02', temperature: 24.2, gas_level: 115, humidity: 51 },
    { time: '00:04', temperature: 24.1, gas_level: 120, humidity: 49 },
  ]);

  const [currentTelemetry, setCurrentTelemetry] = useState({
    temperature: 24.1,
    gas_level: 120,
    humidity: 49,
    motion: false,
    device_id: 'env-sensor-01'
  });

  // Threat & Hardware Alarm State (Audio Siren + Red Strobe)
  const [alarmActive, setAlarmActive] = useState(false);
  const [alarmMessage, setAlarmMessage] = useState('');
  const [isMuted, setIsMuted] = useState(false);
  const audioCtxRef = useRef(null);
  const sirenIntervalRef = useRef(null);

  const startSiren = () => {
    if (isMuted) return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!audioCtxRef.current) {
        audioCtxRef.current = new AudioCtx();
      }
      const ctx = audioCtxRef.current;
      if (ctx.state === 'suspended') {
        ctx.resume();
      }

      let toggle = false;
      if (sirenIntervalRef.current) clearInterval(sirenIntervalRef.current);

      sirenIntervalRef.current = setInterval(() => {
        try {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sawtooth';
          osc.frequency.value = toggle ? 880 : 587;
          gain.gain.setValueAtTime(0.12, ctx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.28);
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start();
          osc.stop(ctx.currentTime + 0.3);
          toggle = !toggle;
        } catch (e) {}
      }, 320);
    } catch (e) {
      console.warn('Audio alarm initialization warning:', e);
    }
  };

  const stopSiren = () => {
    if (sirenIntervalRef.current) {
      clearInterval(sirenIntervalRef.current);
      sirenIntervalRef.current = null;
    }
    setAlarmActive(false);
    api.devices.setAlarm(false, 'none', 'Alarm silenced by operator').catch(() => {});
  };

  const triggerAlarm = (msg, threatType = 'weapon_threat') => {
    setAlarmActive(true);
    setAlarmMessage(msg);
    startSiren();
    addToast(msg, 'error');
    api.devices.setAlarm(true, threatType, msg).catch(() => {});
  };

  useEffect(() => {
    // Fetch initial camera source state
    api.video.getSource()
      .then((res) => {
        setCameraSource(res.source);
        setIsSynthetic(res.is_synthetic);
        if (res.rotation !== undefined) {
          setRotation(res.rotation);
        }
        if (res.source.startsWith('http')) {
          setActiveTab('phone');
          setPhoneUrl(res.source);
        } else {
          setActiveTab('laptop');
        }
      })
      .catch(() => {});

    // Listen for WebSocket connection status
    const unsubStatus = wsService.onStatusChange((status) => {
      setWsStatus(status);
    });


    // Subscribe to live WebSocket messages
    const unsubMessages = wsService.subscribe((payload) => {
      if (payload.type === 'vision_update') {
        setVisionStats({
          person_count: payload.person_count,
          density_level: payload.density_level,
          fps: payload.fps,
          timestamp: Date.now()
        });
      } else if (payload.type === 'telemetry_update') {
        const t = payload.telemetry;
        setCurrentTelemetry(t);
        const timeStr = new Date().toLocaleTimeString().slice(3, 8);

        setSensorHistory((prev) => {
          const next = [
            ...prev,
            {
              time: timeStr,
              temperature: t.temperature,
              gas_level: t.gas_level,
              humidity: t.humidity
            }
          ];
          return next.slice(-20); // Keep last 20 points
        });
      } else if (payload.type === 'threat_alert' || payload.type === 'event_alert') {
        const evt = payload.event || payload;
        if (evt.severity === 'critical' || evt.event_type?.includes('threat') || evt.alarm || evt.event_type?.includes('violence')) {
          triggerAlarm(evt.description || 'CRITICAL THREAT: Brandished Weapon or Physical Altercation Detected!');
        }
      }
    });

    return () => {
      unsubStatus();
      unsubMessages();
    };
  }, []);

  const refreshStream = () => {
    setStreamError(false);
    setVideoSrc(`${api.getVideoStreamUrl()}&_t=${Date.now()}`);
  };

  const handleRotate = async () => {
    const nextRot = (rotation + 90) % 360;
    try {
      const res = await api.video.setRotation(nextRot);
      setRotation(res.rotation);
      refreshStream();
      addToast(`Camera feed rotated to ${res.rotation}°`, 'info');
    } catch (err) {
      addToast('Failed to rotate camera', 'error');
    }
  };

  const handleSwitchSource = async (newSource) => {
    setSwitchingCamera(true);
    try {
      const res = await api.video.setSource(newSource);
      setCameraSource(res.source);
      setIsSynthetic(res.is_synthetic);
      refreshStream();
      addToast(res.message, res.success ? 'success' : 'info');
    } catch (err) {
      addToast(err.message || 'Failed to switch camera source', 'error');
    } finally {
      setSwitchingCamera(false);
    }
  };

  const densityBadge = {
    low: { bg: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' },
    medium: { bg: 'bg-amber-500/20 text-amber-400 border-amber-500/30' },
    high: { bg: 'bg-rose-500/20 text-rose-400 border-rose-500/30 animate-pulse' }
  }[visionStats.density_level.toLowerCase()] || { bg: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' };

  return (
    <div className="space-y-6">
      {/* Page Title & Status */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Video className="w-5 h-5 text-cyan-400" />
            <span>Live Surveillance & Telemetry Feed</span>
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time optical stream with YOLO person detection HUD & IoT environmental sensor charts.
          </p>
        </div>

        {/* WebSocket Health Banner */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-dark-900 border border-dark-800 text-xs font-mono">
            {wsStatus === 'connected' ? (
              <>
                <span className="w-2 h-2 rounded-full bg-emerald-400 radar-online" />
                <span className="text-emerald-400">SOCKET SYNCED</span>
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                <span className="text-amber-400">RECONNECTING...</span>
              </>
            )}
          </div>
          <button
            onClick={() => {
              if (alarmActive) {
                stopSiren();
              } else {
                triggerAlarm("EMERGENCY ALERT: Brandished Weapon & Physical Altercation Detected! Arduino Pin 13 LED Strobe Active.");
              }
            }}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-mono font-semibold transition ${
              alarmActive
                ? 'bg-rose-500 text-white animate-bounce shadow-lg shadow-rose-950'
                : 'bg-rose-950/40 hover:bg-rose-900/60 border border-rose-800 text-rose-300'
            }`}
            title="Simulate / Trigger Threat Siren & Arduino LED"
          >
            <Siren className="w-4 h-4 text-rose-400" />
            <span>{alarmActive ? 'Silence Alarm' : 'Test Threat Alarm'}</span>
          </button>
          <button
            onClick={handleRotate}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-dark-900 hover:bg-dark-800 border border-dark-800 text-slate-300 hover:text-cyan-400 transition-colors text-xs font-mono"
            title="Rotate Video Stream 90 Degrees"
          >
            <RotateCw className="w-4 h-4 text-cyan-400" />
            <span>Rotate {rotation}°</span>
          </button>
          <button
            onClick={refreshStream}
            className="p-2 rounded-xl bg-dark-900 hover:bg-dark-800 border border-dark-800 text-slate-300 hover:text-white transition-colors"
            title="Reload Video Stream"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Critical Security Threat & Hardware Alarm Banner */}
      {alarmActive && (
        <div className="bg-rose-950/70 border-2 border-rose-500 rounded-2xl p-4 flex flex-col sm:flex-row items-center justify-between gap-4 animate-pulse shadow-2xl shadow-rose-950">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-rose-500 text-white rounded-xl animate-bounce flex-shrink-0">
              <Siren className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white tracking-wide uppercase flex items-center gap-2">
                <span>EMERGENCY THREAT ALARM ACTIVE</span>
                <span className="px-2 py-0.5 rounded bg-rose-500 text-white text-[10px] font-mono font-bold animate-ping">
                  ARDUINO PIN 13 LED STROBE ON
                </span>
              </h3>
              <p className="text-xs text-rose-200 mt-1 font-mono">{alarmMessage}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={() => setIsMuted(!isMuted)}
              className="px-3 py-2 rounded-xl bg-dark-900 hover:bg-dark-850 text-slate-200 border border-dark-700 text-xs font-mono flex items-center gap-1.5 transition"
            >
              {isMuted ? <VolumeX className="w-4 h-4 text-rose-400" /> : <Volume2 className="w-4 h-4 text-emerald-400" />}
              <span>{isMuted ? 'Unmute Siren' : 'Mute Siren'}</span>
            </button>
            <button
              onClick={stopSiren}
              className="px-4 py-2 bg-rose-500 hover:bg-rose-400 text-white font-bold text-xs rounded-xl shadow-lg transition"
            >
              Dismiss Alarm
            </button>
          </div>
        </div>
      )}

      {/* Camera Input Source Switcher (Laptop vs Phone IP Camera) */}
      <div className="bg-dark-900 border border-dark-800 rounded-2xl p-4 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-400 font-bold flex items-center gap-1.5">
              <Video className="w-4 h-4 text-emerald-400" />
              Camera Source:
            </span>
            <div className="flex items-center gap-1.5 bg-dark-950 p-1 rounded-xl border border-dark-800">
              <button
                type="button"
                onClick={() => {
                  setActiveTab('laptop');
                  handleSwitchSource('0');
                }}
                disabled={switchingCamera}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition ${
                  activeTab === 'laptop'
                    ? 'bg-emerald-500 text-dark-950 shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Laptop className="w-3.5 h-3.5" />
                Laptop Webcam
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('phone')}
                disabled={switchingCamera}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition ${
                  activeTab === 'phone'
                    ? 'bg-cyan-500 text-dark-950 shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Smartphone className="w-3.5 h-3.5" />
                Mobile Phone (IP Cam)
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="text-slate-400">Status:</span>
            {!isSynthetic ? (
              <span className="px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5 text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                LIVE HARDWARE STREAM ({cameraSource})
              </span>
            ) : (
              <span className="px-2.5 py-1 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1.5 text-[11px]">
                STANDBY / TEST GENERATOR
              </span>
            )}
          </div>
        </div>

        {/* Mobile Phone IP Camera Configuration Input */}
        {activeTab === 'phone' && (
          <div className="pt-2 border-t border-dark-800/80 space-y-2">
            <div className="flex flex-col sm:flex-row items-center gap-2">
              <div className="relative flex-1 w-full">
                <input
                  type="text"
                  value={phoneUrl}
                  onChange={(e) => setPhoneUrl(e.target.value)}
                  placeholder="e.g. http://192.168.1.15:8080/video"
                  className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs text-cyan-300 font-mono placeholder-slate-600 focus:outline-none focus:border-cyan-500"
                />
              </div>
              <button
                type="button"
                onClick={() => handleSwitchSource(phoneUrl)}
                disabled={switchingCamera || !phoneUrl.trim()}
                className="w-full sm:w-auto px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-dark-950 text-xs font-bold rounded-xl transition flex items-center justify-center gap-1.5 shadow-md shadow-cyan-950"
              >
                {switchingCamera ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Connecting...
                  </>
                ) : (
                  <>
                    <Smartphone className="w-3.5 h-3.5" /> Connect Phone Camera
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={() => setShowPhoneHelp(!showPhoneHelp)}
                className="px-3 py-2 bg-dark-800 hover:bg-dark-750 text-slate-300 text-xs rounded-xl border border-dark-700 flex items-center gap-1"
              >
                <HelpCircle className="w-3.5 h-3.5 text-cyan-400" />
                {showPhoneHelp ? 'Hide Guide' : 'How to Setup Phone?'}
              </button>
            </div>

            {/* Step-by-Step Setup Instructions for Phone Camera */}
            {showPhoneHelp && (
              <div className="bg-dark-950 border border-cyan-500/30 rounded-xl p-4 text-xs text-slate-300 space-y-2 animate-fadeIn">
                <div className="font-bold text-cyan-300 flex items-center gap-1.5">
                  <Smartphone className="w-4 h-4" />
                  Phone Camera Kaise Connect Karein? (4 Easy Steps):
                </div>
                <ol className="list-decimal list-inside space-y-1 text-slate-300 text-[11px] leading-relaxed">
                  <li>Apne phone me Google Play Store / App Store se free app <strong className="text-white">"IP Webcam"</strong> (ya <strong className="text-white">"DroidCam"</strong>) install karein.</li>
                  <li>Phone aur Laptop dono ko <strong className="text-white">same Wi-Fi network</strong> (ya phone ke Mobile Hotspot) se connect karein.</li>
                  <li>Phone me IP Webcam app khol kar sabse niche scroll karein aur <strong className="text-emerald-400">"Start server"</strong> par click karein.</li>
                  <li>Phone screen par jo URL likha aayega (jaise: <code className="bg-dark-800 text-cyan-300 px-1 py-0.5 rounded">http://192.168.1.15:8080/video</code>), use upar wale box me paste karke <strong className="text-cyan-400">"Connect Phone Camera"</strong> dabayein!</li>
                </ol>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Real-time Detection Status & Orientation Tip Banner */}
      <div className="bg-gradient-to-r from-cyan-950/40 via-dark-900 to-emerald-950/30 border border-cyan-800/40 rounded-xl p-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2.5 text-cyan-200">
          <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          <span>
            <strong className="text-white">Live AI Person Detection Active:</strong> Bounding boxes aur count automatically live stream par dikhenge. Agar camera sideways hai ya bed par lette huye test kar rahe hain, toh <strong className="text-cyan-300">"Rotate {rotation}°"</strong> dabakar seedha karein.
          </span>
        </div>
        <button
          onClick={handleRotate}
          className="px-3 py-1.5 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 rounded-xl text-xs font-mono font-semibold flex items-center gap-1.5 flex-shrink-0 transition"
        >
          <RotateCw className="w-3.5 h-3.5" /> Rotate 90°
        </button>
      </div>

      {/* Main Vision Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Optical Stream Player (2 Columns) */}
        <div className="lg:col-span-2 bg-dark-900 border border-dark-800 rounded-2xl overflow-hidden shadow-2xl relative flex flex-col">
          {/* Stream Overlay Bar */}
          <div className="bg-dark-950/80 backdrop-blur-md px-4 py-3 border-b border-dark-800 flex items-center justify-between z-10">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse" />
              <span className="text-xs font-mono font-bold tracking-wider text-slate-200 uppercase">
                {activeTab === 'phone' ? 'MOBILE PHONE CAMERA FEED' : 'LAPTOP WEBCAM FEED'}
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono">
              <button
                onClick={handleRotate}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-dark-900 hover:bg-dark-800 border border-dark-750 text-slate-300 hover:text-cyan-300 transition-colors text-[11px]"
                title="Rotate 90 degrees"
              >
                <RotateCw className="w-3 h-3 text-cyan-400" />
                <span>Rotate {rotation}°</span>
              </button>
              <span className="text-slate-400">FPS: <strong className="text-emerald-400">{visionStats.fps || 15}</strong></span>
              <span className={`px-2 py-0.5 rounded border text-[11px] font-bold uppercase ${densityBadge.bg}`}>
                {visionStats.density_level} DENSITY
              </span>
            </div>
          </div>


          {/* Video Stream Container */}
          <div className="relative aspect-video bg-dark-950 flex items-center justify-center overflow-hidden">
            {!streamError ? (
              <img
                src={videoSrc}
                alt="Live Video Stream Feed"
                onError={() => setStreamError(true)}
                className="w-full h-full object-contain"
              />
            ) : (
              <div className="p-8 text-center space-y-3">
                <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto" />
                <h4 className="text-sm font-semibold text-white">Optical Stream Offline</h4>
                <p className="text-xs text-slate-400 max-w-sm">
                  Start a crowd monitoring task from the AI Command Center to activate the live feed.
                </p>
                <button
                  onClick={refreshStream}
                  className="px-4 py-2 rounded-xl bg-dark-800 hover:bg-dark-750 text-emerald-400 border border-emerald-500/30 text-xs font-mono transition-colors"
                >
                  Retry Connection
                </button>
              </div>
            )}

            {/* Privacy Guardrail Watermark */}
            <div className="absolute bottom-3 left-3 px-2.5 py-1 rounded-md bg-dark-950/70 backdrop-blur-sm border border-dark-700/50 text-[10px] font-mono text-slate-400">
              🔒 Privacy Protocol: Aggregate Count Only &bull; Zero Biometric ID
            </div>
          </div>
        </div>

        {/* Live Metrics & Quick Stats (1 Column) */}
        <div className="space-y-4 flex flex-col justify-between">
          {/* Person Count HUD Card */}
          <div className="p-5 rounded-2xl bg-dark-900 border border-dark-800 space-y-3">
            <span className="text-xs font-mono font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <Users className="w-4 h-4 text-emerald-400" />
              <span>Real-Time Person Count</span>
            </span>
            <div className="flex items-baseline gap-3">
              <span className="text-5xl font-extrabold font-mono text-white tracking-tight">
                {visionStats.person_count}
              </span>
              <span className="text-xs text-slate-400 font-mono">detected in view</span>
            </div>
            <div className="pt-2 border-t border-dark-800 flex items-center justify-between text-xs font-mono text-slate-400">
              <span>Spatial Density:</span>
              <span className={`px-2 py-0.5 rounded font-bold uppercase ${densityBadge.bg}`}>
                {visionStats.density_level}
              </span>
            </div>
          </div>

          {/* Environmental Sensor Gauge Cards */}
          <div className="p-5 rounded-2xl bg-dark-900 border border-dark-800 space-y-4">
            <span className="text-xs font-mono font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-cyan-400" />
              <span>Current IoT Telemetry</span>
            </span>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-dark-950 border border-dark-800">
                <div className="flex items-center gap-1.5 text-slate-400 mb-1">
                  <Thermometer className="w-3.5 h-3.5 text-amber-400" />
                  <span>Temperature</span>
                </div>
                <span className="text-lg font-bold font-mono text-white">{currentTelemetry.temperature}&deg;C</span>
                <p className="text-[10px] text-slate-400 font-mono">Limit: 32.0&deg;C</p>
              </div>

              <div className="p-3 rounded-xl bg-dark-950 border border-dark-800">
                <div className="flex items-center gap-1.5 text-slate-400 mb-1">
                  <Flame className="w-3.5 h-3.5 text-rose-400" />
                  <span>MQ-2 Gas</span>
                </div>
                <span className={`text-lg font-bold font-mono ${currentTelemetry.gas_level >= 400 ? 'text-rose-400 animate-pulse' : 'text-white'}`}>
                  {currentTelemetry.gas_level} <span className="text-xs font-normal text-slate-400">ppm</span>
                </span>
                <p className="text-[10px] text-slate-400 font-mono">Hazard Limit: 400</p>
              </div>

              <div className="p-3 rounded-xl bg-dark-950 border border-dark-800">
                <div className="flex items-center gap-1.5 text-slate-400 mb-1">
                  <Droplets className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Humidity</span>
                </div>
                <span className="text-lg font-bold font-mono text-white">{currentTelemetry.humidity}%</span>
                <p className="text-[10px] text-slate-400 font-mono">Nominal: 20-75%</p>
              </div>

              <div className="p-3 rounded-xl bg-dark-950 border border-dark-800">
                <div className="flex items-center gap-1.5 text-slate-400 mb-1">
                  <Activity className="w-3.5 h-3.5 text-emerald-400" />
                  <span>PIR Motion</span>
                </div>
                <span className={`text-sm font-bold font-mono uppercase ${currentTelemetry.motion ? 'text-emerald-400' : 'text-slate-400'}`}>
                  {currentTelemetry.motion ? 'Active' : 'Clear'}
                </span>
                <p className="text-[10px] text-slate-400 font-mono">Station Alpha</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Real-time Recharts Line Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Temperature Trend */}
        <div className="p-5 rounded-2xl bg-dark-900 border border-dark-800 space-y-4">
          <div className="flex items-center justify-between border-b border-dark-800 pb-3">
            <h3 className="text-xs font-mono font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Thermometer className="w-4 h-4 text-amber-400" />
              <span>Ambient Temperature History (&deg;C)</span>
            </h3>
            <span className="text-[11px] font-mono text-amber-400">Threshold: 32&deg;C</span>
          </div>

          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sensorHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" />
                <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 10 }} />
                <YAxis domain={[15, 45]} stroke="#64748b" tick={{ fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0e1117', borderColor: '#283149', borderRadius: '8px', fontSize: '11px' }}
                />
                <ReferenceLine y={32} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: 'MAX 32°C', fill: '#f59e0b', fontSize: 10 }} />
                <Line type="monotone" dataKey="temperature" stroke="#fbbf24" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Gas Concentration Trend */}
        <div className="p-5 rounded-2xl bg-dark-900 border border-dark-800 space-y-4">
          <div className="flex items-center justify-between border-b border-dark-800 pb-3">
            <h3 className="text-xs font-mono font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Flame className="w-4 h-4 text-rose-400" />
              <span>MQ-2 Gas / Smoke Concentration (ppm)</span>
            </h3>
            <span className="text-[11px] font-mono text-rose-400">Hazard Line: 400 ppm</span>
          </div>

          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sensorHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" />
                <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 10 }} />
                <YAxis domain={[0, 700]} stroke="#64748b" tick={{ fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0e1117', borderColor: '#283149', borderRadius: '8px', fontSize: '11px' }}
                />
                <ReferenceLine y={400} stroke="#f43f5e" strokeDasharray="4 4" label={{ value: 'HAZARD 400 ppm', fill: '#f43f5e', fontSize: 10 }} />
                <Line type="monotone" dataKey="gas_level" stroke="#f43f5e" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LiveMonitoring;

