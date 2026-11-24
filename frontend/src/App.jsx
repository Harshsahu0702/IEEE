import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';

import DashboardLayout from './components/layout/DashboardLayout';
import Login from './pages/Login';
import Overview from './pages/Overview';
import CommandCenter from './pages/CommandCenter';
import LiveMonitoring from './pages/LiveMonitoring';
import Devices from './pages/Devices';
import EventsAlerts from './pages/EventsAlerts';
import Reports from './pages/Reports';
import AuditLogs from './pages/AuditLogs';
import Settings from './pages/Settings';


function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      {/* Protected Dashboard Layout */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Overview />} />
        <Route path="command" element={<CommandCenter />} />
        <Route path="live" element={<LiveMonitoring />} />
        <Route path="monitoring" element={<LiveMonitoring />} />
        <Route path="devices" element={<Devices />} />
        <Route path="events" element={<EventsAlerts />} />
        <Route path="reports" element={<Reports />} />
        <Route path="audit" element={<AuditLogs />} />
        <Route path="settings" element={<Settings />} />

      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
