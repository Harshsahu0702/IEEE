import React, { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Sidebar } from './Sidebar';
import { wsService } from '../../services/websocket';
import { useToast } from '../../context/ToastContext';

export const DashboardLayout = () => {
  const { addToast } = useToast();
  const [systemStatus, setSystemStatus] = useState('operational');
  const [openEventsCount, setOpenEventsCount] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    // Start WebSocket connection
    wsService.connect();

    // Subscribe to real-time events for Toast alerts
    const unsubscribe = wsService.subscribe((msg) => {
      if (msg.type === 'event_alert') {
        const evt = msg.event;
        const isHazard = evt.severity === 'critical';
        addToast({
          type: isHazard ? 'hazard' : evt.severity === 'high' ? 'error' : 'warning',
          title: `⚠️ Alert: ${evt.event_type.replace('_', ' ').toUpperCase()}`,
          message: `${evt.description} (Needs operator review)`,
          duration: isHazard ? 10000 : 6000,
        });
        setSystemStatus(isHazard ? 'hazard_alert' : 'elevated');
        setOpenEventsCount((c) => c + 1);
      }
    });

    return () => {
      unsubscribe();
      wsService.disconnect();
    };
  }, [addToast]);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-900">
      <Navbar
        systemStatus={systemStatus}
        openEventsCount={openEventsCount}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
      />
      <div className="flex-1 flex overflow-hidden">
        <Sidebar isOpen={sidebarOpen} />
        <main className="flex-1 overflow-y-auto p-6 md:p-8 transition-all duration-300">
          <div className="max-w-[1600px] mx-auto">
            <Outlet context={{ systemStatus, setSystemStatus }} />
          </div>
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;

