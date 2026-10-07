// ============================================================================
// Core Domain Types & Interfaces
// Reconstructed for Camera Platform Frontend & Backend Schemas
// ============================================================================

// --- Enums & Literals ---

export type UserRole = 'SUPER_ADMIN' | 'ORG_ADMIN' | 'OPERATOR' | 'VIEWER';

export type CameraStatus =
  | 'ONLINE'
  | 'OFFLINE'
  | 'CONNECTING'
  | 'DEGRADED'
  | 'STOPPING'
  | 'ERROR'
  | 'UNKNOWN';

// --- API Generic Wrapper ---

export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: {
    code?: string;
    message?: string;
    details?: any;
  } | null;
  message?: string | null;
  request_id?: string | null;
}

// --- Auth & User Types ---

export interface User {
  id: string;
  organization_id: string;
  email: string;
  name: string;
  role: UserRole;
  is_active?: boolean;
  created_at: string;
  updated_at?: string;
  token?: string;
  user_id?: string;
}

export interface LoginResponse {
  user_id: string;
  email: string;
  name: string;
  role: UserRole | string;
  organization_id: string;
  token?: string;
}

// --- Organization Types ---

export interface Organization {
  id: string;
  name: string;
  description?: string | null;
  created_at?: string;
  updated_at?: string;
}

// --- Site Types ---

export interface Site {
  id: string;
  organization_id?: string;
  name: string;
  location?: string | null;
  description?: string | null;
  created_at?: string;
  updated_at?: string;
}

// --- Camera Types ---

export interface Camera {
  id: string;
  camera_id?: string;
  organization_id?: string;
  site_id: string;
  name: string;
  description?: string | null;
  source_protocol: string;
  stream_url?: string;
  source_url?: string;
  media_path: string;
  configured_resolution?: string;
  configured_fps?: number;
  enabled: boolean;
  ai_enabled: boolean;
  ai_model?: string;
  ai_endpoint?: string | null;
  status: CameraStatus | string;
  has_credentials?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CameraDetail extends Camera {
  whep_url?: string;
}

export interface CameraPlayback {
  camera_id: string;
  name?: string;
  media_path?: string;
  whep_url: string;
  whep_ai_url?: string | null;
  hls_url: string;
  hls_ai_url?: string | null;
  rtsp_url?: string;
  rtsp_ai_url?: string | null;
  reader_credentials?: {
    username: string;
    password?: string;
  } | null;
  control_state?: string;
  media_state?: string;
  ingest_state?: string;
}

export interface CameraStream {
  camera_id: string;
  status: string;
  online: boolean;
  streams: Record<string, string>;
}

// --- Detection & AI Types ---

export interface DetectionItem {
  class_id?: number;
  class_name: string;
  confidence: number;
  bbox?: number[];
}

export interface DetectionEvent {
  id: string;
  camera_id: string;
  camera_name?: string | null;
  site_id?: string | null;
  timestamp: string;
  class_name: string;
  confidence: number;
  bounding_box?: number[] | null;
  detections?: DetectionItem[];
  model_name?: string;
  inference_latency_ms?: number;
  created_at?: string;
}

export type DetectionLog = DetectionEvent;

export interface DetectionLogsResponse {
  items: DetectionLog[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// --- Audit Log Types ---

export interface AuditLogEntry {
  id: string;
  organization_id?: string | null;
  user_id?: string | null;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  timestamp: string;
  request_id?: string | null;
  details?: Record<string, any>;
}

export interface AuditLogsResponse {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// --- Analytics Types ---

export interface DetectionTrendPoint {
  period: string;
  count: number;
}

export interface DetectionTrendsResponse {
  granularity: string;
  points: DetectionTrendPoint[];
}

export interface DetectionClassItem {
  class_name: string;
  count: number;
  percentage: number;
}

export interface CameraAnalyticsItem {
  camera_id: string;
  camera_name: string;
  status: string;
  detection_count: number;
  last_activity?: string | null;
}

export interface DurationStatistics {
  average_duration?: number | null;
  total_duration?: number | null;
  max_duration?: number | null;
  total_events_with_duration?: number;
}

export interface AnalyticsOverview {
  total_detections: number;
  active_cameras: number;
  offline_cameras: number;
  detection_classes_count: number;
}

export interface FullAnalytics {
  overview: AnalyticsOverview;
  trends: DetectionTrendsResponse;
  classes: DetectionClassItem[];
  cameras: CameraAnalyticsItem[];
  duration?: DurationStatistics;
}

// --- Health Types ---

export interface DetailedHealth {
  status: string;
  service?: string;
  environment?: string;
  database?: boolean;
  database_status?: string;
  mediamtx?: string;
  mediamtx_ok?: boolean;
  timestamp?: string;
  backend?: {
    status: string;
    ok: boolean;
    version?: string;
  };
  cameras?: {
    status: string;
    ok: boolean;
    total: number;
    online: number;
  };
  ai?: {
    status: string;
    ok: boolean;
    enabled?: boolean;
    active_pipelines: number;
    model?: string;
    total_inferences?: number;
    successful_inferences?: number;
    last_latency_ms?: number;
  };
}
