import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { DetectionSocketProvider } from './context/DetectionSocketContext';
import { AppLayout } from './layouts/AppLayout';
// Existing Batch 1 & 2 Pages
import { Login } from './pages/Login';
import { Register } from './pages/Register';
import { Dashboard } from './pages/Dashboard';
import { Cameras } from './pages/Cameras';
import { CameraDetail } from './pages/CameraDetail';
import { Sites } from './pages/Sites';
import { SiteDetail } from './pages/SiteDetail';
import { Streams } from './pages/Streams';
import { Logs } from './pages/Logs';
import { Users } from './pages/Users';
import { Health } from './pages/Health';
import { Settings } from './pages/Settings';
import { Profile } from './pages/Profile';


export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <DetectionSocketProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            <Route element={<AppLayout />}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/cameras" element={<Cameras />} />
              <Route path="/cameras/:id" element={<CameraDetail />} />
              <Route path="/sites" element={<Sites />} />
              <Route path="/sites/:id" element={<SiteDetail />} />
              <Route path="/streams" element={<Streams />} />
              <Route path="/streams/cameras/:id" element={<CameraDetail />} />
              <Route path="/logs" element={<Logs />} />
              <Route path="/users" element={<Users />} />
              <Route path="/health" element={<Health />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/profile" element={<Profile />} />
            </Route>

            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </DetectionSocketProvider>
      </AuthProvider>
    </BrowserRouter>
  );
};
