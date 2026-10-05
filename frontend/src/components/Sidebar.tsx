import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Activity,
  Building2,
  Camera,
  Compass,
  FileText,
  LayoutDashboard,
  Settings,
  Users,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export const Sidebar: React.FC = () => {
  const { user, organization } = useAuth();

  const navItems = [
    { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    { name: 'Cameras', path: '/cameras', icon: Camera },
    { name: 'Sites', path: '/sites', icon: Compass },
    { name: 'Logs', path: '/logs', icon: FileText },
    { name: 'Users', path: '/users', icon: Users, roleRequired: 'ORG_ADMIN' },
    { name: 'System Health', path: '/health', icon: Activity },
    { name: 'Settings', path: '/settings', icon: Settings },
  ];

  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col justify-between shrink-0 select-none">
      <div>
        {/* Brand Header */}
        <div className="h-16 flex items-center gap-3 px-6 border-b border-slate-800">
          <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
            <Camera className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold text-white tracking-tight">StreamOps</h1>
            <p className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Multi-Camera Core</p>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="p-4 space-y-1">
          {navItems.map((item) => {
            if (item.roleRequired && user?.role !== 'ORG_ADMIN' && user?.role !== 'SUPER_ADMIN') {
              return null;
            }
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-emerald-600/15 text-emerald-400 border border-emerald-500/30 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                  }`
                }
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Organization Badge at bottom */}
      <div className="p-4 border-t border-slate-800">
        <div className="px-3 py-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div className="flex items-center gap-1.5 text-slate-500">
            <Building2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
            <p className="text-[11px] font-medium uppercase tracking-wider">Tenant</p>
          </div>
          <p className="text-xs font-semibold text-slate-200 truncate mt-1">
            {organization?.name || user?.organization_id || 'My Organization'}
          </p>
          {user?.role === 'SUPER_ADMIN' && (
            <span className="mt-1 inline-block text-[9px] font-mono uppercase px-1.5 py-0.2 rounded bg-purple-950 text-purple-300 border border-purple-800/60">
              Platform Admin
            </span>
          )}
        </div>
      </div>
    </aside>
  );
};
