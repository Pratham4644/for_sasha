import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Camera as CameraIcon,
  Compass,
  Edit2,
  MapPin,
  Plus,
  Power,
  RefreshCw,
  Trash2,
  Video,
} from 'lucide-react';
import { Camera, Site } from '../types';
import { api } from '../services/api';
import { StatusBadge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';

export const SiteDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();

  const [site, setSite] = useState<Site | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Edit Site Modal
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editName, setEditName] = useState('');
  const [editLocation, setEditLocation] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Add Camera Modal
  const [isAddCamOpen, setIsAddCamOpen] = useState(false);
  const [camName, setCamName] = useState('');
  const [camMediaPath, setCamMediaPath] = useState('');
  const [camUrl, setCamUrl] = useState('');
  const [camUsername, setCamUsername] = useState('');
  const [camPassword, setCamPassword] = useState('');
  const [camResolution, setCamResolution] = useState('1920x1080');
  const [camFps, setCamFps] = useState('15');
  const [isAddingCam, setIsAddingCam] = useState(false);
  const [addCamError, setAddCamError] = useState<string | null>(null);

  const loadData = async () => {
    if (!id) return;
    setIsLoading(true);
    setError(null);
    try {
      const [siteData, camData] = await Promise.all([
        api.get<Site>(`/sites/${id}`),
        api.get<Camera[]>('/cameras', { site_id: id }),
      ]);
      setSite(siteData);
      setCameras(camData || []);
      if (siteData) {
        setEditName(siteData.name);
        setEditLocation(siteData.location || '');
        setEditDescription(siteData.description || '');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load site details');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [id]);

  const handleUpdateSite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    setEditError(null);
    setIsUpdating(true);
    try {
      await api.patch(`/sites/${id}`, {
        name: editName.trim(),
        location: editLocation.trim() || undefined,
        description: editDescription.trim() || undefined,
      });
      setIsEditOpen(false);
      loadData();
    } catch (err: any) {
      setEditError(err.message || 'Failed to update site');
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDeleteSite = async () => {
    if (!site || !id) return;
    if (cameras.length > 0) {
      alert(`Cannot delete site with ${cameras.length} active camera(s). Remove all cameras first.`);
      return;
    }
    if (!window.confirm(`Are you sure you want to permanently delete site "${site.name}"?`)) return;

    try {
      await api.delete(`/sites/${id}`);
      navigate('/sites');
    } catch (err: any) {
      alert(`Failed to delete site: ${err.message}`);
    }
  };

  const handleCreateCamera = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    setAddCamError(null);
    setIsAddingCam(true);
    try {
      const payload: Record<string, any> = {
        name: camName.trim(),
        site_id: id,
        source_protocol: 'RTSP',
        ingest_mode: 'EDGE',
        source_url: camUrl.trim(),
        username: camUsername.trim() || null,
        password: camPassword.trim() || null,
        configured_resolution: camResolution.trim() || '1920x1080',
        configured_fps: parseFloat(camFps) || 15.0,
        enabled: true,
      };
      if (camMediaPath.trim()) {
        payload.media_path = camMediaPath.trim();
      }
      await api.post('/cameras', payload);
      setIsAddCamOpen(false);
      setCamName('');
      setCamMediaPath('');
      setCamUrl('');
      setCamUsername('');
      setCamPassword('');
      loadData();
    } catch (err: any) {
      setAddCamError(err.message || 'Failed to create camera');
    } finally {
      setIsAddingCam(false);
    }
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
      alert(`Restart initiated for ${cam.name}`);
      loadData();
    } catch (err: any) {
      alert(`Restart failed: ${err.message}`);
    }
  };

  const handleDeleteCamera = async (cam: Camera) => {
    if (!window.confirm(`Are you sure you want to delete camera "${cam.name}" (${cam.id})?`)) return;
    try {
      await api.delete(`/cameras/${cam.id}`);
      loadData();
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  };


  if (isLoading) {
    return (
      <div className="p-12 text-center text-slate-400 flex items-center justify-center gap-3">
        <RefreshCw className="w-5 h-5 animate-spin text-emerald-400" />
        <span>Loading site configuration...</span>
      </div>
    );
  }

  if (error || !site) {
    return (
      <div className="space-y-4">
        <Link to="/sites" className="inline-flex items-center gap-2 text-xs text-slate-400 hover:text-white">
          <ArrowLeft className="w-4 h-4" /> Back to Sites
        </Link>
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 text-xs">
          {error || 'Site not found'}
        </div>
      </div>
    );
  }

  const total = cameras.length;
  const online = cameras.filter((c) => c.status === 'ONLINE').length;
  const offline = cameras.filter((c) => c.status === 'OFFLINE').length;
  const siteStatus = total === 0 ? 'NO CAMERAS' : online === total ? 'ONLINE' : online > 0 ? 'DEGRADED' : 'OFFLINE';

  return (
    <div className="space-y-6">
      {/* Back button */}
      <div>
        <Link to="/sites" className="inline-flex items-center gap-2 text-xs text-slate-400 hover:text-white transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to Sites
        </Link>
      </div>

      {/* Header Banner */}
      <div className="p-6 bg-slate-900 border border-slate-800 rounded-2xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="p-3.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <Compass className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-white tracking-tight">{site.name}</h1>
              <StatusBadge status={siteStatus} size="sm" />
            </div>
            {site.location && (
              <p className="text-xs text-slate-400 mt-1 flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-slate-500" />
                {site.location}
              </p>
            )}
            {site.description && (
              <p className="text-xs text-slate-500 mt-1.5">{site.description}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {hasPermission('site:update') && (
            <button
              onClick={() => setIsEditOpen(true)}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium border border-slate-700 transition-colors"
            >
              <Edit2 className="w-3.5 h-3.5" />
              Edit Site
            </button>
          )}

          {hasPermission('camera:create') && (
            <button
              onClick={() => setIsAddCamOpen(true)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow-lg shadow-emerald-950/40 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Add Camera Here
            </button>
          )}

          {hasPermission('site:delete') && (
            <button
              onClick={handleDeleteSite}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-rose-950/40 hover:bg-rose-950 border border-rose-800 text-rose-300 text-xs font-medium transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete Site
            </button>
          )}
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-3 gap-4">
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wider">Total Cameras</p>
          <p className="text-2xl font-bold text-slate-100 mt-1">{total}</p>
        </div>
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
          <p className="text-xs text-emerald-500 font-medium uppercase tracking-wider">Online</p>
          <p className="text-2xl font-bold text-emerald-400 mt-1">{online}</p>
        </div>
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
          <p className="text-xs text-rose-500 font-medium uppercase tracking-wider">Offline</p>
          <p className="text-2xl font-bold text-rose-400 mt-1">{offline}</p>
        </div>
      </div>

      {/* Cameras at this Site */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white tracking-tight">Cameras Assigned to this Site</h2>
          <button
            onClick={loadData}
            className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white text-xs inline-flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>

        {cameras.length === 0 ? (
          <div className="p-12 text-center rounded-2xl bg-slate-900/40 border border-slate-800/80">
            <CameraIcon className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <p className="text-sm text-slate-400">No cameras configured for this site yet.</p>
            {hasPermission('camera:create') && (
              <button
                onClick={() => setIsAddCamOpen(true)}
                className="mt-3 inline-block px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold"
              >
                Add First Camera
              </button>
            )}
          </div>
        ) : (
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden divide-y divide-slate-800">
            {cameras.map((cam) => (
              <div
                key={cam.id}
                className="p-4 flex flex-wrap items-center justify-between gap-4 hover:bg-slate-800/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-400">
                    <Video className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <Link to={`/cameras/${cam.id}`} className="font-semibold text-sm text-slate-200 hover:text-emerald-400">
                        {cam.name}
                      </Link>
                      <StatusBadge status={cam.status} size="sm" />
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-500 mt-1">
                      <span className="font-mono">/{cam.media_path}</span>
                      <span>•</span>
                      <span>{cam.configured_resolution || '1080p'}</span>
                      <span>•</span>
                      <span>{cam.configured_fps || 15} fps</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Link
                    to={`/cameras/${cam.id}`}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium border border-slate-700 transition-colors"
                  >
                    View Stream
                  </Link>

                  {hasPermission('camera:update') && (
                    <button
                      onClick={() => handleToggleEnable(cam)}
                      title={cam.enabled ? 'Disable Camera' : 'Enable Camera'}
                      className={`p-1.5 rounded-lg border text-xs font-medium transition-colors ${
                        cam.enabled
                          ? 'bg-slate-800 border-slate-700 text-emerald-400 hover:text-rose-400'
                          : 'bg-rose-950/60 border-rose-800 text-rose-300 hover:text-emerald-400'
                      }`}
                    >
                      <Power className="w-3.5 h-3.5" />
                    </button>
                  )}

                  {hasPermission('stream:control') && cam.enabled && (
                    <button
                      onClick={() => handleRestartStream(cam)}
                      title="Restart Stream"
                      className="p-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:text-white transition-colors"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                  )}

                  {hasPermission('camera:delete') && (
                    <button
                      onClick={() => handleDeleteCamera(cam)}
                      title="Delete Camera"
                      className="p-1.5 rounded-lg bg-slate-800 hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 border border-slate-700 hover:border-rose-800 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Edit Site Modal */}
      {isEditOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-base font-bold text-white">Edit Site Details</h2>
              <button onClick={() => setIsEditOpen(false)} className="text-slate-400 hover:text-white">&times;</button>
            </div>

            {editError && (
              <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-xs text-rose-300">
                {editError}
              </div>
            )}

            <form onSubmit={handleUpdateSite} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-400 uppercase font-semibold mb-1">Site Name</label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 uppercase font-semibold mb-1">Location</label>
                <input
                  type="text"
                  value={editLocation}
                  onChange={(e) => setEditLocation(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 uppercase font-semibold mb-1">Description</label>
                <textarea
                  rows={3}
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="pt-3 flex justify-end gap-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsEditOpen(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isUpdating}
                  className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold"
                >
                  {isUpdating ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Camera Modal */}
      {isAddCamOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-base font-bold text-white">Add Camera to {site.name}</h2>
              <button onClick={() => setIsAddCamOpen(false)} className="text-slate-400 hover:text-white">&times;</button>
            </div>

            {addCamError && (
              <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-xs text-rose-300">
                {addCamError}
              </div>
            )}

            <form onSubmit={handleCreateCamera} className="space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 uppercase font-semibold mb-1">Camera Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Front Gate East"
                    value={camName}
                    onChange={(e) => setCamName(e.target.value)}
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
                    value={camMediaPath}
                    onChange={(e) => setCamMediaPath(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
                  />
                  <p className="text-[10px] text-slate-500 mt-1">Leave empty to auto-generate a secure MediaMTX identifier</p>
                </div>
              </div>

              <div>
                <label className="block text-slate-400 uppercase font-semibold mb-1">Source RTSP URL</label>
                <input
                  type="text"
                  required
                  placeholder="rtsp://192.168.1.100:554/live/ch0"
                  value={camUrl}
                  onChange={(e) => setCamUrl(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 uppercase font-semibold mb-1">Camera Username</label>
                  <input
                    type="text"
                    placeholder="Optional username"
                    value={camUsername}
                    onChange={(e) => setCamUsername(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 uppercase font-semibold mb-1">Camera Password</label>
                  <input
                    type="password"
                    placeholder="Optional password"
                    value={camPassword}
                    onChange={(e) => setCamPassword(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 uppercase font-semibold mb-1">Resolution</label>
                  <select
                    value={camResolution}
                    onChange={(e) => setCamResolution(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="1920x1080">1920x1080 (1080p)</option>
                    <option value="1280x720">1280x720 (720p)</option>
                    <option value="640x480">640x480 (VGA)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 uppercase font-semibold mb-1">Target FPS</label>
                  <select
                    value={camFps}
                    onChange={(e) => setCamFps(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="15">15 FPS</option>
                    <option value="25">25 FPS</option>
                    <option value="30">30 FPS</option>
                  </select>
                </div>
              </div>

              <div className="pt-3 flex justify-end gap-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsAddCamOpen(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isAddingCam}
                  className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold"
                >
                  {isAddingCam ? 'Adding...' : 'Add Camera'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
