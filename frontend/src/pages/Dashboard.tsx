import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  BarChart3,
  Camera as CameraIcon,
  CheckCircle2,
  Cpu,
  Filter,
  Layers,
  PieChart,
  RefreshCw,
  Search,
  Server,
  Shield,
  Timer,
  TrendingUp,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { Camera, FullAnalytics } from '../types';
import { api } from '../services/api';
import { StatusBadge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';

// ── Skeleton Loader for KPI Cards ───────────────────────────────────────────
const KpiSkeleton: React.FC = () => (
  <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 animate-pulse">
    <div className="flex items-center justify-between">
      <div className="h-3 w-24 bg-slate-800 rounded" />
      <div className="h-10 w-10 bg-slate-800 rounded-lg" />
    </div>
    <div className="mt-4">
      <div className="h-7 w-16 bg-slate-800 rounded" />
      <div className="h-2.5 w-24 bg-slate-800/60 rounded mt-2" />
    </div>
  </div>
);

// ── Empty State Placeholder ─────────────────────────────────────────────────
const EmptyState: React.FC<{
  icon: React.ReactNode;
  title: string;
  description: string;
}> = ({ icon, title, description }) => (
  <div className="flex flex-col items-center justify-center py-12 text-center">
    <div className="p-3 rounded-xl bg-slate-800/40 border border-slate-800/60 text-slate-600 mb-3">
      {icon}
    </div>
    <p className="text-sm font-medium text-slate-400">{title}</p>
    <p className="text-xs text-slate-500 mt-1 max-w-xs leading-relaxed">{description}</p>
  </div>
);

// ── Section Container ───────────────────────────────────────────────────────
const DashboardSection: React.FC<{
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  action?: React.ReactNode;
}> = ({ title, subtitle, icon, children, action }) => (
  <div className="bg-slate-900/50 border border-slate-800/80 rounded-2xl overflow-hidden">
    <div className="px-6 py-4 border-b border-slate-800/60 flex items-center justify-between flex-wrap gap-2">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-slate-800/60 border border-slate-700/40 text-slate-400">
          {icon}
        </div>
        <div>
          <h2 className="text-sm font-bold text-white tracking-tight">{title}</h2>
          {subtitle && <p className="text-[11px] text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
    <div className="p-6">{children}</div>
  </div>
);

// ── Responsive SVG Trend Chart ──────────────────────────────────────────────
const TrendChart: React.FC<{
  points: { period: string; count: number }[];
}> = ({ points }) => {
  if (points.length === 0 || points.every((p) => p.count === 0)) {
    return (
      <div className="h-64 flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-800/80 bg-slate-950/30">
        <BarChart3 className="w-8 h-8 text-slate-700 mb-2" />
        <p className="text-xs text-slate-400 font-medium">No detection data available</p>
        <p className="text-[11px] text-slate-600 mt-1">
          Detection volume will appear here once events are recorded.
        </p>
      </div>
    );
  }

  const maxVal = Math.max(...points.map((p) => p.count), 1);
  const chartHeight = 180;

  return (
    <div className="space-y-4">
      <div className="h-48 w-full flex items-end gap-2 pt-6 pb-2 px-2 overflow-x-auto">
        {points.map((pt, idx) => {
          const heightPct = Math.max(8, (pt.count / maxVal) * 100);
          return (
            <div
              key={idx}
              className="flex-1 min-w-[36px] max-w-[60px] flex flex-col items-center gap-2 group relative"
            >
              {/* Tooltip on hover */}
              <div className="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-8 bg-slate-800 text-emerald-400 text-[10px] font-mono px-2 py-0.5 rounded border border-slate-700 shadow pointer-events-none whitespace-nowrap z-10">
                {pt.count} detections
              </div>
              <div
                className="w-full bg-emerald-600/30 border border-emerald-500/50 rounded-t-sm group-hover:bg-emerald-500 transition-colors"
                style={{ height: `${heightPct}%` }}
              />
              <span className="text-[9px] font-mono text-slate-500 truncate w-full text-center">
                {pt.period.includes(' ') ? pt.period.split(' ')[1] : pt.period.slice(5)}
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex justify-between items-center text-[10px] text-slate-500 font-mono border-t border-slate-800/60 pt-2 px-2">
        <span>Start: {points[0]?.period}</span>
        <span>Peak: {maxVal} events</span>
        <span>Latest: {points[points.length - 1]?.period}</span>
      </div>
    </div>
  );
};

export const Dashboard: React.FC = () => {
  const { organization } = useAuth();

  // Filters
  const [dateRange, setDateRange] = useState<string>('7d'); // 24h, 7d, 30d, 90d
  const [cameraFilter, setCameraFilter] = useState<string>('');
  const [classFilter, setClassFilter] = useState<string>('');
  const [granularity, setGranularity] = useState<'hour' | 'day' | 'week' | 'month'>('day');

  // Real backend analytics state
  const [analytics, setAnalytics] = useState<FullAnalytics | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [healthStatus, setHealthStatus] = useState<string>('Unknown');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Helper to compute date_from for query
  const getDateFromParam = (range: string): string | undefined => {
    const now = Date.now();
    if (range === '24h') return new Date(now - 24 * 60 * 60 * 1000).toISOString();
    if (range === '7d') return new Date(now - 7 * 24 * 60 * 60 * 1000).toISOString();
    if (range === '30d') return new Date(now - 30 * 24 * 60 * 60 * 1000).toISOString();
    if (range === '90d') return new Date(now - 90 * 24 * 60 * 60 * 1000).toISOString();
    return undefined;
  };

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const dateFrom = getDateFromParam(dateRange);
      const queryParams: Record<string, string | undefined> = {
        date_from: dateFrom,
        camera_id: cameraFilter || undefined,
        class_name: classFilter || undefined,
        granularity,
      };

      const [analyticsData, camsData, healthData] = await Promise.all([
        api.get<FullAnalytics>('/analytics', queryParams),
        api.get<Camera[]>('/cameras'),
        api.get<{ status: string }>('/health/public').catch(() => ({ status: 'ok' })),
      ]);

      setAnalytics(analyticsData);
      setCameras(camsData || []);
      setHealthStatus(healthData?.status === 'ok' ? 'Online' : 'Degraded');
    } catch (err: any) {
      setError(err.message || 'Failed to load analytics data');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [dateRange, cameraFilter, classFilter, granularity]);

  const overview = analytics?.overview;
  const trends = analytics?.trends?.points || [];
  const cameraStats = analytics?.cameras || [];
  const classStats = analytics?.classes || [];
  const durationStats = analytics?.duration;

  const totalDetections = overview?.total_detections ?? 0;
  const activeCameras = overview?.active_cameras ?? 0;
  const offlineCameras = overview?.offline_cameras ?? 0;
  const distinctClassesCount = overview?.detection_classes_count ?? 0;

  return (
    <div className="space-y-6">
      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            {organization ? `${organization.name}` : 'Analytics Dashboard'}
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Real-time detection events, camera metrics &amp; AI system intelligence
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Date Range Selector */}
          <select
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value)}
            className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-emerald-500 transition-colors"
          >
            <option value="24h">Past 24 Hours</option>
            <option value="7d">Past 7 Days</option>
            <option value="30d">Past 30 Days</option>
            <option value="90d">Past 90 Days</option>
          </select>

          <button
            onClick={loadData}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-900 border border-slate-800 text-xs font-medium text-slate-300 hover:text-white hover:border-slate-700 transition-colors shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── Error Banner ────────────────────────────────────────────────── */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800/80 text-rose-300 text-xs flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* ── Filters Bar ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 p-3 bg-slate-900/40 border border-slate-800/60 rounded-xl">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Filter className="w-3.5 h-3.5" />
          <span className="font-medium">Filter Events:</span>
        </div>

        <select
          value={cameraFilter}
          onChange={(e) => setCameraFilter(e.target.value)}
          className="px-2.5 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-emerald-500"
        >
          <option value="">All Cameras</option>
          {cameras.map((cam) => (
            <option key={cam.id} value={cam.id}>
              {cam.name}
            </option>
          ))}
        </select>

        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-500" />
          <input
            type="text"
            value={classFilter}
            onChange={(e) => setClassFilter(e.target.value)}
            placeholder="Class (e.g. person, vehicle)..."
            className="pl-7 pr-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-emerald-500 w-52"
          />
        </div>

        {(cameraFilter || classFilter) && (
          <button
            onClick={() => {
              setCameraFilter('');
              setClassFilter('');
            }}
            className="px-2.5 py-1.5 text-xs text-slate-400 hover:text-white transition-colors"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* ── 1. Analytics Overview: KPI Cards ────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {isLoading ? (
          <>
            <KpiSkeleton />
            <KpiSkeleton />
            <KpiSkeleton />
            <KpiSkeleton />
          </>
        ) : (
          <>
            {/* Total Detection Events */}
            <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 hover:border-slate-700/80 transition-colors">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-400">Total Detection Events</p>
                <div className="p-2.5 rounded-lg border text-blue-400 bg-blue-950/40 border-blue-800/40">
                  <TrendingUp className="w-5 h-5" />
                </div>
              </div>
              <div className="mt-3">
                <h3 className="text-2xl font-bold text-slate-100 tracking-tight">
                  {totalDetections.toLocaleString()}
                </h3>
                <p className="text-[11px] text-slate-500 mt-1">Recorded events in range</p>
              </div>
            </div>

            {/* Active Cameras */}
            <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 hover:border-slate-700/80 transition-colors">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-400">Active Cameras</p>
                <div className="p-2.5 rounded-lg border text-emerald-400 bg-emerald-950/40 border-emerald-800/40">
                  <Wifi className="w-5 h-5" />
                </div>
              </div>
              <div className="mt-3">
                <h3 className="text-2xl font-bold text-slate-100 tracking-tight">
                  {activeCameras}
                </h3>
                <p className="text-[11px] text-slate-500 mt-1">
                  {cameras.length > 0 ? `of ${cameras.length} registered` : 'No cameras registered'}
                </p>
              </div>
            </div>

            {/* Offline Cameras */}
            <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 hover:border-slate-700/80 transition-colors">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-400">Offline Cameras</p>
                <div className="p-2.5 rounded-lg border text-rose-400 bg-rose-950/40 border-rose-800/40">
                  <WifiOff className="w-5 h-5" />
                </div>
              </div>
              <div className="mt-3">
                <h3 className="text-2xl font-bold text-slate-100 tracking-tight">
                  {offlineCameras}
                </h3>
                <p className="text-[11px] text-slate-500 mt-1">
                  {offlineCameras === 0 ? 'All cameras healthy' : 'Requires inspection'}
                </p>
              </div>
            </div>

            {/* Detection Classes */}
            <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 hover:border-slate-700/80 transition-colors">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-400">Detection Classes</p>
                <div className="p-2.5 rounded-lg border text-purple-400 bg-purple-950/40 border-purple-800/40">
                  <Layers className="w-5 h-5" />
                </div>
              </div>
              <div className="mt-3">
                <h3 className="text-2xl font-bold text-slate-100 tracking-tight">
                  {distinctClassesCount}
                </h3>
                <p className="text-[11px] text-slate-500 mt-1">Unique object types</p>
              </div>
            </div>
          </>
        )}
      </div>

      {/* ── 2. Detection Trends ─────────────────────────────────────────── */}
      <DashboardSection
        title="Detection Trends"
        subtitle="Aggregated detection volume over selected time range"
        icon={<TrendingUp className="w-4 h-4" />}
        action={
          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-1 text-xs">
            {(['hour', 'day', 'week', 'month'] as const).map((g) => (
              <button
                key={g}
                onClick={() => setGranularity(g)}
                className={`px-2 py-0.5 rounded capitalize text-[11px] transition-colors ${
                  granularity === g
                    ? 'bg-emerald-600 text-white font-semibold'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {g}ly
              </button>
            ))}
          </div>
        }
      >
        {isLoading ? (
          <div className="h-48 flex items-center justify-center animate-pulse">
            <RefreshCw className="w-6 h-6 text-emerald-500 animate-spin" />
          </div>
        ) : (
          <TrendChart points={trends} />
        )}
      </DashboardSection>

      {/* ── 3. Camera Analytics ─────────────────────────────────────────── */}
      <DashboardSection
        title="Camera Analytics"
        subtitle="Per-camera detection counts and last activity timestamps"
        icon={<CameraIcon className="w-4 h-4" />}
        action={
          <Link to="/cameras" className="text-xs text-emerald-400 hover:underline">
            Manage cameras &rarr;
          </Link>
        }
      >
        {isLoading ? (
          <div className="space-y-3 animate-pulse">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-10 bg-slate-800/40 rounded-lg" />
            ))}
          </div>
        ) : cameraStats.length === 0 ? (
          <EmptyState
            icon={<CameraIcon className="w-6 h-6" />}
            title="No camera analytics available"
            description="Camera statistics will appear here once cameras are registered and active."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b border-slate-800/60 text-slate-400 uppercase text-[10px] tracking-wider font-semibold">
                  <th className="py-3 px-4">Camera</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Detections</th>
                  <th className="py-3 px-4">Last Activity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40">
                {cameraStats.map((cam) => (
                  <tr key={cam.camera_id} className="hover:bg-slate-800/20 transition-colors">
                    <td className="py-3 px-4 font-semibold text-slate-200">
                      {cam.camera_name}
                    </td>
                    <td className="py-3 px-4">
                      <StatusBadge status={cam.status} size="sm" />
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-300">
                      {cam.detection_count.toLocaleString()}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-400">
                      {cam.last_activity ? new Date(cam.last_activity).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DashboardSection>

      {/* ── 4. Detection Distribution & Duration Analytics ──────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Detection Distribution by Class */}
        <DashboardSection
          title="Detection Distribution"
          subtitle="Breakdown of detected classes from stored events"
          icon={<PieChart className="w-4 h-4" />}
        >
          {isLoading ? (
            <div className="h-44 flex items-center justify-center animate-pulse">
              <RefreshCw className="w-5 h-5 text-emerald-500 animate-spin" />
            </div>
          ) : classStats.length === 0 ? (
            <EmptyState
              icon={<PieChart className="w-6 h-6" />}
              title="No detection data available"
              description="Class distribution will appear as detection events are logged."
            />
          ) : (
            <div className="space-y-3">
              {classStats.map((item) => (
                <div key={item.class_name} className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-slate-300 capitalize">
                      {item.class_name}
                    </span>
                    <span className="font-mono text-slate-400">
                      {item.count} ({item.percentage}%)
                    </span>
                  </div>
                  <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(100, item.percentage)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </DashboardSection>

        {/* Detection Duration */}
        <DashboardSection
          title="Detection Duration"
          subtitle="Real duration metrics derived from event records"
          icon={<Timer className="w-4 h-4" />}
        >
          {isLoading ? (
            <div className="h-44 flex items-center justify-center animate-pulse">
              <RefreshCw className="w-5 h-5 text-emerald-500 animate-spin" />
            </div>
          ) : !durationStats || durationStats.total_events_with_duration === 0 ? (
            <EmptyState
              icon={<Timer className="w-6 h-6" />}
              title="No duration metrics available"
              description="Event duration will appear when duration data is provided in detection events."
            />
          ) : (
            <div className="grid grid-cols-3 gap-3 pt-2">
              <div className="p-3 bg-slate-950/40 border border-slate-800/60 rounded-xl text-center">
                <p className="text-[11px] text-slate-400">Average Duration</p>
                <p className="text-xl font-bold font-mono text-emerald-400 mt-2">
                  {durationStats.average_duration !== null ? `${durationStats.average_duration}s` : '—'}
                </p>
              </div>
              <div className="p-3 bg-slate-950/40 border border-slate-800/60 rounded-xl text-center">
                <p className="text-[11px] text-slate-400">Total Duration</p>
                <p className="text-xl font-bold font-mono text-blue-400 mt-2">
                  {durationStats.total_duration !== null ? `${durationStats.total_duration}s` : '—'}
                </p>
              </div>
              <div className="p-3 bg-slate-950/40 border border-slate-800/60 rounded-xl text-center">
                <p className="text-[11px] text-slate-400">Longest Duration</p>
                <p className="text-xl font-bold font-mono text-purple-400 mt-2">
                  {durationStats.max_duration !== null ? `${durationStats.max_duration}s` : '—'}
                </p>
              </div>
            </div>
          )}
        </DashboardSection>
      </div>

      {/* ── 5. System Health ────────────────────────────────────────────── */}
      <DashboardSection
        title="System &amp; AI Health"
        subtitle="Infrastructure health and AI processing status"
        icon={<Shield className="w-4 h-4" />}
        action={
          <Link to="/health" className="text-xs text-emerald-400 hover:underline">
            System diagnostics &rarr;
          </Link>
        }
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Camera Health */}
          <div className="p-4 bg-slate-950/40 border border-slate-800/60 rounded-xl">
            <div className="flex items-center gap-2 mb-2">
              <CameraIcon className="w-4 h-4 text-slate-400" />
              <span className="text-xs font-semibold text-slate-300">Camera Health</span>
            </div>
            <div className="flex items-center gap-2 mt-2">
              {offlineCameras === 0 && cameras.length > 0 ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-amber-400" />
              )}
              <span className="text-xs text-slate-200">
                {activeCameras}/{cameras.length} Online
              </span>
            </div>
          </div>

          {/* Backend / API Health */}
          <div className="p-4 bg-slate-950/40 border border-slate-800/60 rounded-xl">
            <div className="flex items-center gap-2 mb-2">
              <Server className="w-4 h-4 text-slate-400" />
              <span className="text-xs font-semibold text-slate-300">Backend API</span>
            </div>
            <div className="flex items-center gap-2 mt-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span className="text-xs text-slate-200">{healthStatus}</span>
            </div>
          </div>

          {/* AI / Inference Health */}
          <div className="p-4 bg-slate-950/40 border border-slate-800/60 rounded-xl">
            <div className="flex items-center gap-2 mb-2">
              <Cpu className="w-4 h-4 text-slate-400" />
              <span className="text-xs font-semibold text-slate-300">AI / Inference Pipeline</span>
            </div>
            <div className="flex items-center gap-2 mt-2">
              <span className="h-2 w-2 rounded-full bg-slate-600" />
              <span className="text-xs text-slate-500">
                AI pipeline not connected
              </span>
            </div>
          </div>
        </div>
      </DashboardSection>
    </div>
  );
};
