import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Camera as CameraIcon,
  Compass,
  Grid,
  Maximize2,
  Minimize2,
  RefreshCw,
  Video,
  VideoOff,
} from 'lucide-react';
import { Camera, CameraPlayback, Site } from '../types';
import { api } from '../services/api';
import { WebRTCPlayer } from '../components/WebRTCPlayer';
import { StatusBadge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';

// Individual Stream Cell that manages its own playback state
const StreamCell: React.FC<{
  camera: Camera;
  siteName?: string;
  onRestart: (cam: Camera) => void;
}> = ({ camera, siteName, onRestart }) => {
  const [playback, setPlayback] = useState<CameraPlayback | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [streamMode, setStreamMode] = useState<'raw' | 'ai'>('raw');

  const loadPlayback = async () => {
    if (!camera.enabled) {
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.get<CameraPlayback>(`/cameras/${camera.id}/playback`);
      setPlayback(data);
    } catch (err: any) {
      setError(err.message || 'Playback unavailable');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadPlayback();
  }, [camera.id, camera.enabled]);

  const rawWhep = playback?.whep_url || '';
  const aiWhep = playback?.whep_ai_url || (rawWhep ? rawWhep.replace('/whep', '-ai/whep') : '');
  const activeWhep = streamMode === 'ai' ? (aiWhep || rawWhep) : rawWhep;

  const rawHls = playback?.hls_url || '';
  const aiHls = playback?.hls_ai_url || (rawHls ? rawHls.replace('/index.m3u8', '-ai/index.m3u8') : '');
  const activeHls = streamMode === 'ai' ? (aiHls || rawHls) : rawHls;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col shadow-md hover:border-slate-700 transition-colors">
      {/* Top Header */}
      <div className="p-3 bg-slate-950/80 border-b border-slate-800/80 flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <Link
            to={`/cameras/${camera.id}`}
            className="text-xs font-bold text-slate-100 hover:text-emerald-400 truncate"
          >
            {camera.name}
          </Link>
          {siteName && (
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700 truncate">
              {siteName}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {camera.ai_enabled && (
            <button
              onClick={() => setStreamMode((m) => (m === 'ai' ? 'raw' : 'ai'))}
              title={streamMode === 'ai' ? 'Showing AI Bounding Boxes (Click for Raw)' : 'Showing Raw Feed (Click for AI)'}
              className={`px-1.5 py-0.5 rounded text-[10px] font-bold border transition-colors ${
                streamMode === 'ai'
                  ? 'bg-indigo-600 text-white border-indigo-400 shadow-sm'
                  : 'bg-slate-800 text-slate-400 hover:text-slate-200 border-slate-700'
              }`}
            >
              {streamMode === 'ai' ? '⚡ AI' : 'RAW'}
            </button>
          )}
          <StatusBadge status={camera.status} size="sm" />
          <button
            onClick={() => onRestart(camera)}
            title="Restart Stream"
            className="p-1 rounded text-slate-500 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Video Content Area */}
      <div className="relative aspect-video bg-black flex items-center justify-center">
        {!camera.enabled ? (
          <div className="p-4 text-center text-slate-500">
            <VideoOff className="w-8 h-8 mx-auto mb-2 text-slate-600" />
            <p className="text-xs font-medium">Camera Disabled</p>
            <p className="text-[10px] text-slate-600 mt-1">Enable in camera settings to view stream</p>
          </div>
        ) : isLoading ? (
          <div className="p-4 text-center text-slate-400 flex items-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
            <span className="text-xs font-mono">Negotiating WebRTC...</span>
          </div>
        ) : error || !activeWhep ? (
          <div className="p-4 text-center text-rose-400/80">
            <VideoOff className="w-8 h-8 mx-auto mb-2 text-rose-500/60" />
            <p className="text-xs font-medium">{error || 'Stream offline'}</p>
            <button
              onClick={loadPlayback}
              className="mt-2 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-300 font-medium"
            >
              Retry
            </button>
          </div>
        ) : (
          <WebRTCPlayer
            key={`${activeWhep}-${activeHls}`}
            whepUrl={activeWhep}
            hlsUrl={activeHls}
            readerCredentials={playback?.reader_credentials ?? undefined}
            cameraName={`${camera.name} (${streamMode === 'ai' ? 'AI' : 'Raw'})`}
            autoPlay={true}
          />
        )}
      </div>

      {/* Footer Info */}
      <div className="px-3 py-2 bg-slate-950/40 border-t border-slate-800/40 flex items-center justify-between text-[11px] text-slate-500 font-mono">
        <span>/{camera.media_path}</span>
        <Link to={`/cameras/${camera.id}`} className="text-emerald-400 hover:underline">
          Details &rarr;
        </Link>
      </div>
    </div>
  );
};

export const Streams: React.FC = () => {
  const { hasPermission } = useAuth();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSite, setSelectedSite] = useState<string>('');
  const [gridCols, setGridCols] = useState<1 | 2 | 3>(2);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [camData, siteData] = await Promise.all([
        api.get<Camera[]>('/cameras', { site_id: selectedSite || undefined }),
        api.get<Site[]>('/sites'),
      ]);
      setCameras(camData || []);
      setSites(siteData || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load streams');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [selectedSite]);

  const handleRestart = async (cam: Camera) => {
    try {
      await api.post(`/cameras/${cam.id}/restart`);
      alert(`Restart initiated for ${cam.name}`);
      loadData();
    } catch (err: any) {
      alert(`Failed to restart stream: ${err.message}`);
    }
  };

  const siteMap = new Map(sites.map((s) => [s.id, s.name]));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Live Stream Matrix</h1>
          <p className="text-sm text-slate-400 mt-1">
            Low-latency WebRTC surveillance wall with real-time WHEP negotiation
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Site Selector */}
          <select
            value={selectedSite}
            onChange={(e) => setSelectedSite(e.target.value)}
            className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-emerald-500"
          >
            <option value="">All Monitored Sites</option>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>

          {/* Grid Layout Switcher */}
          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-1">
            <button
              onClick={() => setGridCols(1)}
              className={`px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                gridCols === 1 ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              1×1
            </button>
            <button
              onClick={() => setGridCols(2)}
              className={`px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                gridCols === 2 ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              2×2
            </button>
            <button
              onClick={() => setGridCols(3)}
              className={`px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                gridCols === 3 ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              3×3
            </button>
          </div>

          <button
            onClick={loadData}
            title="Refresh stream list"
            className="p-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 text-xs">
          {error}
        </div>
      )}

      {/* Stream Grid */}
      {cameras.length === 0 ? (
        <div className="p-16 text-center rounded-2xl bg-slate-900/40 border border-slate-800/80">
          <CameraIcon className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-base font-semibold text-slate-300">No cameras available</p>
          <p className="text-xs text-slate-500 mt-1">
            Add cameras or select a different site to monitor active streams.
          </p>
          <Link
            to="/cameras"
            className="mt-4 inline-block px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold"
          >
            Manage Cameras
          </Link>
        </div>
      ) : (
        <div
          className={`grid gap-5 ${
            gridCols === 1
              ? 'grid-cols-1 max-w-4xl mx-auto'
              : gridCols === 2
              ? 'grid-cols-1 md:grid-cols-2'
              : 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'
          }`}
        >
          {cameras.map((cam) => (
            <StreamCell
              key={cam.id}
              camera={cam}
              siteName={siteMap.get(cam.site_id)}
              onRestart={handleRestart}
            />
          ))}
        </div>
      )}
    </div>
  );
};
