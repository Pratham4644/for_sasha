import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Download,
  Filter,
  Layers,
  RefreshCw,
  Search,
  Shield,
  Video,
} from 'lucide-react';
import { AuditLogEntry, Camera, DetectionLog, DetectionLogsResponse } from '../types';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useDetectionSocket } from '../context/DetectionSocketContext';

export const Logs: React.FC = () => {
  const { hasPermission } = useAuth();
  const { latestDetection } = useDetectionSocket();

  // Mode: "detection" (default, primary) or "audit" (admin access)
  const [activeTab, setActiveTab] = useState<'detection' | 'audit'>('detection');

  // ── Detection Logs State ──────────────────────────────────────────────────
  const [detectionLogs, setDetectionLogs] = useState<DetectionLog[]>([]);
  const [totalDetectionLogs, setTotalDetectionLogs] = useState<number>(0);
  const [detPage, setDetPage] = useState<number>(1);
  const [detPageSize] = useState<number>(25);

  // Filters
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedCamera, setSelectedCamera] = useState<string>('');
  const [classFilter, setClassFilter] = useState<string>('');
  const [minConfidence, setMinConfidence] = useState<string>('');
  const [dateRange, setDateRange] = useState<string>('all'); // all, 24h, 7d, 30d
  const [searchTerm, setSearchTerm] = useState<string>('');

  const [isLoadingDetections, setIsLoadingDetections] = useState<boolean>(true);
  const [detectionError, setDetectionError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState<boolean>(false);

  // ── Audit Logs State (Preserved for Administrators) ────────────────────────
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [totalAuditLogs, setTotalAuditLogs] = useState<number>(0);
  const [auditPage, setAuditPage] = useState<number>(1);
  const [auditResourceType, setAuditResourceType] = useState<string>('');
  const [auditActionFilter, setAuditActionFilter] = useState<string>('');
  const [isLoadingAudit, setIsLoadingAudit] = useState<boolean>(false);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [selectedAuditLog, setSelectedAuditLog] = useState<AuditLogEntry | null>(null);

  // Load cameras for filtering dropdown
  useEffect(() => {
    api.get<Camera[]>('/cameras')
      .then((cams) => setCameras(cams || []))
      .catch(() => setCameras([]));
  }, []);

  // Compute ISO dates based on dateRange helper
  const computeDateRangeParams = () => {
    if (dateRange === '24h') {
      const d = new Date(Date.now() - 24 * 60 * 60 * 1000);
      return { date_from: d.toISOString() };
    }
    if (dateRange === '7d') {
      const d = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
      return { date_from: d.toISOString() };
    }
    if (dateRange === '30d') {
      const d = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
      return { date_from: d.toISOString() };
    }
    return {};
  };

  const getDetectionFilterParams = () => {
    const dates = computeDateRangeParams();
    return {
      camera_id: selectedCamera || undefined,
      class_name: classFilter.trim() || undefined,
      min_confidence: minConfidence ? parseFloat(minConfidence) : undefined,
      search: searchTerm.trim() || undefined,
      ...dates,
    };
  };

  // Fetch Detection Logs
  const loadDetectionLogs = async () => {
    setIsLoadingDetections(true);
    setDetectionError(null);
    try {
      const params = {
        page: detPage,
        page_size: detPageSize,
        ...getDetectionFilterParams(),
      };
      const res = await api.get<DetectionLogsResponse>('/detection-logs', params);
      setDetectionLogs(res?.items || []);
      setTotalDetectionLogs(res?.total || 0);
    } catch (err: any) {
      setDetectionError(err.message || 'Failed to load detection logs');
      setDetectionLogs([]);
      setTotalDetectionLogs(0);
    } finally {
      setIsLoadingDetections(false);
    }
  };

  // Fetch Audit Logs (when on audit tab)
  const loadAuditLogs = async () => {
    setIsLoadingAudit(true);
    setAuditError(null);
    try {
      const res = await api.get<{ items: AuditLogEntry[]; total: number }>('/logs', {
        page: auditPage,
        page_size: 25,
        resource_type: auditResourceType || undefined,
        action: auditActionFilter || undefined,
      });
      setAuditLogs(res?.items || []);
      setTotalAuditLogs(res?.total || 0);
    } catch (err: any) {
      setAuditError(err.message || 'Failed to load audit logs');
    } finally {
      setIsLoadingAudit(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'detection') {
      loadDetectionLogs();
    } else {
      loadAuditLogs();
    }
  }, [
    activeTab,
    detPage,
    selectedCamera,
    classFilter,
    minConfidence,
    dateRange,
    searchTerm,
    auditPage,
    auditResourceType,
    auditActionFilter,
  ]);

  // Real-time detection event ingestion via WebSocket
  useEffect(() => {
    if (!latestDetection || activeTab !== 'detection' || detPage !== 1) return;
    if (selectedCamera && latestDetection.camera_id !== selectedCamera) return;
    if (classFilter && !latestDetection.class_name.toLowerCase().includes(classFilter.toLowerCase())) return;
    if (minConfidence && latestDetection.confidence < parseFloat(minConfidence)) return;

    setDetectionLogs((prev) => [latestDetection, ...prev]);
    setTotalDetectionLogs((t) => t + 1);
  }, [latestDetection, activeTab, detPage, selectedCamera, classFilter, minConfidence]);

  // CSV Export handler
  const handleExportCsv = async () => {
    setIsExporting(true);
    try {
      await api.exportDetectionLogsCsv(getDetectionFilterParams());
    } catch (err: any) {
      alert(`Export failed: ${err.message || 'Unknown error'}`);
    } finally {
      setIsExporting(false);
    }
  };

  const totalDetPages = Math.ceil(totalDetectionLogs / detPageSize) || 1;
  const totalAuditPages = Math.ceil(totalAuditLogs / 25) || 1;

  const formatConfidence = (conf: number): string => {
    if (conf <= 1.0) {
      return `${(conf * 100).toFixed(1)}%`;
    }
    return `${conf.toFixed(1)}%`;
  };

  const formatDuration = (sec?: number | null): string => {
    if (sec === undefined || sec === null) return '—';
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const mins = Math.floor(sec / 60);
    const rem = sec % 60;
    return `${mins}m ${rem.toFixed(0)}s`;
  };

  const formatDetectionSnapshotText = (log: DetectionLog): string => {
    if (log.detections && log.detections.length > 0) {
      const counts: Record<string, number> = {};
      for (const d of log.detections) {
        const cls = (d.class_name || 'Object').trim();
        counts[cls] = (counts[cls] || 0) + 1;
      }
      const parts = Object.entries(counts).map(([cls, count]) => {
        let name = cls.charAt(0).toUpperCase() + cls.slice(1).toLowerCase();
        if (name.toLowerCase() === 'person') {
          name = count > 1 ? 'Persons' : 'Person';
        } else if (count > 1 && !name.endsWith('s')) {
          name += 's';
        }
        return `${count} ${name}`;
      });
      return parts.join(' · ');
    }
    const cls = (log.class_name || 'Object').trim();
    let name = cls.charAt(0).toUpperCase() + cls.slice(1).toLowerCase();
    if (name.toLowerCase() === 'person') name = 'Person';
    return `1 ${name}`;
  };

  const formatSnapshotTime = (isoStr: string): string => {
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
    } catch {
      return isoStr;
    }
  };

  const cameraGroups = React.useMemo(() => {
    const groups: {
      cameraId: string;
      cameraName: string;
      events: DetectionLog[];
    }[] = [];
    const groupMap = new Map<string, { cameraId: string; cameraName: string; events: DetectionLog[] }>();

    for (const log of detectionLogs) {
      const cid = log.camera_id || 'unknown';
      let g = groupMap.get(cid);
      if (!g) {
        const camObj = cameras.find((c) => c.id === cid);
        const cname = log.camera_name || camObj?.name || cid;
        g = { cameraId: cid, cameraName: cname, events: [] };
        groupMap.set(cid, g);
        groups.push(g);
      }
      g.events.push(log);
    }

    for (const g of groups) {
      g.events.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    }

    return groups;
  }, [detectionLogs, cameras]);

  return (
    <div className="space-y-6">
      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Detection Logs</h1>
          <p className="text-sm text-slate-400 mt-1">
            Detection events recorded across cameras.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Tab Selector (Detection vs Audit if user has audit:read) */}
          {hasPermission('audit:read') && (
            <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-1">
              <button
                onClick={() => setActiveTab('detection')}
                className={`px-3 py-1.5 rounded text-xs font-semibold transition-colors ${
                  activeTab === 'detection'
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                Detection Logs
              </button>
              <button
                onClick={() => setActiveTab('audit')}
                className={`px-3 py-1.5 rounded text-xs font-semibold transition-colors ${
                  activeTab === 'audit'
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                Audit Logs
              </button>
            </div>
          )}

          {activeTab === 'detection' && (
            <button
              onClick={handleExportCsv}
              disabled={isExporting || totalDetectionLogs === 0}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-xs font-semibold text-white transition-colors shadow-sm"
            >
              <Download className={`w-3.5 h-3.5 ${isExporting ? 'animate-bounce' : ''}`} />
              {isExporting ? 'Exporting...' : 'Export CSV'}
            </button>
          )}

          <button
            onClick={() => (activeTab === 'detection' ? loadDetectionLogs() : loadAuditLogs())}
            disabled={activeTab === 'detection' ? isLoadingDetections : isLoadingAudit}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-900 border border-slate-800 text-xs font-medium text-slate-300 hover:text-white hover:border-slate-700 transition-colors shadow-sm"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${
                (activeTab === 'detection' ? isLoadingDetections : isLoadingAudit)
                  ? 'animate-spin'
                  : ''
              }`}
            />
            Refresh
          </button>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* TAB 1: DETECTION LOGS (PRIMARY)                                    */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'detection' && (
        <>
          {/* Filters Bar */}
          <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center gap-1.5 text-xs text-slate-400 font-medium">
                <Filter className="w-3.5 h-3.5 text-slate-500" />
                <span>Filters:</span>
              </div>

              {/* Date Range Selector */}
              <select
                value={dateRange}
                onChange={(e) => {
                  setDateRange(e.target.value);
                  setDetPage(1);
                }}
                className="px-2.5 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-emerald-500"
              >
                <option value="all">All Time</option>
                <option value="24h">Past 24 Hours</option>
                <option value="7d">Past 7 Days</option>
                <option value="30d">Past 30 Days</option>
              </select>

              {/* Camera Filter */}
              <select
                value={selectedCamera}
                onChange={(e) => {
                  setSelectedCamera(e.target.value);
                  setDetPage(1);
                }}
                className="px-2.5 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-emerald-500"
              >
                <option value="">All Cameras</option>
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>

              {/* Class Filter */}
              <input
                type="text"
                placeholder="Class (e.g. person)..."
                value={classFilter}
                onChange={(e) => {
                  setClassFilter(e.target.value);
                  setDetPage(1);
                }}
                className="px-2.5 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-emerald-500 w-36"
              />

              {/* Min Confidence */}
              <select
                value={minConfidence}
                onChange={(e) => {
                  setMinConfidence(e.target.value);
                  setDetPage(1);
                }}
                className="px-2.5 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-emerald-500"
              >
                <option value="">Any Confidence</option>
                <option value="0.50">&ge; 50%</option>
                <option value="0.75">&ge; 75%</option>
                <option value="0.85">&ge; 85%</option>
                <option value="0.90">&ge; 90%</option>
                <option value="0.95">&ge; 95%</option>
              </select>

              {/* Search text */}
              <div className="relative">
                <Search className="w-3 h-3 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search logs..."
                  value={searchTerm}
                  onChange={(e) => {
                    setSearchTerm(e.target.value);
                    setDetPage(1);
                  }}
                  className="pl-7 pr-2.5 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-emerald-500 w-40"
                />
              </div>

              {(selectedCamera || classFilter || minConfidence || dateRange !== 'all' || searchTerm) && (
                <button
                  onClick={() => {
                    setSelectedCamera('');
                    setClassFilter('');
                    setMinConfidence('');
                    setDateRange('all');
                    setSearchTerm('');
                    setDetPage(1);
                  }}
                  className="text-xs text-slate-400 hover:text-white transition-colors"
                >
                  Reset
                </button>
              )}
            </div>

            <div className="text-xs text-slate-500 font-mono">
              Showing {detectionLogs.length} of {totalDetectionLogs} events
            </div>
          </div>

          {detectionError && (
            <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{detectionError}</span>
            </div>
          )}

          {/* Grouped Camera Detection Sections */}
          {isLoadingDetections ? (
            <div className="p-16 bg-slate-900 border border-slate-800 rounded-2xl flex flex-col items-center justify-center gap-2 text-slate-500 shadow-sm">
              <RefreshCw className="w-5 h-5 text-emerald-500 animate-spin" />
              <span className="text-xs">Loading detection logs...</span>
            </div>
          ) : detectionLogs.length === 0 ? (
            <div className="p-16 bg-slate-900 border border-slate-800 rounded-2xl text-center text-slate-500 shadow-sm">
              <Layers className="w-10 h-10 text-slate-700 mx-auto mb-3" />
              <p className="text-sm font-medium text-slate-400">No detection data available</p>
              <p className="text-xs text-slate-600 mt-1">
                Detection logs will appear here once the AI pipeline records events.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {cameraGroups.map((section) => (
                <div
                  key={section.cameraId}
                  className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm"
                >
                  {/* Camera Header Banner */}
                  <div className="bg-slate-950 px-6 py-4 border-b border-slate-800 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                        <Video className="w-4 h-4" />
                      </div>
                      <span className="text-sm font-bold font-mono tracking-wider text-white uppercase">
                        CAMERA: {section.cameraName}
                      </span>
                    </div>
                    <span className="text-xs font-mono text-slate-400 bg-slate-900 px-2.5 py-1 rounded-md border border-slate-800">
                      {section.events.length} snapshot{section.events.length !== 1 ? 's' : ''}
                    </span>
                  </div>

                  {/* Chronological Event Entries */}
                  <div className="p-6 space-y-4">
                    {section.events.map((event) => (
                      <div
                        key={event.id}
                        className="p-3.5 bg-slate-950/60 rounded-xl border border-slate-800/60 flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:border-slate-700 transition-colors"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-baseline gap-2 sm:gap-6">
                          <span className="text-xs font-mono font-bold text-slate-400 shrink-0 min-w-[75px]">
                            {formatSnapshotTime(event.timestamp)}
                          </span>
                          <span className="text-sm font-semibold text-emerald-300 tracking-wide">
                            {formatDetectionSnapshotText(event)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-[11px] font-mono text-slate-500 self-end sm:self-auto">
                          {event.confidence ? (
                            <span className="text-slate-400">
                              Peak: {formatConfidence(event.confidence)}
                            </span>
                          ) : null}
                          {event.inference_latency_ms ? (
                            <span className="text-slate-600">
                              • {event.inference_latency_ms.toFixed(0)}ms
                            </span>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Pagination Controls */}
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl flex items-center justify-between text-xs text-slate-400">
            <span>
              Page {detPage} of {totalDetPages}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setDetPage((p) => Math.max(1, p - 1))}
                disabled={detPage <= 1}
                className="p-1.5 rounded-lg border border-slate-800 bg-slate-900 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-800 text-slate-300"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setDetPage((p) => Math.min(totalDetPages, p + 1))}
                disabled={detPage >= totalDetPages}
                className="p-1.5 rounded-lg border border-slate-800 bg-slate-900 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-800 text-slate-300"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* TAB 2: AUDIT LOGS (ADMINISTRATIVE)                                 */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'audit' && (
        <>
          <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3 flex-wrap">
              <select
                value={auditResourceType}
                onChange={(e) => {
                  setAuditResourceType(e.target.value);
                  setAuditPage(1);
                }}
                className="px-3 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-emerald-500"
              >
                <option value="">All Resource Types</option>
                <option value="camera">Camera</option>
                <option value="site">Site</option>
                <option value="user">User</option>
                <option value="organization">Organization</option>
                <option value="auth">Auth</option>
                <option value="stream">Stream</option>
              </select>

              <input
                type="text"
                placeholder="Filter by action..."
                value={auditActionFilter}
                onChange={(e) => {
                  setAuditActionFilter(e.target.value);
                  setAuditPage(1);
                }}
                className="px-3 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div className="text-xs text-slate-500 font-mono">
              Showing {auditLogs.length} of {totalAuditLogs} events
            </div>
          </div>

          {auditError && (
            <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 text-xs">
              {auditError}
            </div>
          )}

          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/70 border-b border-slate-800 text-slate-400 uppercase text-[10px] tracking-wider font-semibold">
                  <tr>
                    <th className="p-4">Timestamp</th>
                    <th className="p-4">Resource</th>
                    <th className="p-4">Action</th>
                    <th className="p-4">Target Resource ID</th>
                    <th className="p-4">Actor</th>
                    <th className="p-4 text-right">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {isLoadingAudit ? (
                    <tr>
                      <td colSpan={6} className="p-12 text-center text-slate-500">
                        Loading audit logs...
                      </td>
                    </tr>
                  ) : auditLogs.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-12 text-center text-slate-500">
                        No audit records found matching your filters.
                      </td>
                    </tr>
                  ) : (
                    auditLogs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="p-4 font-mono text-slate-400 whitespace-nowrap">
                          {new Date(log.timestamp).toLocaleString()}
                        </td>
                        <td className="p-4 font-mono uppercase text-slate-300">
                          <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px]">
                            {log.resource_type}
                          </span>
                        </td>
                        <td className="p-4">
                          <span className="px-2 py-0.5 rounded font-mono text-[10px] border bg-slate-800 text-slate-300 border-slate-700">
                            {log.action}
                          </span>
                        </td>
                        <td className="p-4 font-mono text-slate-400 max-w-[150px] truncate">
                          {log.resource_id || '—'}
                        </td>
                        <td className="p-4 font-mono text-slate-400 max-w-[150px] truncate">
                          {log.user_id ? log.user_id.slice(0, 12) + '...' : 'System'}
                        </td>
                        <td className="p-4 text-right">
                          <button
                            onClick={() => setSelectedAuditLog(log)}
                            className="text-emerald-400 hover:underline font-mono text-xs"
                          >
                            View &rarr;
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="p-4 bg-slate-950/60 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <span>
                Page {auditPage} of {totalAuditPages}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setAuditPage((p) => Math.max(1, p - 1))}
                  disabled={auditPage <= 1}
                  className="p-1.5 rounded-lg border border-slate-800 bg-slate-900 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-800 text-slate-300"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setAuditPage((p) => Math.min(totalAuditPages, p + 1))}
                  disabled={auditPage >= totalAuditPages}
                  className="p-1.5 rounded-lg border border-slate-800 bg-slate-900 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-800 text-slate-300"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Audit Log Detail Modal */}
      {selectedAuditLog && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Shield className="w-4 h-4 text-emerald-400" />
                Audit Record Details
              </h2>
              <button
                onClick={() => setSelectedAuditLog(null)}
                className="text-slate-400 hover:text-white text-lg"
              >
                &times;
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2 p-3 bg-slate-950 rounded-lg border border-slate-800 font-mono text-[11px]">
                <div>
                  <span className="text-slate-500">Record ID:</span>
                  <p className="text-slate-200 truncate">{selectedAuditLog.id}</p>
                </div>
                <div>
                  <span className="text-slate-500">Timestamp:</span>
                  <p className="text-slate-200 truncate">{new Date(selectedAuditLog.timestamp).toISOString()}</p>
                </div>
                <div>
                  <span className="text-slate-500">Resource:</span>
                  <p className="text-slate-200">{selectedAuditLog.resource_type}</p>
                </div>
                <div>
                  <span className="text-slate-500">Action:</span>
                  <p className="text-slate-200">{selectedAuditLog.action}</p>
                </div>
              </div>
              <div>
                <p className="text-slate-400 uppercase font-semibold text-[10px] mb-1">Details JSON Payload</p>
                <pre className="p-3 bg-slate-950 rounded-lg border border-slate-800 font-mono text-[11px] text-emerald-400 overflow-x-auto max-h-60">
                  {JSON.stringify(selectedAuditLog.details, null, 2)}
                </pre>
              </div>
            </div>
            <div className="pt-3 flex justify-end border-t border-slate-800">
              <button
                onClick={() => setSelectedAuditLog(null)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
