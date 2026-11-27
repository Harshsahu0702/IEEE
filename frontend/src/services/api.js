const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiClient {
  constructor() {
    this.token = sessionStorage.getItem('omnisense_token') || null;
    this.user = JSON.parse(sessionStorage.getItem('omnisense_user') || 'null');
  }

  setToken(token, user = null) {
    this.token = token;
    if (token) {
      sessionStorage.setItem('omnisense_token', token);
    } else {
      sessionStorage.removeItem('omnisense_token');
    }
    if (user) {
      this.user = user;
      sessionStorage.setItem('omnisense_user', JSON.stringify(user));
    }
  }

  clearToken() {
    this.token = null;
    this.user = null;
    sessionStorage.removeItem('omnisense_token');
    sessionStorage.removeItem('omnisense_user');
  }

  async request(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(url, { ...options, headers });

      if (response.status === 401) {
        this.clearToken();
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        throw new Error('Session expired or unauthorized');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Request failed with status ${response.status}`);
      }

      return await response.json();
    } catch (err) {
      console.error(`API Error on [${options.method || 'GET'}] ${endpoint}:`, err);
      throw err;
    }
  }

  // Auth Endpoints
  auth = {
    login: (username, password) => this.request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    }),
    register: (data) => this.request('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
    getProfile: () => this.request('/api/auth/me'),
    changePassword: (old_password, new_password) => this.request('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ old_password, new_password })
    }),
  };


  // Overview Endpoints
  overview = {
    getStats: () => this.request('/api/overview/stats'),
  };

  // Agent Endpoints
  agent = {
    sendCommand: (command) => this.request('/api/agent/command', {
      method: 'POST',
      body: JSON.stringify({ command })
    }),
    listPlans: () => this.request('/api/agent/plans'),
    approvePlan: (planId, approved = true, comment = '') => this.request(`/api/agent/plans/${planId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved, comment })
    }),
    getAuditLogs: (limit = 50) => this.request(`/api/agent/audit-logs?limit=${limit}`),
  };

  // Tasks Endpoints
  tasks = {
    list: () => this.request('/api/tasks'),
    start: (taskId) => this.request(`/api/tasks/${taskId}/start`, { method: 'POST' }),
    stop: (taskId) => this.request(`/api/tasks/${taskId}/stop`, { method: 'POST' }),
  };

  // Devices Endpoints
  devices = {
    list: () => this.request('/api/devices'),
    getHealth: (deviceId) => this.request(`/api/devices/${deviceId}/health`),
    getTelemetry: (deviceId, limit = 50) => this.request(`/api/devices/${deviceId}/telemetry?limit=${limit}`),
    approve: (deviceId) => this.request(`/api/devices/${deviceId}/approve`, { method: 'POST' }),
    getAlarm: () => this.request('/api/devices/alarm'),
    setAlarm: (alarm_active, threat_type = 'manual', description = '') => this.request('/api/devices/alarm', {
      method: 'POST',
      body: JSON.stringify({ alarm_active, threat_type, description })
    }),
    resetAlarm: () => this.request('/api/devices/alarm', {
      method: 'POST',
      body: JSON.stringify({ alarm_active: false, threat_type: 'none', description: 'Cleared by operator' })
    }),
    discoverHardware: () => this.request('/api/devices/hardware/discover'),
    selectHardware: (vision_source, enabled_sensors) => this.request('/api/devices/hardware/select', {
      method: 'POST',
      body: JSON.stringify({ vision_source, enabled_sensors })
    }),
  };

  // Events Endpoints
  events = {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return this.request(`/api/events${q ? `?${q}` : ''}`);
    },
    get: (eventId) => this.request(`/api/events/${eventId}`),
    review: (eventId, payload, reviewer_notes = '') => {
      const body = typeof payload === 'object' ? payload : { status: payload, reviewer_notes };
      return this.request(`/api/events/${eventId}/review`, {
        method: 'PATCH',
        body: JSON.stringify(body)
      });
    },
  };

  // Reports Endpoints
  reports = {
    generate: (data) => this.request('/api/reports/generate', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
    list: () => this.request('/api/reports'),
    downloadUrl: (id) => `${API_BASE}/api/reports/${id}/download`,
    delete: (id) => this.request(`/api/reports/${id}`, { method: 'DELETE' }),
  };

  // Monitoring Profiles Endpoints
  profiles = {
    list: () => this.request('/api/profiles'),
    create: (data) => this.request('/api/profiles', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
    activate: (id) => this.request(`/api/profiles/${id}/activate`, {
      method: 'POST'
    }),
    delete: (id) => this.request(`/api/profiles/${id}`, { method: 'DELETE' }),
  };

  // Video Stream & Camera Source Switcher
  video = {
    getSource: () => this.request('/api/video/source'),
    setSource: (source) => this.request('/api/video/source', {
      method: 'POST',
      body: JSON.stringify({ source: String(source) })
    }),
    switchCamera: (source) => this.request('/api/video/source', {
      method: 'POST',
      body: JSON.stringify({ source: String(source) })
    }),
    setRotation: (rotation) => this.request('/api/video/rotation', {
      method: 'POST',
      body: JSON.stringify({ rotation: Number(rotation) })
    }),
    rotateCamera: (rotation) => this.request('/api/video/rotation', {
      method: 'POST',
      body: JSON.stringify({ rotation: Number(rotation) })
    }),
  };

  // Video Stream URL helper


  getVideoStreamUrl() {
    return `${API_BASE}/api/video/stream${this.token ? `?token=${encodeURIComponent(this.token)}` : ''}`;
  }

  // Evidence snapshot URL helper
  getEvidenceUrl(path) {
    if (!path) return null;
    if (path.startsWith('http')) return path;
    return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  }
}

export const api = new ApiClient();
export const authApi = api.auth;
export const overviewApi = api.overview;
export const agentApi = api.agent;
export const tasksApi = api.tasks;
export const devicesApi = api.devices;
export const eventsApi = api.events;
export default api;

