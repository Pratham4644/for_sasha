import React, { createContext, useContext, useState, useEffect } from 'react';
import { Organization, User, UserRole } from '../types';
import { api } from '../services/api';

interface AuthContextType {
  user: User | null;
  organization: Organization | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string, organizationName: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  refreshOrganization: () => Promise<void>;
  hasRole: (minRole: UserRole) => boolean;
  hasPermission: (permission: string) => boolean;
}

const roleLevels: Record<UserRole, number> = {
  VIEWER: 1,
  OPERATOR: 2,
  ORG_ADMIN: 3,
  SUPER_ADMIN: 4,
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const fetchMe = async () => {
    try {
      const profile = await api.get<User>('/auth/me');
      setUser(profile);
      if (profile?.organization_id) {
        try {
          const org = await api.get<Organization>(`/organizations/${profile.organization_id}`);
          setOrganization(org);
        } catch {
          setOrganization(null);
        }
      }
    } catch {
      setUser(null);
      setOrganization(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchMe();
  }, []);

  const login = async (email: string, password: string) => {
    const userProfile = await api.post<User>('/auth/login', { email, password });
    setUser(userProfile);
    if (userProfile?.organization_id) {
      try {
        const org = await api.get<Organization>(`/organizations/${userProfile.organization_id}`);
        setOrganization(org);
      } catch {
        setOrganization(null);
      }
    }
  };

  const register = async (name: string, email: string, password: string, organizationName: string) => {
    const userProfile = await api.post<User>('/auth/register', {
      name,
      email,
      password,
      organization_name: organizationName,
    });
    setUser(userProfile);
    if (userProfile?.organization_id) {
      try {
        const org = await api.get<Organization>(`/organizations/${userProfile.organization_id}`);
        setOrganization(org);
      } catch {
        setOrganization(null);
      }
    }
  };

  const logout = async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      // ignore
    } finally {
      setUser(null);
      setOrganization(null);
    }
  };

  const refreshUser = async () => {
    try {
      const profile = await api.get<User>('/auth/me');
      setUser(profile);
    } catch {
      setUser(null);
    }
  };

  const refreshOrganization = async () => {
    if (user?.organization_id) {
      try {
        const org = await api.get<Organization>(`/organizations/${user.organization_id}`);
        setOrganization(org);
      } catch {
        // ignore
      }
    }
  };

  const hasRole = (minRole: UserRole): boolean => {
    if (!user) return false;
    return roleLevels[user.role] >= roleLevels[minRole];
  };

  const hasPermission = (permission: string): boolean => {
    if (!user) return false;
    if (user.role === 'SUPER_ADMIN') return true;
    if (user.role === 'ORG_ADMIN') {
      return !permission.startsWith('super:');
    }
    if (user.role === 'OPERATOR') {
      return [
        'camera:read', 'camera:update',
        'stream:read', 'stream:control',
        'site:read', 'org:read', 'user:read',
        'recording:read',
      ].includes(permission);
    }
    // VIEWER
    return ['camera:read', 'stream:read', 'site:read', 'org:read', 'recording:read'].includes(permission);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        organization,
        isLoading,
        login,
        register,
        logout,
        refreshUser,
        refreshOrganization,
        hasRole,
        hasPermission,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
