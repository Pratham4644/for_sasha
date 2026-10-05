import React from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut, Shield, User as UserIcon } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export const Navbar: React.FC = () => {
  const { user, organization, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <header className="h-16 bg-slate-900/60 backdrop-blur-md border-b border-slate-800 px-8 flex items-center justify-between shrink-0">
      <div className="flex items-center gap-3">
        {organization ? (
          <span className="text-xs font-medium text-emerald-400 bg-emerald-950/60 px-3 py-1 rounded-lg border border-emerald-800/60 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="font-semibold text-slate-200">{organization.name}</span>
          </span>
        ) : (
          <span className="text-xs font-mono text-slate-400 bg-slate-800/80 px-2.5 py-1 rounded-md border border-slate-700/60">
            StreamOps Platform
          </span>
        )}
      </div>

      <div className="flex items-center gap-4">
        {user && (
          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="text-xs font-semibold text-slate-200">{user.name}</p>
              <div className="flex items-center justify-end gap-1.5 mt-0.5">
                <span className="text-[10px] font-mono uppercase px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/60">
                  {user.role}
                </span>
              </div>
            </div>

            <button
              onClick={() => navigate('/profile')}
              title="Profile"
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors border border-slate-700"
            >
              <UserIcon className="w-4 h-4" />
            </button>

            <button
              onClick={handleLogout}
              title="Sign Out"
              className="p-2 rounded-lg bg-slate-800 hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 hover:border-rose-800 transition-colors border border-slate-700"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
