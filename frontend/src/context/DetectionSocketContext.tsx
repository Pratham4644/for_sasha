import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { DetectionEvent } from '../types';

interface DetectionSocketContextType {
  latestDetection: DetectionEvent | null;
  recentDetections: DetectionEvent[];
  isConnected: boolean;
  toasts: DetectionToast[];
  dismissToast: (id: string) => void;
}

export interface DetectionToast {
  id: string;
  cameraName: string;
  className: string;
  confidence: number;
  timestamp: string;
}

const DetectionSocketContext = createContext<DetectionSocketContextType | undefined>(undefined);

export const DetectionSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [latestDetection, setLatestDetection] = useState<DetectionEvent | null>(null);
  const [recentDetections, setRecentDetections] = useState<DetectionEvent[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [toasts, setToasts] = useState<DetectionToast[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef<boolean>(true);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    // Build WebSocket URL from current window location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/ws/detections`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'detection' && message.data) {
            const det: DetectionEvent = message.data;
            setLatestDetection(det);
            setRecentDetections((prev) => [det, ...prev.slice(0, 49)]);

            // Generate a transient toast
            const toastId = `${det.id || Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
            const newToast: DetectionToast = {
              id: toastId,
              cameraName: det.camera_name || det.camera_id || 'Camera',
              className: det.class_name || 'Object',
              confidence: det.confidence || 0,
              timestamp: new Date().toLocaleTimeString(),
            };

            setToasts((prev) => [newToast, ...prev.slice(0, 3)]);

            // Auto dismiss toast after 5s
            setTimeout(() => {
              if (mountedRef.current) {
                dismissToast(toastId);
              }
            }, 5000);
          }
        } catch {
          // ignore non-JSON messages
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        // Exponential/Fixed reconnect after 3 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, 3000);
      };

      ws.onerror = () => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      };
    } catch {
      setIsConnected(false);
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, 5000);
    }
  }, [dismissToast]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return (
    <DetectionSocketContext.Provider
      value={{
        latestDetection,
        recentDetections,
        isConnected,
        toasts,
        dismissToast,
      }}
    >
      {children}
      {/* Global floating live detection notification toasts */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className="pointer-events-auto bg-slate-900/95 border border-emerald-500/40 text-slate-100 rounded-xl p-3.5 shadow-2xl backdrop-blur-md flex items-start justify-between gap-3 animate-slide-in"
          >
            <div className="flex items-start gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping mt-1" />
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-xs text-white">{toast.cameraName}</span>
                  <span className="text-[10px] bg-emerald-500/20 text-emerald-300 font-mono px-1.5 py-0.5 rounded">
                    {(toast.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-xs text-slate-300 mt-0.5">
                  Detected <span className="font-medium text-emerald-400 capitalize">{toast.className}</span>
                </p>
                <span className="text-[10px] text-slate-500">{toast.timestamp}</span>
              </div>
            </div>
            <button
              onClick={() => dismissToast(toast.id)}
              className="text-slate-400 hover:text-white text-xs px-1"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </DetectionSocketContext.Provider>
  );
};

export const useDetectionSocket = () => {
  const context = useContext(DetectionSocketContext);
  if (!context) {
    throw new Error('useDetectionSocket must be used within a DetectionSocketProvider');
  }
  return context;
};
