import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Camera as CameraIcon,
  Eye,
  Plus,
  Power,
  RefreshCw,
  Search,
  Trash2,
  Zap,
} from 'lucide-react';
import { Camera, Site } from '../types';
import { api } from '../services/api';
import { StatusBadge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';

export const Cameras: React.FC = () => {
  const { user, hasPermission } = useAuth();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState<string>('');
  const [selectedSite, setSelectedSite] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');

  // Add Camera Modal State
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [newCamName, setNewCamName] = useState('');
  const [newCamSite, setNewCamSite] = useState('');
  const [newCamMediaPath, setNewCamMediaPath] = useState('');
  const [newCamUrl, setNewCamUrl] = useState('');
  const [newCamUsername, setNewCamUsername] = useState('');
  const [newCamPassword, setNewCamPassword] = useState('');
  const [newCamResolution, setNewCamResolution] = useState('1920x1080');
  const [newCamFps, setNewCamFps] = useState('15');
  const [newCamAiEnabled, setNewCamAiEnabled] = useState(true);
  const [newCamAiModel, setNewCamAiModel] = useState('yolo');
  const [newCamAiEndpoint, setNewCamAiEndpoint] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [cams, sList] = await Promise.all([
        api.get<Camera[]>('/cameras', {
          site_id: selectedSite || undefined,
          status: selectedStatus || undefined,
          search: search || undefined,
        }),
        api.get<Site[]>('/sites'),
      ]);
      setCameras(cams || []);
      setSites(sList || []);
      if (!newCamSite && sList && sList.length > 0) {
        setNewCamSite(sList[0].id);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load cameras');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [selectedSite, selectedStatus]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadData();
  };

  const handleToggleEnable = async (cam: Camera) => {
    try {
      const action = cam.enabled ? 'disable' : 'enable';
      await api.post(`/cameras/${cam.id}/${action}`);
      loadData();
    } catch (err: any) {
      alert(`Operation failed: ${err.message}`);
    }
  };

  const handleRestartStream = async (cam: Camera) => {
    try {
      await api.post(`/cameras/${cam.id}/restart`);
      alert(`Stream restart initiated for ${cam.name}`);
      loadData();
    } catch (err: any) {
      alert(`Restart failed: ${err.message}`);
    }
  };

  const handleDelete = async (cam: Camera) => {
    if (!window.confirm(`Are you sure you want to delete camera "${cam.name}" (${cam.id})?`)) return;
    try {
      await api.delete(`/cameras/${cam.id}`);
      loadData();
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const handleCreateCamera = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setIsSubmitting(true);
    try {
      const firstSite = sites[0]?.id || '';
      const siteId = newCamSite || firstSite;
      const payload: Record<string, any> = {
        name: newCamName.trim(),
        site_id: siteId,
        source_protocol: 'RTSP',
        ingest_mode: 'EDGE',
        source_url: newCamUrl.trim(),
        username: newCamUsername ? newCamUsername.trim() : null,
        password: newCamPassword ? newCamPassword.trim() : null,
        configured_resolution: newCamResolution.trim() || '1920x1080',
        configured_fps: parseFloat(newCamFps) || 15.0,
        enabled: true,
        ai_enabled: newCamAiEnabled,
        ai_model: newCamAiModel.trim() || 'yolo',
        ai_endpoint: newCamAiEndpoint.trim() || null,
      };
      if (newCamMediaPath.trim()) {
        payload.media_path = newCamMediaPath.trim();
      }
      await api.post('/cameras', payload);
      setIsModalOpen(false);
      setNewCamName('');
      setNewCamMediaPath('');
      setNewCamUrl('');
      setNewCamUsername('');
      setNewCamPassword('');
      setNewCamAiEndpoint('');
      loadData();
    } catch (err: any) {
      setFormError(err.message || 'Failed to create camera');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Camera Management</h1>
          <p className="text-sm text-slate-400 mt-1">Configure RTSP streams, verify connectivity, and inspect feeds</p>
        </div>
        {hasPermission('camera:create') && (
          <button
            onClick={() => setIsModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors shadow-lg shadow-emerald-950/40"
          >
            <Plus className="w-4 h-4" />
            Add Camera
          </button>
        )}
      </div>

      {/* Filters Bar */}
      <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl flex flex-wrap items-center justify-between gap-4">
        <form onSubmit={handleSearchSubmit} className="flex-1 min-w-[240px] relative">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-3" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by camera name or description..."
            className="w-full pl-10 pr-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-emerald-500"
          />
        </form>

        <div className="flex items-center gap-3">
          <select
            value={selectedSite}
            onChange={(e) => setSelectedSite(e.target.value)}
            className="px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-emerald-500"
          >
            <option value="">All Sites</option>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>

          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-emerald-500"
          >
            <option value="">All Statuses</option>
            <option value="ONLINE">ONLINE</option>
            <option value="OFFLINE">OFFLINE</option>
            <option value="DEGRADED">DEGRADED</option>
            <option value="UNKNOWN">UNKNOWN</option>
          </select>

          <button
            onClick={loadData}
            title="Refresh list"
            className="p-2 rounded-lg bg-slate-950 border border-slate-800 hover:border-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Cameras Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 border-b border-slate-800 text-slate-400 uppercase font-mono tracking-wider">
              <tr>
                <th className="py-3.5 px-4">Camera</th>
                <th className="py-3.5 px-4">Site</th>
                <th className="py-3.5 px-4">Protocol</th>
                <th className="py-3.5 px-4">MediaMTX Path</th>
                <th className="py-3.5 px-4">Status</th>
                <th className="py-3.5 px-4">Stream</th>
                <th className="py-3.5 px-4">AI Pipeline</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {cameras.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-16 text-center">
                    {sites.length === 0 ? (
                      <div className="max-w-sm mx-auto space-y-3">
                        <CameraIcon className="w-10 h-10 text-slate-600 mx-auto" />
                        <p className="text-sm font-semibold text-slate-300">No Sites Configured</p>
                        <p className="text-xs text-slate-400">
                          In this multi-tenant platform, cameras must be attached to an organization site. Please create your first site before adding cameras.
                        </p>
                        <Link
                          to="/sites"
                          className="inline-block px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md transition-colors"
                        >
                          Create First Site &rarr;
                        </Link>
                      </div>
                    ) : (
                      <div className="max-w-sm mx-auto space-y-3">
                        <CameraIcon className="w-10 h-10 text-slate-600 mx-auto" />
                        <p className="text-sm font-semibold text-slate-300">No Cameras Registered</p>
                        <p className="text-xs text-slate-400">
                          Add your first RTSP stream to begin low-latency WebRTC surveillance.
                        </p>
                        {hasPermission('camera:create') && (
                          <button
                            onClick={() => setIsModalOpen(true)}
                            className="inline-block px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md transition-colors"
                          >
                            Add Your First Camera
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ) : (
                cameras.map((cam) => (
                  <tr key={cam.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-slate-800/80 border border-slate-700/60 text-slate-400">
                          <CameraIcon className="w-4 h-4" />
                        </div>
                        <div>
                          <Link
                            to={`/cameras/${cam.id}`}
                            className="font-semibold text-slate-100 hover:text-emerald-400 transition-colors"
                          >
                            {cam.name}
                          </Link>
                          <p className="text-[11px] text-slate-500 font-mono mt-0.5">ID: {cam.id.slice(0, 8)}...</p>
                        </div>
                      </div>
                    </td>

                    <td className="py-3.5 px-4">
                      <span className="font-medium text-slate-300">
                        {sites.find((s) => s.id === cam.site_id)?.name || cam.site_id.slice(0, 8)}
                      </span>
                    </td>

                    <td className="py-3.5 px-4">
                      <span className="font-mono text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                        {cam.source_protocol}
                      </span>
                    </td>

                    <td className="py-3.5 px-4 font-mono text-[11px] text-slate-400">
                      /{cam.media_path}
                    </td>

                    <td className="py-3.5 px-4">
                      <StatusBadge status={cam.status} size="sm" />
                    </td>

                    <td className="py-3.5 px-4">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium border ${
                          cam.enabled
                            ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/60'
                            : 'bg-slate-800 text-slate-500 border-slate-700'
                        }`}
                      >
                        {cam.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </td>

                    <td className="py-3.5 px-4">
                      {cam.ai_enabled ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                          <Zap className="w-3 h-3 text-emerald-400" />
                          {cam.ai_model || 'yolo'}
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-500 font-mono">Off</span>
                      )}
                    </td>

                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <Link
                          to={`/cameras/${cam.id}`}
                          title="View Camera Detail"
                          className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </Link>

                        {hasPermission('camera:update') && (
                          <>
                            <button
                              onClick={() => handleToggleEnable(cam)}
                              title={cam.enabled ? 'Disable Camera' : 'Enable Camera'}
                              className={`p-1.5 rounded-lg border transition-colors ${
                                cam.enabled
                                  ? 'bg-slate-800 hover:bg-amber-950/40 text-slate-400 hover:text-amber-400 border-slate-700 hover:border-amber-800'
                                  : 'bg-slate-800 hover:bg-emerald-950/40 text-slate-400 hover:text-emerald-400 border-slate-700 hover:border-emerald-800'
                              }`}
                            >
                              <Power className="w-3.5 h-3.5" />
                            </button>

                            <button
                              onClick={() => handleRestartStream(cam)}
                              title="Restart Ingestion Stream"
                              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white border border-slate-700 transition-colors"
                            >
                              <RefreshCw className="w-3.5 h-3.5" />
                            </button>
                          </>
                        )}

                        {hasPermission('camera:delete') && (
                          <button
                            onClick={() => handleDelete(cam)}
                            title="Delete Camera"
                            className="p-1.5 rounded-lg bg-slate-800 hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 border border-slate-700 hover:border-rose-800 transition-colors"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Camera Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <h2 className="text-lg font-bold text-white tracking-tight">Add New Camera</h2>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                &times;
              </button>
            </div>

            {formError && (
              <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-xs text-rose-300">
                {formError}
              </div>
            )}

            {sites.length === 0 ? (
              <div className="p-6 text-center rounded-xl bg-amber-950/40 border border-amber-800/60 text-amber-200 text-xs space-y-3">
                <p className="font-semibold text-sm">No Monitored Sites Found</p>
                <p className="text-slate-400 max-w-sm mx-auto">
                  In a multi-tenant environment, every camera must be anchored to a physical site within your organization.
                </p>
                <Link
                  to="/sites"
                  className="inline-block px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-md transition-colors"
                >
                  Create Your First Site &rarr;
                </Link>
              </div>
            ) : (
              <form onSubmit={handleCreateCamera} className="space-y-4 text-xs">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-slate-400 uppercase font-semibold mb-1">Friendly Name</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Front Gate East"
                      value={newCamName}
                      onChange={(e) => setNewCamName(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 uppercase font-semibold mb-1">
                      Media Path <span className="text-slate-500 font-normal lowercase">(optional)</span>
                    </label>
                    <input
                      type="text"
                      placeholder="Auto-generated (cam_<UUID>)"
                      value={newCamMediaPath}
                      onChange={(e) => setNewCamMediaPath(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
                    />
                    <p className="text-[10px] text-slate-500 mt-1">Leave empty to auto-generate a secure MediaMTX identifier</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-slate-400 uppercase font-semibold mb-1">Site</label>
                    <select
                      value={newCamSite || (sites[0]?.id || '')}
                      onChange={(e) => setNewCamSite(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                    >
                      {sites.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-slate-400 uppercase font-semibold mb-1">Resolution</label>
                    <input
                      type="text"
                      value={newCamResolution}
                      onChange={(e) => setNewCamResolution(e.target.value)}
                      placeholder="1920x1080"
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-slate-400 uppercase font-semibold mb-1">Source RTSP URL</label>
                  <input
                    type="text"
                    required
                    placeholder="rtsp://192.168.1.100:554/Streaming/Channels/101"
                    value={newCamUrl}
                    onChange={(e) => setNewCamUrl(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-slate-400 uppercase font-semibold mb-1">Username (Optional)</label>
                    <input
                      type="text"
                      value={newCamUsername}
                      onChange={(e) => setNewCamUsername(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 uppercase font-semibold mb-1">Password (Optional)</label>
                    <input
                      type="password"
                      value={newCamPassword}
                      onChange={(e) => setNewCamPassword(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>

                <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-lg space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-semibold text-slate-200">Enable AI Object Detection</span>
                      <p className="text-[11px] text-slate-400">Routes camera frames to SageMaker inference and generates bounding boxes</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={newCamAiEnabled}
                      onChange={(e) => setNewCamAiEnabled(e.target.checked)}
                      className="w-4 h-4 rounded text-emerald-500 focus:ring-emerald-500 bg-slate-900 border-slate-700"
                    />
                  </div>
                  {newCamAiEnabled && (
                    <div className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-800/80">
                      <div>
                        <label className="block text-slate-400 uppercase text-[10px] font-semibold mb-1">AI Model</label>
                        <input
                          type="text"
                          value={newCamAiModel}
                          onChange={(e) => setNewCamAiModel(e.target.value)}
                          placeholder="yolo"
                          className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-800 rounded text-slate-100 text-xs"
                        />
                      </div>
                      <div>
                        <label className="block text-slate-400 uppercase text-[10px] font-semibold mb-1">SageMaker Endpoint (Optional)</label>
                        <input
                          type="text"
                          value={newCamAiEndpoint}
                          onChange={(e) => setNewCamAiEndpoint(e.target.value)}
                          placeholder="Default Cluster Endpoint"
                          className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-800 rounded text-slate-100 text-xs"
                        />
                      </div>
                    </div>
                  )}
                </div>

                <div className="pt-4 flex items-center justify-end gap-3 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setIsModalOpen(false)}
                    className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-lg shadow-emerald-950/40"
                  >
                    {isSubmitting ? 'Registering...' : 'Add Camera'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
