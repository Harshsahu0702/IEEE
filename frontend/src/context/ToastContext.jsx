import React, { createContext, useContext, useState, useCallback } from 'react';
import { CheckCircle2, AlertTriangle, AlertOctagon, Info, X } from 'lucide-react';

const ToastContext = createContext(null);

export const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((toast) => {
    const id = Date.now() + Math.random().toString(36).substring(2, 6);
    const newToast = {
      id,
      type: toast.type || 'info', // 'success', 'warning', 'error', 'info', 'hazard'
      title: toast.title,
      message: toast.message,
      duration: toast.duration || 5000,
    };

    setToasts((prev) => [newToast, ...prev].slice(0, 5));

    if (newToast.duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, newToast.duration);
    }
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const icons = {
    success: <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />,
    warning: <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />,
    error: <AlertOctagon className="w-5 h-5 text-rose-400 shrink-0" />,
    hazard: <AlertOctagon className="w-5 h-5 text-rose-500 shrink-0 animate-pulse" />,
    info: <Info className="w-5 h-5 text-cyan-400 shrink-0" />
  };

  const borderStyles = {
    success: 'border-emerald-500/40 bg-emerald-950/80 shadow-emerald-900/30',
    warning: 'border-amber-500/40 bg-amber-950/80 shadow-amber-900/30',
    error: 'border-rose-500/40 bg-rose-950/80 shadow-rose-900/30',
    hazard: 'border-rose-600 bg-rose-950 shadow-rose-950/60 ring-1 ring-rose-500',
    info: 'border-cyan-500/40 bg-dark-900/90 shadow-cyan-900/20'
  };

  return (
    <ToastContext.Provider value={{ addToast, removeToast }}>
      {children}
      {/* Toast Notification Container */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2.5 max-w-md w-full pointer-events-none">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-start gap-3 p-4 rounded-xl border backdrop-blur-md shadow-xl transition-all duration-300 animate-in slide-in-from-bottom-5 ${borderStyles[toast.type] || borderStyles.info}`}
          >
            {icons[toast.type] || icons.info}
            <div className="flex-1 min-w-0">
              {toast.title && <h4 className="text-sm font-semibold text-white tracking-wide">{toast.title}</h4>}
              <p className="text-xs text-slate-300 mt-0.5 leading-relaxed break-words">{toast.message}</p>
            </div>
            <button
              onClick={() => removeToast(toast.id)}
              className="text-slate-400 hover:text-white transition-colors p-1"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = () => useContext(ToastContext);
