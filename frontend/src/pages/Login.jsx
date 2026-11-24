import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Shield, Lock, User, AlertCircle, ArrowRight } from 'lucide-react';

export const Login = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username || !password) {
      setError('Please provide both username and password.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      await login(username, password);
      navigate('/');
    } catch (err) {
      setError(err.message || 'Invalid username or password.');
    } finally {
      setLoading(false);
    }
  };

  const fillCredentials = (u, p) => {
    setUsername(u);
    setPassword(p);
    setError('');
  };

  return (
    <div className="min-h-screen bg-dark-950 flex flex-col justify-center items-center px-4 relative overflow-hidden">
      {/* Background ambient security grid */}
      <div className="absolute inset-0 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:24px_24px] opacity-25" />
      <div className="absolute w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl -top-20 -left-20 pointer-events-none" />
      <div className="absolute w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl -bottom-20 -right-20 pointer-events-none" />

      <div className="max-w-md w-full relative z-10">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 mb-4 shadow-lg shadow-emerald-950">
            <Shield className="w-7 h-7" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">OmniSense AI</h1>
          <p className="text-xs text-slate-400 font-mono mt-1">Autonomous AI+IoT Security & Monitoring Platform</p>
        </div>

        {/* Card */}
        <div className="bg-dark-900/90 border border-dark-800 rounded-2xl p-7 shadow-2xl backdrop-blur-xl">
          <div className="border-b border-dark-800 pb-4 mb-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">Operator Sign In</h2>
            <p className="text-xs text-slate-400 mt-0.5">Access dashboard metrics, camera feeds & command agent.</p>
          </div>

          {error && (
            <div className="mb-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center gap-2.5 text-xs text-rose-300">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">Username</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <User className="w-4 h-4" />
                </div>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin"
                  className="w-full pl-9 pr-4 py-2.5 bg-dark-950 border border-dark-700 rounded-xl text-xs text-white placeholder-slate-400 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">Password</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Lock className="w-4 h-4" />
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-9 pr-4 py-2.5 bg-dark-950 border border-dark-700 rounded-xl text-xs text-white placeholder-slate-400 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-dark-950 font-semibold text-xs tracking-wide transition-all shadow-md shadow-emerald-950 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              {loading ? (
                <span>Authenticating...</span>
              ) : (
                <>
                  <span>Sign In to Station</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Quick Demo Pre-fills */}
          <div className="mt-6 pt-5 border-t border-dark-800 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wider font-mono mb-2">Quick Demo Access</p>
            <div className="flex gap-2 justify-center">
              <button
                type="button"
                onClick={() => fillCredentials('admin', 'admin123')}
                className="px-3 py-1.5 rounded-lg bg-dark-800 border border-dark-700 hover:border-emerald-500/40 text-[11px] text-slate-300 hover:text-emerald-300 transition-colors"
              >
                Admin (Full Access)
              </button>
            </div>
          </div>
        </div>

        <p className="text-center text-[10px] font-mono text-slate-400 mt-6">
          OmniSense AI Milestone 1 &bull; Zero-Identity Surveillance &bull; SOC Compliant
        </p>
      </div>
    </div>
  );
};

export default Login;

