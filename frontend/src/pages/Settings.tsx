import React, { useEffect, useState } from 'react';
import {
  Building2,
  CheckCircle,
  Database,
  Lock,
  RefreshCw,
  Save,
  Server,
  Shield,
  Video,
} from 'lucide-react';
import { Organization } from '../types';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';

export const Settings: React.FC = () => {
  const { user, hasPermission } = useAuth();
  const [org, setOrg] = useState<Organization | null>(null);
  const [orgName, setOrgName] = useState('');
  const [orgDesc, setOrgDesc] = useState('');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadSettings = async () => {
    if (!user?.organization_id) return;
    setIsLoading(true);
    try {
      const data = await api.get<Organization>(`/organizations/${user.organization_id}`);
      setOrg(data);
      if (data) {
        setOrgName(data.name);
        setOrgDesc(data.description || '');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load organization settings');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, [user?.organization_id]);

  const handleSaveOrg = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user?.organization_id) return;
    setIsSaving(true);
    setSuccessMsg(null);
    setErrorMsg(null);

    try {
      await api.patch(`/organizations/${user.organization_id}`, {
        name: orgName.trim(),
        description: orgDesc.trim() || undefined,
      });
      setSuccessMsg('Organization profile updated successfully.');
      loadSettings();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to update organization');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-8 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">System &amp; Platform Settings</h1>
        <p className="text-sm text-slate-400 mt-1">
          Configure organization metadata, review streaming parameters, and inspect security posture
        </p>
      </div>

      {successMsg && (
        <div className="p-4 rounded-xl bg-emerald-950/60 border border-emerald-800 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle className="w-4 h-4 shrink-0 text-emerald-400" />
          <span>{successMsg}</span>
        </div>
      )}

      {errorMsg && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 text-xs">
          {errorMsg}
        </div>
      )}

      {/* Organization Settings */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-5">
        <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
          <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <Building2 className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">Organization Profile</h2>
            <p className="text-xs text-slate-400">Manage tenant identity and primary organizational boundaries</p>
          </div>
        </div>

        {isLoading ? (
          <div className="py-6 text-center text-slate-500 text-xs flex items-center justify-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
            Loading organization data...
          </div>
        ) : (
          <form onSubmit={handleSaveOrg} className="space-y-4 text-xs">
            <div>
              <label className="block text-slate-400 uppercase font-semibold mb-1">Organization ID</label>
              <input
                type="text"
                disabled
                value={org?.id || user?.organization_id || ''}
                className="w-full px-3 py-2 bg-slate-950/60 border border-slate-800 rounded-lg text-slate-500 font-mono text-xs cursor-not-allowed"
              />
            </div>

            <div>
              <label className="block text-slate-400 uppercase font-semibold mb-1">Organization Name</label>
              <input
                type="text"
                required
                disabled={!hasPermission('org:update')}
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500 disabled:opacity-60"
              />
            </div>

            <div>
              <label className="block text-slate-400 uppercase font-semibold mb-1">Description</label>
              <textarea
                rows={3}
                disabled={!hasPermission('org:update')}
                value={orgDesc}
                onChange={(e) => setOrgDesc(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500 disabled:opacity-60"
                placeholder="Operational scope or division details..."
              />
            </div>

            {hasPermission('org:update') && (
              <div className="pt-2 flex justify-end">
                <button
                  type="submit"
                  disabled={isSaving}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors shadow-md shadow-emerald-950/40"
                >
                  <Save className="w-3.5 h-3.5" />
                  {isSaving ? 'Saving...' : 'Save Organization Profile'}
                </button>
              </div>
            )}
          </form>
        )}
      </div>

      {/* Streaming Infrastructure Overview */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-5">
        <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
          <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <Video className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">Streaming Plane Configuration</h2>
            <p className="text-xs text-slate-400">MediaMTX and Edge Ingest architectural parameters</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
          <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
            <span className="text-slate-500 text-[10px] uppercase font-sans font-bold">Media Server</span>
            <p className="text-slate-200">MediaMTX v1.11+ (WebRTC / RTSP)</p>
          </div>
          <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
            <span className="text-slate-500 text-[10px] uppercase font-sans font-bold">Playback Protocol</span>
            <p className="text-slate-200">WHEP (WebRTC HTTP Egress Protocol)</p>
          </div>
          <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
            <span className="text-slate-500 text-[10px] uppercase font-sans font-bold">Default Resolution</span>
            <p className="text-slate-200">1920×1080 @ 15fps (H.264 / AAC)</p>
          </div>
          <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
            <span className="text-slate-500 text-[10px] uppercase font-sans font-bold">Gateway Supervision</span>
            <p className="text-slate-200">Edge Ingest Subprocess Watchdog</p>
          </div>
        </div>
      </div>

      {/* Security & Isolation Overview */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-5">
        <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
          <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">Security &amp; Data Protection</h2>
            <p className="text-xs text-slate-400">Cryptographic controls, session security, and isolation</p>
          </div>
        </div>

        <div className="space-y-3 text-xs">
          <div className="flex items-center justify-between p-3 bg-slate-950 rounded-xl border border-slate-800">
            <div className="flex items-center gap-2.5">
              <Lock className="w-4 h-4 text-emerald-400" />
              <div>
                <p className="font-semibold text-slate-200">Camera Credential Encryption</p>
                <p className="text-[11px] text-slate-500">Fernet symmetric envelope encryption before database persistence</p>
              </div>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950/80 text-emerald-400 border border-emerald-800">
              Active
            </span>
          </div>

          <div className="flex items-center justify-between p-3 bg-slate-950 rounded-xl border border-slate-800">
            <div className="flex items-center gap-2.5">
              <Server className="w-4 h-4 text-emerald-400" />
              <div>
                <p className="font-semibold text-slate-200">Session Cookie Security</p>
                <p className="text-[11px] text-slate-500">HttpOnly, SameSite=Lax, Secure flags prevent XSS access</p>
              </div>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950/80 text-emerald-400 border border-emerald-800">
              Enforced
            </span>
          </div>

          <div className="flex items-center justify-between p-3 bg-slate-950 rounded-xl border border-slate-800">
            <div className="flex items-center gap-2.5">
              <Database className="w-4 h-4 text-emerald-400" />
              <div>
                <p className="font-semibold text-slate-200">Tenant Scoping</p>
                <p className="text-[11px] text-slate-500">Mandatory server-side query scoping on every resource</p>
              </div>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950/80 text-emerald-400 border border-emerald-800">
              Isolated
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
