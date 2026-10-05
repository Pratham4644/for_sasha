import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Camera as CameraIcon, Compass, MapPin, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { Camera, Site } from '../types';
import { api } from '../services/api';
import { StatusBadge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';

export const Sites: React.FC = () => {
  const { hasPermission } = useAuth();
  const [sites, setSites] = useState<Site[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Add Site Modal
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [description, setDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadSites = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [siteList, cameraList] = await Promise.all([
        api.get<Site[]>('/sites'),
        api.get<Camera[]>('/cameras').catch(() => [] as Camera[]),
      ]);
      setSites(siteList || []);
      setCameras(cameraList || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load sites');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadSites();
  }, []);

  const handleCreateSite = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setIsSubmitting(true);
    try {
      await api.post('/sites', {
        name: name.trim(),
        location: location.trim() || undefined,
        description: description.trim() || undefined,
      });
      setIsModalOpen(false);
      setName('');
      setLocation('');
      setDescription('');
      loadSites();
    } catch (err: any) {
      setFormError(err.message || 'Failed to create site');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (s: Site) => {
    if (!window.confirm(`Delete site "${s.name}"?`)) return;
    try {
      await api.delete(`/sites/${s.id}`);
      loadSites();
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Monitored Sites</h1>
          <p className="text-sm text-slate-400 mt-1">Multi-site physical facility and campus camera groupings</p>
        </div>
        {hasPermission('site:create') && (
          <button
            onClick={() => setIsModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors shadow-lg shadow-emerald-950/40"
          >
            <Plus className="w-4 h-4" />
            Add Site
          </button>
        )}
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800/80 text-rose-300 text-xs">
          {error}
        </div>
      )}

      {/* Sites Grid or Empty State */}
      {sites.length === 0 && !isLoading ? (
        <div className="p-16 text-center rounded-2xl bg-slate-900/40 border border-slate-800/80 max-w-lg mx-auto">
          <div className="p-3.5 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 w-fit mx-auto mb-4">
            <Compass className="w-8 h-8" />
          </div>
          <h2 className="text-base font-bold text-slate-100">No sites created yet</h2>
          <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto leading-relaxed">
            Create physical or logical sites (e.g. Headquarters, Factory A, Dock 4) to group and organize your camera installations.
          </p>
          {hasPermission('site:create') && (
            <button
              onClick={() => setIsModalOpen(true)}
              className="mt-5 inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-lg shadow-emerald-950/40 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Create First Site
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {sites.map((s) => {
          const siteCams = cameras.filter((c) => c.site_id === s.id);
          const total = siteCams.length;
          const online = siteCams.filter((c) => c.status === 'ONLINE').length;
          const offline = siteCams.filter((c) => c.status === 'OFFLINE').length;
          const status = total === 0 ? 'NO CAMERAS' : online === total ? 'ONLINE' : online > 0 ? 'DEGRADED' : 'OFFLINE';

          return (
            <div
              key={s.id}
              className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm hover:border-slate-700 transition-colors flex flex-col justify-between space-y-4"
            >
              <div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      <Compass className="w-4 h-4" />
                    </div>
                    <Link to={`/sites/${s.id}`} className="font-bold text-slate-100 hover:text-emerald-400 text-base">
                      {s.name}
                    </Link>
                  </div>
                  <StatusBadge status={status} size="sm" />
                </div>

                {s.location && (
                  <p className="text-xs text-slate-400 mt-3 flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5 text-slate-500" />
                    {s.location}
                  </p>
                )}

                {s.description && (
                  <p className="text-xs text-slate-500 mt-2 line-clamp-2 leading-relaxed">{s.description}</p>
                )}
              </div>

              <div className="pt-4 border-t border-slate-800/80 space-y-3">
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="p-2 bg-slate-950 rounded-lg border border-slate-800">
                    <p className="text-[10px] text-slate-500 uppercase">Total</p>
                    <p className="text-sm font-bold text-slate-200 mt-0.5">{total}</p>
                  </div>
                  <div className="p-2 bg-slate-950 rounded-lg border border-slate-800">
                    <p className="text-[10px] text-emerald-500 uppercase">Online</p>
                    <p className="text-sm font-bold text-emerald-400 mt-0.5">{online}</p>
                  </div>
                  <div className="p-2 bg-slate-950 rounded-lg border border-slate-800">
                    <p className="text-[10px] text-slate-500 uppercase">Offline</p>
                    <p className="text-sm font-bold text-slate-400 mt-0.5">{offline}</p>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs pt-1">
                  <Link to={`/sites/${s.id}`} className="text-emerald-400 hover:underline font-medium">
                    Manage Cameras &rarr;
                  </Link>
                  {hasPermission('site:delete') && (
                    <button
                      onClick={() => handleDelete(s)}
                      title="Delete site"
                      className="p-1 text-slate-500 hover:text-rose-400 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      )}

      {/* Add Site Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-base font-bold text-white">Add Monitored Site</h2>
              <button onClick={() => setIsModalOpen(false)} className="text-slate-400 hover:text-white">&times;</button>
            </div>

            {formError && (
              <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-xs text-rose-300">
                {formError}
              </div>
            )}

            <form onSubmit={handleCreateSite} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-400 uppercase font-semibold mb-1">Site Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Factory A, Campus West"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 uppercase font-semibold mb-1">Location</label>
                <input
                  type="text"
                  placeholder="e.g. Building 2, Seoul"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 uppercase font-semibold mb-1">Description</label>
                <textarea
                  rows={3}
                  placeholder="Description of physical facility..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="pt-3 flex justify-end gap-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold"
                >
                  {isSubmitting ? 'Creating...' : 'Create Site'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
