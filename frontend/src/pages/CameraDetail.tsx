import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  CheckCircle,
  Copy,
  Cpu,
  Eye,
  Play,
  Power,
  RefreshCw,
  Shield,
  Video,
  Zap,
} from 'lucide-react';
import { CameraDetail as CameraDetailType, CameraPlayback, DetectionEvent, Site } from '../types';
import { api } from '../services/api';
import { WebRTCPlayer } from '../components/WebRTCPlayer';
import { StatusBadge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';
import { useDetectionSocket } from '../context/DetectionSocketContext';

export const CameraDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const { latestDetection } = useDetectionSocket();

  const [camera, setCamera] = useState<CameraDetailType | null>(null);
  const [playback, setPlayback] = useState<CameraPlayback | null>(null);
  const [site, setSite] = useState<Site | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Stream toggle state: 'raw' vs 'ai'
  const [streamMode, setStreamMode] = useState<'raw' | 'ai'>('raw');

  // Detection events state for this camera
  const [detections, setDetections] = useState<DetectionEvent[]>([]);
  const [isLoadingDetections, setIsLoadingDetections] = useState<boolean>(false);

  // Connection test state
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [isTesting, setIsTesting] = useState<boolean>(false);
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);

  const loadCamera = async () => {
    if (!id) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.get<CameraDetailType>(`/cameras/${id}`);
      setCamera(data);

      if (data?.enabled) {
        try {
          const pb = await api.get<CameraPlayback>(`/cameras/${id}/playback`);
          setPlayback(pb);
        } catch {
          setPlayback(null);
        }
      }

      if (data?.site_id) {
        try {
          const s = await api.get<Site>(`/sites/${data.site_id}`);
          setSite(s);
        } catch {
          // ignore site fetch error
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load camera');
    } finally {
      setIsLoading(false);
    }
  };

  const loadDetections = async () => {
    if (!id) return;
    setIsLoadingDetections(true);
    try {
      const res = await api.get<{ items: DetectionEvent[]; total: number }>(`/cameras/${id}/detections`, {
        limit: 15,
      });
      setDetections(res.items || []);
    } catch {
      // ignore detection load error
    } finally {
      setIsLoadingDetections(false);
    }
  };

  useEffect(() => {
    loadCamera();
    loadDetections();
  }, [id]);

  // Reactive detection event updates via WebSocket
  useEffect(() => {
    if (latestDetection && camera && (latestDetection.camera_id === camera.id || latestDetection.camera_id === camera.media_path)) {
      setDetections((prev) => [latestDetection, ...prev.slice(0, 24)]);
    }
  }, [latestDetection, camera]);

  const handleTestConnection = async () => {
    if (!id) return;
    setIsTesting(true);
    setTestResult(null);
    try {
      const res = await api.post<{ ok: boolean; message: string }>(`/cameras/${id}/test`);
      setTestResult(res);
    } catch (err: any) {
      setTestResult({ ok: false, message: err.message || 'Connection test failed' });
    } finally {
      setIsTesting(false);
    }
  };

  const handleStartStop = async () => {
    if (!camera) return;
    try {
      const isOnline = camera.status === 'ONLINE';
      const action = isOnline ? 'stop' : 'start';
      await api.post(`/cameras/${camera.id}/${action}`);
      await loadCamera();
    } catch (err: any) {
      alert(`Action failed: ${err.message}`);
    }
  };

  const handleRestart = async () => {
    if (!camera) return;
    try {
      await api.post(`/cameras/${camera.id}/restart`);
      alert('Stream ingestion restart initiated.');
      loadCamera();
    } catch (err: any) {
      alert(`Restart failed: ${err.message}`);
    }
  };

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopiedUrl(label);
    setTimeout(() => setCopiedUrl(null), 2000);
  };

  if (isLoading) {
    return (
      <div className="h-96 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 text-emerald-500 animate-spin" />
          <p className="text-xs font-mono text-slate-400">Loading camera telemetry...</p>
        </div>
      </div>
    );
  }

  if (error || !camera) {
    return (
      <div className="p-8 text-center space-y-4">
        <p className="text-rose-400 text-sm">{error || 'Camera not found'}</p>
        <Link to="/cameras" className="text-xs text-emerald-400 hover:underline">
          &larr; Back to cameras list
        </Link>
      </div>
    );
  }

  const rawWhepUrl = playback?.whep_url || camera.whep_url || '';
  const aiWhepUrl = playback?.whep_ai_url || (rawWhepUrl ? rawWhepUrl.replace('/whep', '-ai/whep') : '');
  const activeWhepUrl = streamMode === 'ai' ? aiWhepUrl : rawWhepUrl;

  const rawHlsUrl = playback?.hls_url || '';
  const aiHlsUrl = playback?.hls_ai_url || (rawHlsUrl ? rawHlsUrl.replace('/index.m3u8', '-ai/index.m3u8') : '');
  const activeHlsUrl = streamMode === 'ai' ? aiHlsUrl : rawHlsUrl;

  return (
    <div className="space-y-6">
      {/* Back button & Title header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/cameras')}
            className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:border-slate-700 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-white tracking-tight">{camera.name}</h1>
              <StatusBadge status={camera.status} />
              {camera.ai_enabled && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                  <Zap className="w-3 h-3 text-emerald-400" />
                  AI Active ({camera.ai_model || 'YOLO'})
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Site: <span className="text-slate-300 font-semibold">{site?.name || camera.site_id.slice(0, 8)}</span> • Path: <span className="font-mono text-emerald-400">/{camera.media_path}</span>
            </p>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-3">
          {hasPermission('camera:read') && (
            <button
              onClick={handleTestConnection}
              disabled={isTesting}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs font-medium text-slate-300 hover:text-white transition-colors"
            >
              <Activity className={`w-3.5 h-3.5 ${isTesting ? 'animate-spin' : ''}`} />
              {isTesting ? 'Testing Link...' : 'Test Source Probe'}
            </button>
          )}

          {hasPermission('camera:update') && (
            <>
              <button
                onClick={handleRestart}
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs font-medium text-slate-300 hover:text-white transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Restart Stream
              </button>

              <button
                onClick={handleStartStop}
                className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium border transition-colors ${
                  camera.status === 'ONLINE'
                    ? 'bg-rose-950/40 border-rose-800/80 text-rose-300 hover:bg-rose-900/60'
                    : 'bg-emerald-950/40 border-emerald-800/80 text-emerald-300 hover:bg-emerald-900/60'
                }`}
              >
                <Power className="w-3.5 h-3.5" />
                {camera.status === 'ONLINE' ? 'Stop Camera' : 'Start Camera'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Connection Test Banner if executed */}
      {testResult && (
        <div
          className={`p-4 rounded-xl border text-xs flex items-center justify-between ${
            testResult.ok
              ? 'bg-emerald-950/60 border-emerald-800/80 text-emerald-300'
              : 'bg-rose-950/60 border-rose-800/80 text-rose-300'
          }`}
        >
          <div className="flex items-center gap-2.5">
            {testResult.ok ? <CheckCircle className="w-4 h-4 text-emerald-400" /> : <AlertTriangle className="w-4 h-4 text-rose-400" />}
            <span className="font-medium">{testResult.message}</span>
          </div>
          <button onClick={() => setTestResult(null)} className="text-slate-400 hover:text-white">
            Dismiss
          </button>
        </div>
      )}

      {/* Main Grid: Player + Telemetry */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Player with Stream Switcher */}
        <div className="lg:col-span-2 space-y-4">
          {/* Stream Selector Controls */}
          <div className="flex items-center justify-between bg-slate-900/80 border border-slate-800 p-2 rounded-xl">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setStreamMode('raw')}
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  streamMode === 'raw'
                    ? 'bg-emerald-500 text-slate-950 font-bold shadow-md'
                    : 'text-slate-400 hover:text-white bg-slate-800/50'
                }`}
              >
                <Video className="w-3.5 h-3.5" />
                Live Direct Stream
              </button>
              <button
                onClick={() => setStreamMode('ai')}
                disabled={!camera.ai_enabled}
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  streamMode === 'ai'
                    ? 'bg-indigo-500 text-white font-bold shadow-md shadow-indigo-500/20'
                    : camera.ai_enabled
                    ? 'text-slate-400 hover:text-white bg-slate-800/50'
                    : 'text-slate-600 bg-slate-900 cursor-not-allowed'
                }`}
              >
                <Cpu className="w-3.5 h-3.5" />
                Live AI Stream (Bounding Boxes)
              </button>
            </div>
            <div className="text-[11px] font-mono text-slate-400 pr-2">
              Mode: <span className="text-emerald-400 font-semibold">{streamMode === 'ai' ? 'AI Overlay' : 'Raw Feed'}</span>
            </div>
          </div>

          <WebRTCPlayer
            key={`${activeWhepUrl}-${activeHlsUrl}`}
            whepUrl={activeWhepUrl}
            hlsUrl={activeHlsUrl}
            readerCredentials={playback?.reader_credentials ?? undefined}
            cameraName={`${camera.name} (${streamMode === 'ai' ? 'AI Stream' : 'Raw Stream'})`}
          />

          {/* Quick Stream Endpoints Card */}
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Integration Endpoints (MediaMTX)
            </h3>
            <div className="space-y-2 text-xs font-mono">
              {rawWhepUrl && (
                <div className="flex items-center justify-between p-2.5 bg-slate-950 rounded-lg border border-slate-800">
                  <span className="text-slate-400">WebRTC WHEP (Raw):</span>
                  <div className="flex items-center gap-2">
                    <span className="text-emerald-400 truncate max-w-sm">{rawWhepUrl}</span>
                    <button
                      onClick={() => handleCopy(rawWhepUrl, 'webrtc_raw')}
                      className="p-1 hover:text-white text-slate-500"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              )}

              {aiWhepUrl && (
                <div className="flex items-center justify-between p-2.5 bg-slate-950 rounded-lg border border-slate-800">
                  <span className="text-slate-400">WebRTC WHEP (AI Feed):</span>
                  <div className="flex items-center gap-2">
                    <span className="text-indigo-400 truncate max-w-sm">{aiWhepUrl}</span>
                    <button
                      onClick={() => handleCopy(aiWhepUrl, 'webrtc_ai')}
                      className="p-1 hover:text-white text-slate-500"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              )}
            </div>
            {copiedUrl && <p className="text-[11px] text-emerald-400">Copied {copiedUrl} URL to clipboard!</p>}
          </div>

          {/* Live Real-Time Detection Events Section */}
          <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-emerald-400" />
                <h3 className="text-sm font-bold text-white tracking-tight">Recent Detection Events</h3>
              </div>
              <span className="text-[11px] font-mono text-slate-400">
                {detections.length} recorded
              </span>
            </div>

            {detections.length === 0 ? (
              <div className="py-8 text-center text-slate-500 text-xs">
                No detection events recorded for this camera yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/60 text-slate-400 uppercase text-[10px]">
                    <tr>
                      <th className="p-2.5">Time</th>
                      <th className="p-2.5">Detected Class</th>
                      <th className="p-2.5">Confidence</th>
                      <th className="p-2.5">Model</th>
                      <th className="p-2.5 text-right">Latency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono">
                    {detections.slice(0, 10).map((det) => (
                      <tr key={det.id} className="hover:bg-slate-800/30 transition-colors">
                        <td className="p-2.5 text-slate-400 whitespace-nowrap">
                          {new Date(det.timestamp).toLocaleTimeString()}
                        </td>
                        <td className="p-2.5">
                          <span className="font-semibold text-emerald-400 capitalize">
                            {det.class_name}
                          </span>
                        </td>
                        <td className="p-2.5">
                          <span className="inline-block px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 font-medium">
                            {(det.confidence * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="p-2.5 text-slate-400">
                          {det.model_name || 'yolo'}
                        </td>
                        <td className="p-2.5 text-right text-slate-400">
                          {det.inference_latency_ms ? `${det.inference_latency_ms.toFixed(0)}ms` : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right Col: Telemetry & Spec */}
        <div className="space-y-6">
          <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl space-y-4">
            <h2 className="text-sm font-bold text-white tracking-tight border-b border-slate-800 pb-3">
              Camera Configuration
            </h2>

            <div className="space-y-3 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Status:</span>
                <StatusBadge status={camera.status} size="sm" />
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Configured FPS:</span>
                <span className="font-mono text-slate-200">{camera.configured_fps || 15} fps</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Resolution:</span>
                <span className="font-mono text-slate-200">{camera.configured_resolution || 'Auto'}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Protocol:</span>
                <span className="font-mono text-slate-200">{camera.source_protocol}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Credentials:</span>
                <span className="text-slate-200 font-mono">
                  {camera.has_credentials ? 'Encrypted (AES-256)' : 'None'}
                </span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-slate-400">AI Pipeline:</span>
                <span className={`font-semibold ${camera.ai_enabled ? 'text-emerald-400' : 'text-slate-500'}`}>
                  {camera.ai_enabled ? `Enabled (${camera.ai_model || 'yolo'})` : 'Disabled'}
                </span>
              </div>
            </div>
          </div>

          {/* AI Architecture Telemetry Card */}
          <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-400" />
              <h2 className="text-sm font-bold text-white tracking-tight">AI & Inference Engine</h2>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Inference Target:</span>
                <span className="font-mono text-slate-200">AWS SageMaker</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Model Endpoint:</span>
                <span className="font-mono text-slate-300 text-[11px] truncate max-w-[150px]">
                  {camera.ai_endpoint || 'yolo26s-cctv-endpoint'}
                </span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-slate-400">Overlay Relay:</span>
                <span className="font-mono text-emerald-400">/{camera.media_path}-ai</span>
              </div>
            </div>
          </div>

          {playback && (
            <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
              <h2 className="text-sm font-bold text-white tracking-tight">Live Media State</h2>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-slate-800/60">
                  <span className="text-slate-400">Control:</span>
                  <span className="font-mono text-slate-200">{playback.control_state}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800/60">
                  <span className="text-slate-400">Media:</span>
                  <span className="font-mono text-slate-200">{playback.media_state}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-400">Ingest:</span>
                  <span className="font-mono text-slate-200">{playback.ingest_state}</span>
                </div>
              </div>
            </div>
          )}

          <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
            <h2 className="text-sm font-bold text-white tracking-tight">Security & Ingestion</h2>
            <p className="text-xs text-slate-400 leading-relaxed">
              Video is ingested over TCP with low-latency flags (<span className="font-mono text-slate-300">-fflags nobuffer</span>) directly into MediaMTX, terminating into WebRTC WHEP for browser playback without buffering.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
