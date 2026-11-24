class DashboardWebSocketService {
  constructor() {
    this.ws = null;
    this.subscribers = new Set();
    this.reconnectTimer = null;
    this.statusListeners = new Set();
    this.status = 'disconnected'; // 'connected', 'reconnecting', 'disconnected'
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const host = window.location.hostname || 'localhost';
    const wsUrl = `ws://${host}:8000/ws/dashboard`;

    this._setStatus('reconnecting');

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this._setStatus('connected');
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          this.subscribers.forEach((callback) => callback(payload));
        } catch (e) {
          console.debug('Raw WS message received:', event.data);
        }
      };

      this.ws.onclose = () => {
        this._setStatus('reconnecting');
        this._scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        console.warn('Dashboard WebSocket error, retrying...', err);
        this.ws.close();
      };
    } catch (e) {
      console.warn('Could not establish WebSocket connection:', e);
      this._setStatus('reconnecting');
      this._scheduleReconnect();
    }
  }

  _scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, 3000);
  }

  _setStatus(newStatus) {
    this.status = newStatus;
    this.statusListeners.forEach((fn) => fn(newStatus));
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  onStatusChange(callback) {
    this.statusListeners.add(callback);
    callback(this.status);
    return () => this.statusListeners.delete(callback);
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this._setStatus('disconnected');
  }
}

export const wsService = new DashboardWebSocketService();
