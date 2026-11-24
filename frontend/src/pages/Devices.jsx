import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import {
  Cpu,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ShieldCheck,
  RefreshCw,
  Activity,
  Radio
} from 'lucide-react';

export const Devices = () => {
  const { isAdmin, canOperate } = useAuth();
  const { addToast } = useToast();

  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [approvingId, setApprovingId] = useState(null);

  const fetchDevices = async () => {
    try {
      const data = await api.devices.list();
      setDevices(data);
    } catch (err) {
      console.error('Error fetching devices:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDevices();
    const interval = setInterval(fetchDevices, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleApprove = async (deviceId) => {
    if (!isAdmin) return;
    setApprovingId(deviceId);
    try {
      await api.devices.approve(deviceId);
      addToast({
        type: 'success',
        title: 'Device Approved',
        message: `Hardware device ${deviceId} is now trusted and online.`
      });
      fetchDevices();
    } catch (err) {
      addToast({ type: 'error', title: 'Approval Failed', message: err.message });
    } finally {
      setApprovingId(null);
    }
  };

  return (
    <div className="space-y-7">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Cpu className="w-5 h-5 text-cyan-400" />
            <span>IoT Hardware Device Management</span>
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Registered sensor stations, cameras, and zero-trust hardware onboarding.
          </p>
        </div>

        <button
          onClick={fetchDevices}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-dark-900 hover:bg-dark-800 text-xs font-mono text-slate-300 border border-dark-800 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </button>
      </div>

      {/* Devices Table */}
      <div className="bg-dark-900 border border-dark-800 rounded-2xl overflow-hidden shadow-2xl">
        <div className="p-4 border-b border-dark-800 flex items-center justify-between">
          <span className="text-xs font-mono font-semibold uppercase tracking-wider text-slate-300">
            Registered Endpoints ({devices.length})
          </span>
          <span className="text-[11px] font-mono text-slate-400">
            Auto-registration active &bull; Unapproved devices restricted
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-dark-950/80 text-[10px] font-mono uppercase text-slate-400 tracking-wider border-b border-dark-800">
              <tr>
                <th className="py-3 px-4">Device ID</th>
                <th className="py-3 px-4">Device Name</th>
                <th className="py-3 px-4">Type</th>
                <th className="py-3 px-4">Location</th>
                <th className="py-3 px-4">Health & Status</th>
                <th className="py-3 px-4">Approval Status</th>
                <th className="py-3 px-4">Last Telemetry</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-dark-800 font-mono">
              {devices.map((device) => {
                const isPending = device.approval_status === 'pending' || device.status === 'pending';
                const isOnline = device.status === 'online';

                return (
                  <tr key={device.id} className="hover:bg-dark-850/60 transition-colors">
                    <td className="py-3 px-4 font-bold text-white flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${
                        isPending ? 'bg-amber-400 animate-pulse' :
                        isOnline ? 'bg-emerald-400 radar-online' : 'bg-slate-500'
                      }`} />
                      {device.device_id}
                    </td>
                    <td className="py-3 px-4 text-slate-200 font-sans text-xs">{device.name}</td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded bg-dark-800 border border-dark-700 text-slate-300 text-[10px]">
                        {device.device_type}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-400 text-xs font-sans">{device.location}</td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                        isOnline ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                        isPending ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                        'bg-slate-800 text-slate-400 border border-dark-700'
                      }`}>
                        {device.status}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold ${
                        device.approval_status === 'approved' ? 'text-emerald-400' : 'text-amber-400'
                      }`}>
                        {device.approval_status || 'approved'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-400 text-[11px]">
                      {device.last_seen ? new Date(device.last_seen).toLocaleTimeString() : 'Never'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {isPending && isAdmin && (
                        <button
                          onClick={() => handleApprove(device.device_id)}
                          disabled={approvingId === device.device_id}
                          className="px-3 py-1 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-dark-950 font-bold text-[10px] transition-all shadow-sm"
                        >
                          {approvingId === device.device_id ? 'Approving...' : 'Approve'}
                        </button>
                      )}
                      {!isPending && (
                        <span className="text-[10px] text-slate-400 flex items-center justify-end gap-1">
                          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                          <span>Trusted</span>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Devices;

