import React, { useEffect, useState } from 'react';
import { Plus, Power, RefreshCw, Trash2, UserPlus, Users as UsersIcon } from 'lucide-react';
import { User, UserRole } from '../types';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';

export const Users: React.FC = () => {
  const { user: currentUser, hasPermission } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Modal
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>('VIEWER');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadUsers = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.get<User[]>('/users');
      setUsers(data || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load users');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setIsSubmitting(true);
    try {
      await api.post('/users', {
        name: name.trim(),
        email: email.trim(),
        password,
        role,
      });
      setIsModalOpen(false);
      setName('');
      setEmail('');
      setPassword('');
      setRole('VIEWER');
      loadUsers();
    } catch (err: any) {
      setFormError(err.message || 'Failed to create user');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleToggleStatus = async (targetUser: User) => {
    try {
      await api.patch(`/users/${targetUser.id}`, {
        is_active: !targetUser.is_active,
      });
      loadUsers();
    } catch (err: any) {
      alert(`Operation failed: ${err.message}`);
    }
  };

  const handleChangeRole = async (targetUser: User, newRole: UserRole) => {
    try {
      await api.patch(`/users/${targetUser.id}`, { role: newRole });
      loadUsers();
    } catch (err: any) {
      alert(`Role change failed: ${err.message}`);
    }
  };

  const handleDeleteUser = async (targetUser: User) => {
    if (!window.confirm(`Are you sure you want to permanently remove user "${targetUser.name}" (${targetUser.email})?`)) {
      return;
    }
    try {
      await api.delete(`/users/${targetUser.id}`);
      loadUsers();
    } catch (err: any) {
      alert(`Delete user failed: ${err.message}`);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Access Control & Users</h1>
          <p className="text-sm text-slate-400 mt-1">Manage RBAC roles, operator credentials, and account statuses</p>
        </div>
        {hasPermission('user:create') && (
          <button
            onClick={() => setIsModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors shadow-lg shadow-emerald-950/40"
          >
            <Plus className="w-4 h-4" />
            Add User
          </button>
        )}
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 text-xs">
          {error}
        </div>
      )}

      {/* Users Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 border-b border-slate-800 text-slate-400 uppercase font-mono tracking-wider">
              <tr>
                <th className="py-3.5 px-4">User</th>
                <th className="py-3.5 px-4">Role</th>
                <th className="py-3.5 px-4">Status</th>
                <th className="py-3.5 px-4">Created</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-3.5 px-4">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400">
                        <UsersIcon className="w-4 h-4" />
                      </div>
                      <div>
                        <p className="font-semibold text-slate-100">{u.name}</p>
                        <p className="text-[11px] text-slate-500 font-mono mt-0.5">{u.email}</p>
                      </div>
                    </div>
                  </td>

                  <td className="py-3.5 px-4">
                    {hasPermission('user:update') && u.id !== currentUser?.id ? (
                      <select
                        value={u.role}
                        onChange={(e) => handleChangeRole(u, e.target.value as UserRole)}
                        className="px-2.5 py-1 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-emerald-400 focus:outline-none focus:border-emerald-500"
                      >
                        <option value="VIEWER">VIEWER</option>
                        <option value="OPERATOR">OPERATOR</option>
                        <option value="ORG_ADMIN">ORG_ADMIN</option>
                        {currentUser?.role === 'SUPER_ADMIN' && (
                          <option value="SUPER_ADMIN">SUPER_ADMIN</option>
                        )}
                      </select>
                    ) : (
                      <span className="font-mono text-xs text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5 rounded">
                        {u.role}
                      </span>
                    )}
                  </td>

                  <td className="py-3.5 px-4">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium border ${
                        u.is_active
                          ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/60'
                          : 'bg-rose-950/60 text-rose-400 border-rose-800/60'
                      }`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          u.is_active ? 'bg-emerald-400' : 'bg-rose-400'
                        }`}
                      />
                      {u.is_active ? 'ACTIVE' : 'DISABLED'}
                    </span>
                  </td>

                  <td className="py-3.5 px-4 font-mono text-slate-400 text-[11px]">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>

                  <td className="py-3.5 px-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {hasPermission('user:update') && u.id !== currentUser?.id && (
                        <button
                          onClick={() => handleToggleStatus(u)}
                          title={u.is_active ? 'Disable Account' : 'Enable Account'}
                          className={`p-1.5 rounded-lg border transition-colors ${
                            u.is_active
                              ? 'bg-slate-800 hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 border-slate-700 hover:border-rose-800'
                              : 'bg-slate-800 hover:bg-emerald-950/40 text-slate-400 hover:text-emerald-400 border-slate-700 hover:border-emerald-800'
                          }`}
                        >
                          <Power className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {hasPermission('user:delete') && u.id !== currentUser?.id && (
                        <button
                          onClick={() => handleDeleteUser(u)}
                          title="Remove User"
                          className="p-1.5 rounded-lg bg-slate-800 hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 border border-slate-700 hover:border-rose-800 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {users.length === 1 && users[0].id === currentUser?.id && (
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <UserPlus className="w-4 h-4 text-emerald-400" />
            <span>No additional members yet in your organization. Invite operators or viewers to collaborate.</span>
          </div>
          {hasPermission('user:create') && (
            <button
              onClick={() => setIsModalOpen(true)}
              className="text-emerald-400 hover:text-emerald-300 font-medium hover:underline"
            >
              Add User &rarr;
            </button>
          )}
        </div>
      )}

      {/* Add User Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-base font-bold text-white">Create Platform User</h2>
              <button onClick={() => setIsModalOpen(false)} className="text-slate-400 hover:text-white">&times;</button>
            </div>

            {formError && (
              <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-xs text-rose-300">
                {formError}
              </div>
            )}

            <form onSubmit={handleCreateUser} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-400 uppercase font-semibold mb-1">Full Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. John Doe"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 uppercase font-semibold mb-1">Email Address</label>
                <input
                  type="email"
                  required
                  placeholder="operator@camera-platform.local"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 uppercase font-semibold mb-1">Initial Password</label>
                <input
                  type="password"
                  required
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 uppercase font-semibold mb-1">Assigned Role</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as UserRole)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                >
                  <option value="VIEWER">VIEWER (View Only)</option>
                  <option value="OPERATOR">OPERATOR (Streams & Controls)</option>
                  <option value="ORG_ADMIN">ORG_ADMIN (Full Camera & Site CRUD)</option>
                  {currentUser?.role === 'SUPER_ADMIN' && (
                    <option value="SUPER_ADMIN">SUPER_ADMIN (Tenant & Global)</option>
                  )}
                </select>
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
                  {isSubmitting ? 'Creating...' : 'Create User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
