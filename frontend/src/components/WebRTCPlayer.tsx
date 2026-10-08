import React, { useCallback, useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import {
  Maximize2,
  Minimize2,
  RefreshCw,
  Volume2,
  VolumeX,
  WifiOff,
  Clock,
  Radio,
  Zap,
} from 'lucide-react';

// ─── Types ──────────────────────────────────────────────────────────────────

interface WebRTCPlayerProps {
  whepUrl: string;
  hlsUrl?: string;
  readerCredentials?: {
    username: string;
    password?: string;
  };
  cameraName?: string;
  autoPlay?: boolean;
}

type PlaybackState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'waiting'
  | 'failed'
  | 'disconnected';

type StreamProtocol = 'hls' | 'webrtc';

// ─── Constants ──────────────────────────────────────────────────────────────

const MAX_BACKOFF_MS = 10_000;
const INITIAL_BACKOFF_MS = 1_500;
const WEBRTC_FALLBACK_TIMEOUT_MS = 3_000;

// ─── Component ──────────────────────────────────────────────────────────────

export const WebRTCPlayer: React.FC<WebRTCPlayerProps> = ({
  whepUrl,
  hlsUrl,
  readerCredentials,
  cameraName = 'Camera Feed',
  autoPlay = true,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generationRef = useRef(0);
  const mountedRef = useRef(true);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);

  // WebRTC first; HLS is only used after a genuine WebRTC failure
  const [activeProtocol, setActiveProtocol] = useState<StreamProtocol>('webrtc');
  const webrtcConnectedRef = useRef(false);
  const [playbackState, setPlaybackState] = useState<PlaybackState>('idle');
  const playbackStateRef = useRef<PlaybackState>('idle');

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isMuted, setIsMuted] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [reconnectTrigger, setReconnectTrigger] = useState(0);

  // Resolve HLS URL if not explicitly provided
  const resolvedHlsUrl =
    hlsUrl ||
    (whepUrl
      ? whepUrl.replace(':8889', ':8888').replace('/whep', '/index.m3u8')
      : '');

  const updateState = useCallback((nextState: PlaybackState, msg: string | null = null) => {
    playbackStateRef.current = nextState;
    if (mountedRef.current) {
      setPlaybackState(nextState);
      setErrorMessage(msg);
    }
  }, []);

  // ── Clean up all active streams ──────────────────────────────────────────

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (fallbackTimerRef.current) {
      clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
  }, []);

  const closeStream = useCallback(() => {
    clearTimers();
    abortRef.current?.abort();
    abortRef.current = null;
    webrtcConnectedRef.current = false;

    // Clean up WebRTC
    const pc = pcRef.current;
    pcRef.current = null;
    if (pc) {
      pc.ontrack = null;
      pc.oniceconnectionstatechange = null;
      pc.onconnectionstatechange = null;
      pc.onicegatheringstatechange = null;
      try {
        pc.close();
      } catch {
        /* ignore */
      }
    }

    // Clean up HLS
    if (hlsRef.current) {
      try {
        hlsRef.current.destroy();
      } catch {
        /* ignore */
      }
      hlsRef.current = null;
    }

    // Clean up video element
    if (videoRef.current) {
      videoRef.current.srcObject = null;
      videoRef.current.removeAttribute('src');
      videoRef.current.load();
    }
  }, [clearTimers]);

  const requestHlsFallback = useCallback(
    (reason: string) => {
      if (!mountedRef.current || !resolvedHlsUrl) return;
      if (webrtcConnectedRef.current) {
        console.info('[WebRTC] Skipping HLS fallback — WebRTC is already connected.');
        return;
      }
      console.warn(`[WebRTC] ${reason} Falling back to HLS.`);
      closeStream();
      setActiveProtocol('hls');
    },
    [closeStream, resolvedHlsUrl],
  );

  // ── Reconnect scheduler ──────────────────────────────────────────────────

  const scheduleReconnect = useCallback(
    (targetState: PlaybackState, message: string) => {
      if (!mountedRef.current || !autoPlay) return;
      if (reconnectTimerRef.current) return;

      closeStream();
      updateState(targetState, message);

      const delay = backoffRef.current;
      backoffRef.current = Math.min(delay * 1.5, MAX_BACKOFF_MS);

      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        if (!mountedRef.current) return;
        setReconnectTrigger((n) => n + 1);
      }, delay);
    },
    [autoPlay, closeStream, updateState],
  );

  // ── HLS Playback Engine (Production Proven) ───────────────────────────────

  const startHls = useCallback(
    (targetHlsUrl: string) => {
      if (!targetHlsUrl || !videoRef.current) {
        updateState('failed', 'HLS streaming URL not configured.');
        return;
      }

      closeStream();
      updateState('connecting', null);

      const video = videoRef.current;
      video.muted = true;

      if (Hls.isSupported()) {
        const hls = new Hls({
          enableWorker: true,
          lowLatencyMode: true,
          backBufferLength: 4,
          maxBufferLength: 6,
          liveSyncDurationCount: 2,
          liveMaxLatencyDurationCount: 4,
          manifestLoadingTimeOut: 6000,
          manifestLoadingMaxRetry: 4,
          levelLoadingTimeOut: 6000,
        });
        hlsRef.current = hls;

        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          if (!mountedRef.current || !videoRef.current) return;
          backoffRef.current = INITIAL_BACKOFF_MS;
          updateState('connected', null);
          videoRef.current.play().catch(() => {
            if (videoRef.current) {
              videoRef.current.muted = true;
              videoRef.current.play().catch(() => {});
            }
          });
        });

        hls.on(Hls.Events.ERROR, (_, data) => {
          if (!mountedRef.current) return;
          if (data.fatal) {
            switch (data.type) {
              case Hls.ErrorTypes.NETWORK_ERROR:
                // Stream not publishing yet (404) or segment missing
                scheduleReconnect('waiting', 'Waiting for live frames from camera...');
                break;
              case Hls.ErrorTypes.MEDIA_ERROR:
                try {
                  hls.recoverMediaError();
                } catch {
                  scheduleReconnect('failed', 'HLS media error. Recovering...');
                }
                break;
              default:
                hls.destroy();
                scheduleReconnect('failed', 'HLS playback error encountered. Reconnecting...');
                break;
            }
          }
        });

        hls.loadSource(targetHlsUrl);
        hls.attachMedia(video);
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        // Native Safari HLS
        video.src = targetHlsUrl;
        video.addEventListener(
          'loadedmetadata',
          () => {
            if (!mountedRef.current || !videoRef.current) return;
            backoffRef.current = INITIAL_BACKOFF_MS;
            updateState('connected', null);
            videoRef.current.play().catch(() => {});
          },
          { once: true },
        );
      } else {
        updateState('failed', 'Browser does not support HLS.');
      }
    },
    [closeStream, scheduleReconnect, updateState],
  );

  // ── WebRTC WHEP Engine ───────────────────────────────────────────────────

  const startWebRtc = useCallback(
    async (targetWhepUrl: string, fallbackHls: string) => {
      if (!targetWhepUrl) {
        if (fallbackHls) {
          console.warn('[WebRTC] WHEP URL not configured. Using HLS fallback.');
          closeStream();
          setActiveProtocol('hls');
          return;
        }
        updateState('failed', 'WebRTC WHEP endpoint not configured.');
        return;
      }

      closeStream();
      webrtcConnectedRef.current = false;
      console.info('[WebRTC] Attempting WebRTC connection first:', targetWhepUrl);
      updateState('connecting', null);

      const generation = ++generationRef.current;
      const abort = new AbortController();
      abortRef.current = abort;

      const isCurrent = () =>
        mountedRef.current &&
        generation === generationRef.current &&
        !abort.signal.aborted;

      // Start fallback timer: if WebRTC doesn't connect in 3s, drop back to HLS
      if (fallbackHls) {
        fallbackTimerRef.current = setTimeout(() => {
          if (
            isCurrent() &&
            !webrtcConnectedRef.current &&
            playbackStateRef.current !== 'connected' &&
            !videoRef.current?.srcObject
          ) {
            requestHlsFallback('Connection timeout (3s).');
          }
        }, WEBRTC_FALLBACK_TIMEOUT_MS);
      }

      try {
        const pc = new RTCPeerConnection({
          iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
        });
        pcRef.current = pc;

        // Video-only transceiver
        pc.addTransceiver('video', { direction: 'recvonly' });

        pc.ontrack = (event) => {
          if (!isCurrent() || !videoRef.current || !event.streams[0]) return;
          videoRef.current.srcObject = event.streams[0];
          webrtcConnectedRef.current = true;
          backoffRef.current = INITIAL_BACKOFF_MS;
          updateState('connected', null);
          console.info('[WebRTC] Connected successfully. HLS will not be initialized.');

          if (fallbackTimerRef.current) {
            clearTimeout(fallbackTimerRef.current);
            fallbackTimerRef.current = null;
          }

          videoRef.current.play().catch(() => {
            if (videoRef.current) {
              videoRef.current.muted = true;
              videoRef.current.play().catch(() => {});
            }
          });
        };

        pc.oniceconnectionstatechange = () => {
          if (!isCurrent()) return;
          const state = pc.iceConnectionState;
          if (state === 'connected' || state === 'completed') {
            webrtcConnectedRef.current = true;
            backoffRef.current = INITIAL_BACKOFF_MS;
            updateState('connected', null);
            if (fallbackTimerRef.current) {
              clearTimeout(fallbackTimerRef.current);
              fallbackTimerRef.current = null;
            }
          } else if (state === 'failed') {
            if (fallbackHls) {
              requestHlsFallback('ICE connection failed.');
            } else {
              scheduleReconnect('failed', 'WebRTC ICE connection failed.');
            }
          }
        };

        const offer = await pc.createOffer();
        if (!isCurrent()) return;
        await pc.setLocalDescription(offer);

        // Wait brief interval for initial ICE candidate gathering
        await new Promise<void>((resolve) => {
          if (pc.iceGatheringState === 'complete') {
            resolve();
            return;
          }
          let resolved = false;
          const finish = () => {
            if (resolved) return;
            resolved = true;
            pc.removeEventListener('icegatheringstatechange', check);
            clearTimeout(timeout);
            resolve();
          };
          const check = () => {
            if (pc.iceGatheringState === 'complete') finish();
          };
          const timeout = setTimeout(finish, 1000);
          pc.addEventListener('icegatheringstatechange', check);
        });

        if (!isCurrent()) return;

        const headers: Record<string, string> = {
          'Content-Type': 'application/sdp',
        };
        if (readerCredentials?.username) {
          const creds = btoa(`${readerCredentials.username}:${readerCredentials.password || ''}`);
          headers.Authorization = `Basic ${creds}`;
        }

        const resp = await fetch(targetWhepUrl, {
          method: 'POST',
          headers,
          body: pc.localDescription?.sdp,
          signal: abort.signal,
        });

        if (!resp.ok) {
          if (resp.status === 404) {
            scheduleReconnect('waiting', 'Stream publisher not ready yet.');
            return;
          }
          throw new Error(`WHEP negotiation returned HTTP ${resp.status}`);
        }

        const answerSdp = await resp.text();
        if (!isCurrent()) return;

        await pc.setRemoteDescription(
          new RTCSessionDescription({ type: 'answer', sdp: answerSdp }),
        );
      } catch (err: unknown) {
        if (abort.signal.aborted || !isCurrent()) return;
        const msg = err instanceof Error ? err.message : 'WebRTC connection failed';
        console.error('[WebRTC] Failed to establish connection:', msg);

        if (fallbackHls) {
          requestHlsFallback(`Initialization failed (${msg}).`);
        } else {
          scheduleReconnect('failed', msg);
        }
      }
    },
    [closeStream, readerCredentials, requestHlsFallback, scheduleReconnect, updateState],
  );

  // ── Protocol Switch & Reconnect Handlers ──────────────────────────────────

  const handleProtocolToggle = () => {
    clearTimers();
    backoffRef.current = INITIAL_BACKOFF_MS;
    const nextProtocol: StreamProtocol = activeProtocol === 'hls' ? 'webrtc' : 'hls';
    setActiveProtocol(nextProtocol);

    if (nextProtocol === 'hls') {
      startHls(resolvedHlsUrl);
    } else {
      void startWebRtc(whepUrl, resolvedHlsUrl);
    }
  };

  const handleRetry = () => {
    clearTimers();
    backoffRef.current = INITIAL_BACKOFF_MS;
    if (activeProtocol === 'hls') {
      startHls(resolvedHlsUrl);
    } else {
      void startWebRtc(whepUrl, resolvedHlsUrl);
    }
  };

  // ── Main Ingestion Trigger ────────────────────────────────────────────────

  useEffect(() => {
    mountedRef.current = true;
    backoffRef.current = INITIAL_BACKOFF_MS;
    webrtcConnectedRef.current = false;

    if (autoPlay) {
      if (activeProtocol === 'hls') {
        startHls(resolvedHlsUrl);
      } else {
        void startWebRtc(whepUrl, resolvedHlsUrl);
      }
    }

    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      webrtcConnectedRef.current = false;
      clearTimers();
      closeStream();
    };
  }, [autoPlay, activeProtocol, resolvedHlsUrl, whepUrl, reconnectTrigger]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Audio & Fullscreen ────────────────────────────────────────────────────

  const toggleMute = () => {
    if (!videoRef.current) return;
    const next = !videoRef.current.muted;
    videoRef.current.muted = next;
    setIsMuted(next);
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current
        .requestFullscreen()
        .then(() => setIsFullscreen(true))
        .catch(() => {});
    } else {
      document
        .exitFullscreen()
        .then(() => setIsFullscreen(false))
        .catch(() => {});
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      ref={containerRef}
      className="relative w-full aspect-video bg-black rounded-lg overflow-hidden border border-slate-800 shadow-xl flex items-center justify-center group select-none"
    >
      {/* Video Element */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted={isMuted}
        onPlaying={() => updateState('connected', null)}
        onLoadedData={() => updateState('connected', null)}
        className="w-full h-full object-contain bg-black"
      />

      {/* Header Overlay */}
      <div className="absolute top-0 inset-x-0 p-2.5 bg-gradient-to-b from-black/80 via-black/40 to-transparent flex items-center justify-between z-10 opacity-90 group-hover:opacity-100 transition-opacity">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-xs text-white tracking-wide truncate max-w-[150px]">
            {cameraName}
          </span>
          {/* Protocol Switcher */}
          <button
            onClick={handleProtocolToggle}
            title={`Active: ${activeProtocol.toUpperCase()} (Click to switch to ${activeProtocol === 'hls' ? 'WebRTC' : 'HLS'})`}
            className={`inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded border transition-colors ${
              activeProtocol === 'webrtc'
                ? 'bg-amber-950/80 text-amber-300 border-amber-800/80 hover:bg-amber-900/60'
                : 'bg-emerald-950/80 text-emerald-300 border-emerald-800/80 hover:bg-emerald-900/60'
            }`}
          >
            {activeProtocol === 'webrtc' ? (
              <>
                <Zap className="w-2.5 h-2.5" /> WebRTC
              </>
            ) : (
              <>
                <Radio className="w-2.5 h-2.5" /> HLS
              </>
            )}
          </button>
        </div>

        {/* Status Pill */}
        <div className="flex items-center gap-2">
          {playbackState === 'connected' ? (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-950/90 text-emerald-400 border border-emerald-800 shadow-sm">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              LIVE
            </span>
          ) : playbackState === 'connecting' ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-950/90 text-amber-300 border border-amber-800">
              <RefreshCw className="w-2.5 h-2.5 animate-spin" />
              CONNECTING
            </span>
          ) : playbackState === 'waiting' ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-sky-950/90 text-sky-300 border border-sky-800">
              <Clock className="w-2.5 h-2.5" />
              WAITING
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-rose-950/90 text-rose-300 border border-rose-800">
              <WifiOff className="w-2.5 h-2.5" />
              OFFLINE
            </span>
          )}
        </div>
      </div>

      {/* State Overlays */}
      {playbackState === 'connecting' && (
        <div className="absolute inset-0 bg-black/80 flex flex-col items-center justify-center text-center p-4 gap-2 z-20 pointer-events-none">
          <RefreshCw className="w-7 h-7 text-emerald-400 animate-spin" />
          <p className="text-xs font-medium text-slate-300">
            {activeProtocol === 'webrtc'
              ? 'Connecting via WebRTC...'
              : `Buffering ${activeProtocol.toUpperCase()} live stream...`}
          </p>
        </div>
      )}

      {playbackState === 'waiting' && (
        <div className="absolute inset-0 bg-black/85 flex flex-col items-center justify-center text-center p-4 gap-2.5 z-20">
          <Clock className="w-7 h-7 text-sky-400 animate-pulse" />
          <p className="text-xs font-semibold text-slate-200">Waiting for Stream</p>
          <p className="text-[11px] text-slate-400 max-w-xs leading-relaxed">
            MediaMTX is waiting for the camera RTSP ingestion to send video frames.
          </p>
          <button
            onClick={handleRetry}
            className="mt-1 px-3 py-1 rounded bg-sky-600 hover:bg-sky-500 text-white text-[11px] font-medium transition-colors"
          >
            Retry Connection
          </button>
        </div>
      )}

      {playbackState === 'failed' && (
        <div className="absolute inset-0 bg-black/90 flex flex-col items-center justify-center text-center p-4 gap-2 z-20">
          <WifiOff className="w-7 h-7 text-rose-400" />
          <p className="text-xs font-semibold text-slate-200">Stream Connection Failed</p>
          <p className="text-[11px] text-rose-400/90 max-w-xs">{errorMessage || 'Unable to connect to stream'}</p>
          <div className="flex items-center gap-2 mt-1">
            <button
              onClick={handleRetry}
              className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] font-medium transition-colors"
            >
              Retry
            </button>
            <button
              onClick={handleProtocolToggle}
              className="px-3 py-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-[11px] font-medium transition-colors"
            >
              Switch to {activeProtocol === 'hls' ? 'WebRTC' : 'HLS'}
            </button>
          </div>
        </div>
      )}

      {/* Floating Controls at Bottom Right */}
      <div className="absolute bottom-2 right-2 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity z-10">
        <button
          onClick={toggleMute}
          title={isMuted ? 'Unmute' : 'Mute'}
          className="p-1.5 rounded-md bg-black/70 hover:bg-black/90 text-white transition-colors border border-white/10"
        >
          {isMuted ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
        </button>
        <button
          onClick={toggleFullscreen}
          title="Fullscreen"
          className="p-1.5 rounded-md bg-black/70 hover:bg-black/90 text-white transition-colors border border-white/10"
        >
          {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
};
