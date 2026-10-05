import React, { useEffect, useState } from 'react';
import {
  Activity,
  CheckCircle,
  Database,
  RefreshCw,
  Server,
  XCircle,
} from 'lucide-react';
import { DetailedHealth } from '../types';
import { api } from '../services/api';

export const Health: React.FC = () => {
  const [health, setHealth] = useState<DetailedHealth | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const checkHealth = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.get<DetailedHealth>('/health');
      setHealth(data);
      setLastChecked(new Date());
    } catch (err: any) {
      setError(err.message || 'Health check failed');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30_000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const allOk = health && health.status === 'healthy';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">System Health Monitor</h1>
          <p className="text-sm text-slate-400 mt-1">Real-time platform health and component status</p>
        </div>
        <div className="flex items-center gap-4">
          {lastChecked && (
            <span className="text-[11px] text-slate-500 font-mono">
              Last check: {lastChecked.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={checkHealth}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs font-medium text-slate-300 hover:text-white transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 text-xs">
          {error}
        </div>
      )}

      {/* Overall Status Banner */}
      <div
        className={`p-6 rounded-2xl border ${
          allOk
            ? 'bg-emerald-950/30 border-emerald-800/60'
            : health
            ? 'bg-amber-950/30 border-amber-800/60'
            : 'bg-slate-900 border-slate-800'
        }`}
      >
        <div className="flex items-center gap-4">
          {allOk ? (
            <div className="p-3 rounded-full bg-emerald-900/60 border border-emerald-800/80">
              <CheckCircle className="w-8 h-8 text-emerald-400" />
            </div>
          ) : (
            <div className="p-3 rounded-full bg-amber-900/60 border border-amber-800/80">
              <Activity className="w-8 h-8 text-amber-400" />
            </div>
          )}
          <div>
            <h2 className="text-lg font-bold text-white">
              {allOk ? 'All Systems Operational' : health ? 'Degraded Performance Detected' : 'Checking...'}
            </h2>
            {health && (
              <p className="text-xs text-slate-400 mt-1">
                Overall status: <span className="font-mono font-bold text-slate-200">{health.status.toUpperCase()}</span>
                {health.timestamp && (
                  <> • Server time: <span className="font-mono text-slate-300">{new Date(health.timestamp).toLocaleTimeString()}</span></>
                )}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Health Grid */}
      {health && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <HealthCard
            icon={Server}
            title="Backend API"
            ok={true}
            description="FastAPI application is online and responsive"
          />
          <HealthCard
            icon={Database}
            title="MongoDB"
            ok={health.database}
            description={health.database ? 'Database connection established and healthy' : 'Database connection unavailable or unreachable'}
          />
          <HealthCard
            icon={Activity}
            title="MediaMTX Streaming"
            ok={health.status === 'healthy'}
            description={health.status === 'healthy' ? 'Media plane responding' : 'Media engine may be degraded'}
          />
        </div>
      )}
    </div>
  );
};

const HealthCard: React.FC<{
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  ok: boolean;
  description: string;
}> = ({ icon: Icon, title, ok, description }) => (
  <div
    className={`p-5 rounded-xl border transition-colors ${
      ok
        ? 'bg-slate-900 border-slate-800 hover:border-emerald-800/60'
        : 'bg-rose-950/20 border-rose-800/50 hover:border-rose-700'
    }`}
  >
    <div className="flex items-start gap-3.5">
      <div
        className={`p-2.5 rounded-lg border ${
          ok
            ? 'bg-emerald-950/50 border-emerald-800/70 text-emerald-400'
            : 'bg-rose-950/50 border-rose-800/70 text-rose-400'
        }`}
      >
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">{description}</p>
        <div className="flex items-center gap-1.5 mt-2">
          {ok ? (
            <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
          ) : (
            <XCircle className="w-3.5 h-3.5 text-rose-400" />
          )}
          <span className={`text-[11px] font-semibold ${ok ? 'text-emerald-400' : 'text-rose-400'}`}>
            {ok ? 'HEALTHY' : 'DEGRADED'}
          </span>
        </div>
      </div>
    </div>
  </div>
);
