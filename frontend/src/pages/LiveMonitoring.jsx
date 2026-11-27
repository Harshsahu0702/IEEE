import React, { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../services/api';
import { wsService } from '../services/websocket';
import { useToast } from '../context/ToastContext';
import {
  Video,
  Activity,
  Flame,
  Thermometer,
  RefreshCw,
  AlertTriangle,
  Smartphone,
  Laptop,
  HelpCircle,
  RotateCw,
  Siren,
  Volume2,
  VolumeX,
  Radio,
  Eye,
  CheckCircle2,
  Clock,
  Gauge
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

import AdaptiveMonitorPanel from '../components/monitoring/AdaptiveMonitorPanel';
import LiveVideoCanvas from '../components/monitoring/LiveVideoCanvas';
import HardwareSelectorPanel from '../components/monitoring/HardwareSelectorPanel';

export const LiveMonitoring = () => {
  const { addToast } = useToast();
  const [streamReconnectKey, setStreamReconnectKey] = useState(0);
  // Universal monitor WS state
  const [universalMonitorData, setUniversalMonitorData] = useState(null);
  const [activeGoal, setActiveGoal] = useState('');

  const [streamError, setStreamError] = useState(false);
  const [wsStatus, setWsStatus] = useState('disconnected');

  // Camera Source Switcher State
  const [rotation, setRotation] = useState(0);
  const [phoneUrl, setPhoneUrl] = useState('http://192.168.1.15:8080/video');
  const [activeTab, setActiveTab] = useState('laptop'); // 'laptop' or 'phone'
  const [switchingCamera, setSwitchingCamera] = useState(false);
  const [showPhoneHelp, setShowPhoneHelp] = useState(false);
  const [showHardwarePanel, setShowHardwarePanel] = useState(false);

  // Vision Stats (live FPS measured directly from hardware-accelerated canvas)
  const [visionStats, setVisionStats] = useState({
    fps: 20,
    timestamp: Date.now()
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

      if (sirenIntervalRef.current) clearInterval(sirenIntervalRef.current);

      let high = false;
      const playTone = () => {
        if (!audioCtxRef.current || isMuted) return;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(high ? 960 : 720, ctx.currentTime);
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.28);
        osc.start();
        osc.stop(ctx.currentTime + 0.28);
        high = !high;
      };

      playTone();
      sirenIntervalRef.current = setInterval(playTone, 320);
    } catch (e) {
      console.warn('AudioContext failed:', e);
    }
  };

  const stopSiren = () => {
    if (sirenIntervalRef.current) {
      clearInterval(sirenIntervalRef.current);
      sirenIntervalRef.current = null;
    }
  };

  const playAlertChime = () => {
    try {
      if (isMuted) return;
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = audioCtxRef.current || new AudioCtx();
      audioCtxRef.current = ctx;
      if (ctx.state === 'suspended') ctx.resume();

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1320, ctx.currentTime + 0.15);
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
    } catch (e) {
      console.warn('Alert chime failed:', e);
    }
  };

  const dismissAlarm = async () => {
    stopSiren();
    setAlarmActive(false);
    try {
      await api.devices.resetAlarm();
    } catch (e) {
      console.error('Reset alarm failed:', e);
    }
    addToast({
      type: 'info',
      title: '🚨 Hardware Alarm Cleared',
      message: 'Physical buzzer stopped and audio siren silenced.',
      duration: 3000
    });
  };

  useEffect(() => {
    // 1. WebSocket status
    const unsubStatus = wsService.onStatusChange((status) => {
      setWsStatus(status);
    });

    // 2. Subscribe to WebSocket broadcasts
    const unsubMessages = wsService.subscribe((msg) => {
      if (msg.type === 'universal_monitor_update') {
        setUniversalMonitorData(msg);
        if (msg.goal) setActiveGoal(msg.goal);
        if (msg.incident_detected) {
          if (msg.action_required === 'alarm') {
            setAlarmActive(true);
            setAlarmMessage(msg.explanation || 'Universal AI alarm triggered!');
            startSiren();
          } else {
            playAlertChime();
          }
        }
      } else if (msg.type === 'vision_update') {
        setVisionStats((prev) => ({
          ...prev,
          fps: msg.fps || prev.fps,
          timestamp: Date.now()
        }));
      } else if (msg.type === 'threat_alarm') {
        setAlarmActive(true);
        setAlarmMessage(msg.description || 'Threat or hazard detected!');
        startSiren();
      } else if (msg.type === 'alarm_status') {
        if (msg.alarm_active) {
          setAlarmActive(true);
          setAlarmMessage(msg.threat_type ? `Alarm Active: ${msg.threat_type}` : 'Physical Strobe Triggered');
          startSiren();
        } else {
          stopSiren();
          setAlarmActive(false);
        }
      }
    });

    // 3. Check active task on mount
    const checkActiveTask = async () => {
      try {
        const tasks = await api.tasks.list();
        const active = tasks.find((t) => t.status === 'running');
        if (active && active.config?.user_goal) {
          setActiveGoal(active.config.user_goal);
        }
      } catch (e) {
        console.error('Failed to query tasks:', e);
      }
    };
    checkActiveTask();

    return () => {
      unsubStatus();
      unsubMessages();
      stopSiren();
    };
  }, [isMuted]);

  const refreshStream = useCallback(() => {
    setStreamError(false);
    setStreamReconnectKey((k) => k + 1);
  }, []);

  const handleFpsUpdate = useCallback((fps) => {
    setVisionStats({ fps, timestamp: Date.now() });
  }, []);

  const handleStreamError = useCallback((hasErr) => {
    setStreamError(Boolean(hasErr));
  }, []);

  const handleStreamReady = useCallback(() => {
    setStreamError(false);
  }, []);

  const handleSwitchSource = async (source) => {
    setSwitchingCamera(true);
    try {
      const res = await api.video.switchCamera(source);
      if (res.success) {
        addToast({
          type: 'success',
          title: 'Camera Switched Successfully',
          message: res.message || `Switched stream input to ${res.source || source}.`,
          duration: 3500
        });
        refreshStream();
      } else {
        addToast({
          type: 'error',
          title: 'Camera Switch Failed',
          message: res.message || res.error || 'Failed to switch camera.',
          duration: 5000
        });
      }
    } catch (e) {
      addToast({
        type: 'error',
        title: 'Connection Error',
        message: e.message || 'Could not reach server to switch camera.',
        duration: 5000
      });
    } finally {
      setSwitchingCamera(false);
    }
  };

  const handleRotate = async () => {
    const nextRot = (rotation + 90) % 360;
    try {
      const res = await api.video.rotateCamera(nextRot);
      if (res.success) {
        setRotation(nextRot);
        addToast({
          type: 'info',
          title: `Orientation Changed: ${nextRot}°`,
          message: nextRot === 0 ? 'Normal orientation restored.' : `Stream rotated by ${nextRot} degrees clockwise.`,
          duration: 2500
        });
        refreshStream();
      }
    } catch (e) {
      console.error('Failed to rotate camera:', e);
    }
  };

  return (
    <div className="space-y-6">
      {/* Hardware Alarm Warning Modal */}
      {alarmActive && (
        <div className="bg-rose-50 border-2 border-rose-500 rounded-2xl p-5 shadow-lg flex flex-col sm:flex-row items-center justify-between gap-4 animate-bounce">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl bg-rose-500 text-white flex items-center justify-center flex-shrink-0 animate-pulse">
              <Siren className="w-7 h-7" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-rose-900 text-sm tracking-wide uppercase font-mono">
                  🚨 CRITICAL INCIDENT ALARM
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-200 text-rose-900">
                  ARDUINO STROBE TRIGGERED
                </span>
              </div>
              <p className="text-xs text-rose-700 mt-1 font-medium">{alarmMessage}</p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 w-full sm:w-auto justify-end">
            <button
              onClick={() => {
                if (!isMuted) stopSiren();
                setIsMuted(!isMuted);
              }}
              className="px-3 py-2 rounded-xl bg-rose-100 hover:bg-rose-200 text-rose-800 text-xs font-mono font-bold transition flex items-center gap-1.5"
            >
              {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
              {isMuted ? 'Unmute' : 'Mute'}
            </button>
            <button
              onClick={dismissAlarm}
              className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-mono font-bold transition shadow-sm"
            >
              Dismiss Alarm
            </button>
          </div>
        </div>
      )}

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 radar-online" />
            <h1 className="text-xl font-bold tracking-tight text-slate-900">
              Live AI Video Monitor
            </h1>
            <span className="px-2 py-0.5 rounded-md text-[10px] font-mono font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
              640×480 · {visionStats.fps || 20}fps
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Real-time optical feed with dynamic motion tracking and vision-language reasoning.
          </p>
        </div>

        {/* Stream Source Selector */}
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-xl p-1 bg-slate-100 border border-slate-200 text-xs">
            <button
              type="button"
              onClick={() => {
                setActiveTab('laptop');
                handleSwitchSource('0');
              }}
              disabled={switchingCamera}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition ${
                activeTab === 'laptop'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Laptop className="w-3.5 h-3.5" />
              <span>Webcam</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('phone')}
              disabled={switchingCamera}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition ${
                activeTab === 'phone'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Smartphone className="w-3.5 h-3.5" />
              <span>Phone Stream</span>
            </button>
          </div>

          <button
            onClick={() => setShowHardwarePanel((v) => !v)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-medium transition shadow-sm ${
              showHardwarePanel
                ? 'bg-emerald-50 border-emerald-300 text-emerald-800'
                : 'bg-white hover:bg-slate-50 border-slate-200 text-slate-700'
            }`}
            title="Select active cameras & verified sensors"
          >
            <Gauge className="w-3.5 h-3.5" />
            <span>Components</span>
          </button>

          <button
            onClick={handleRotate}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-medium transition shadow-sm"
            title="Rotate camera 90°"
          >
            <RotateCw className="w-3.5 h-3.5 text-slate-600" />
            <span>Rotate {rotation}°</span>
          </button>

          <button
            onClick={refreshStream}
            className="p-2 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-600 hover:text-slate-900 transition shadow-sm"
            title="Refresh stream"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Phone Camera Setup Drawer */}
      {activeTab === 'phone' && (
        <div className="p-4 rounded-xl bg-white border border-slate-200 space-y-3 shadow-sm">
          <div className="flex flex-col sm:flex-row items-center gap-2">
            <input
              type="text"
              value={phoneUrl}
              onChange={(e) => setPhoneUrl(e.target.value)}
              placeholder="e.g. http://192.168.1.15:8080/video"
              className="flex-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-800 font-mono focus:outline-none focus:border-slate-400"
            />
            <button
              type="button"
              onClick={() => handleSwitchSource(phoneUrl)}
              disabled={switchingCamera || !phoneUrl.trim()}
              className="w-full sm:w-auto px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-medium rounded-xl transition flex items-center justify-center gap-1.5"
            >
              {switchingCamera ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Smartphone className="w-3.5 h-3.5" />}
              <span>Connect Phone Stream</span>
            </button>
            <button
              type="button"
              onClick={() => setShowPhoneHelp(!showPhoneHelp)}
              className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs rounded-xl flex items-center gap-1"
            >
              <HelpCircle className="w-3.5 h-3.5" />
              <span>{showPhoneHelp ? 'Hide Guide' : 'Setup Guide'}</span>
            </button>
          </div>

          {showPhoneHelp && (
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 space-y-2">
              <p className="font-semibold text-slate-800 flex items-center gap-1.5">
                <Smartphone className="w-4 h-4 text-emerald-600" />
                How to Connect Phone Camera:
              </p>
              <ol className="list-decimal list-inside space-y-1 text-[11px] leading-relaxed text-slate-600">
                <li>Install the free <strong>"IP Webcam"</strong> or <strong>"DroidCam"</strong> app on your smartphone.</li>
                <li>Connect your phone and PC to the <strong>same Wi-Fi network</strong> (or phone hotspot).</li>
                <li>Open IP Webcam, scroll down and tap <strong>"Start server"</strong>.</li>
                <li>Copy the displayed URL (e.g. <code>http://192.168.1.15:8080/video</code>) into the box above and click Connect.</li>
              </ol>
            </div>
          )}
        </div>
      )}

      {/* Dynamic Hardware & Component Selector Drawer */}
      {showHardwarePanel && (
        <HardwareSelectorPanel onCameraSwitched={refreshStream} />
      )}

      {/* Active Goal Indicator Banner */}
      {activeGoal && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 shadow-sm text-xs font-medium">
          <div className="flex items-center gap-2">
            <Eye className="w-4 h-4 text-emerald-700 flex-shrink-0" />
            <span>Active Goal:</span>
            <span className="font-semibold text-emerald-950 font-mono">"{activeGoal}"</span>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold uppercase tracking-wider">
            Universal VLM Guard
          </span>
        </div>
      )}

      {/* Real-time Prompt Trigger Alert Banner */}
      {universalMonitorData?.incident_detected && (
        <div className="bg-amber-50 border-2 border-amber-400 rounded-2xl p-4 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-3 animate-pulse">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500 text-white flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-amber-900 text-xs tracking-wider uppercase font-mono">
                  ⚠️ PROMPT ALERT: {universalMonitorData.action_required?.toUpperCase() || 'TRIGGERED'}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-200 text-amber-900">
                  {Math.round((universalMonitorData.confidence || 0.8) * 100)}% CONFIDENCE
                </span>
              </div>
              <p className="text-xs text-amber-800 mt-0.5 font-medium">
                {universalMonitorData.explanation || 'Monitored target condition observed in camera feed.'}
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              setUniversalMonitorData((prev) => prev ? { ...prev, incident_detected: false } : null);
            }}
            className="px-3.5 py-1.5 rounded-xl bg-amber-200 hover:bg-amber-300 text-amber-900 text-xs font-semibold transition"
          >
            Acknowledge
          </button>
        </div>
      )}

      {/* =====================================================
          SIDE-BY-SIDE VIDEO FEED & MONITORING GRAPHS
          Video on the left (7 cols), Adaptive Graphs on the right (5 cols)
          ===================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-7 bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm flex flex-col">
          {/* Top Control Header */}
          <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between bg-white">
            <div className="flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 radar-online" />
              <span className="text-xs font-mono font-bold tracking-wider text-slate-800 uppercase">
                CAM-01 · {activeTab === 'phone' ? 'MOBILE PHONE OPTICAL FEED' : 'PRIMARY LAPTOP OPTICAL FEED'}
              </span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold font-mono bg-emerald-50 text-emerald-700 border border-emerald-200">
                LIVE
              </span>
            </div>

            <div className="flex items-center gap-4 text-xs font-mono text-slate-500">
              <span>FPS: <strong className="text-emerald-600">{visionStats.fps || 20}</strong></span>
              <span>Stream: <strong className="text-slate-800 font-semibold">WS Canvas</strong></span>
            </div>
          </div>

          {/* Video Viewport Container (Always keep LiveVideoCanvas mounted so auto-reconnect recovers automatically) */}
          <div className="relative aspect-video bg-slate-950 flex items-center justify-center overflow-hidden">
            <LiveVideoCanvas
              reconnectKey={streamReconnectKey}
              onFpsUpdate={handleFpsUpdate}
              onStreamError={handleStreamError}
              onStreamReady={handleStreamReady}
              className="w-full h-full object-contain"
            />
            {streamError && (
              <div className="absolute inset-0 bg-slate-950/90 backdrop-blur-sm p-8 text-center flex flex-col items-center justify-center space-y-3">
                <AlertTriangle className="w-10 h-10 text-amber-500 mx-auto" />
                <h4 className="text-sm font-semibold text-white">Video Stream Offline</h4>
                <p className="text-xs text-slate-400 max-w-sm">
                  Backend server (port 8000) is unreachable or camera stream is initializing. Auto-reconnecting...
                </p>
                <button
                  onClick={refreshStream}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-emerald-400 border border-slate-700 text-xs font-mono transition-colors"
                >
                  Retry Stream
                </button>
              </div>
            )}

            {/* Privacy Protocol Badge
            <div className="absolute bottom-3 left-3 px-3 py-1 rounded-md bg-slate-900/80 backdrop-blur-sm border border-slate-700 text-[10px] font-mono text-slate-300">
              🔒 Privacy Protocol: Aggregate Count &bull; Zero Biometric ID &bull; Motion Bounding Active
            </div> */}
          </div>
        </div>

        {/* =====================================================
            CONTEXT-ADAPTIVE MONITORING PANEL (SIDE-BY-SIDE)
            Renders dynamically beside the video feed.
            ===================================================== */}
        <div className="lg:col-span-5 space-y-5">
          {universalMonitorData ? (
            <AdaptiveMonitorPanel wsData={universalMonitorData} goal={activeGoal} sideBySide />
          ) : (
            <div className="p-8 rounded-2xl bg-white border border-slate-200 text-center space-y-3 shadow-sm">
              <div className="w-12 h-12 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto">
                <Radio className="w-6 h-6 animate-pulse" />
              </div>
              <h3 className="text-sm font-semibold text-slate-900">Universal Monitor Ready</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Go to the <strong>AI Command Center</strong> and type any natural language monitoring goal (e.g. <em>"Monitor if fan is moving"</em>, <em>"Watch for exam cheating"</em>, or <em>"Detect falls"</em>).
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default LiveMonitoring;
