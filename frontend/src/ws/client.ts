/** WebSocket client for PPTagent real-time events.
 *
 * Channels:
 * - `task:{taskId}` — generation progress events
 * - `user:{userId}:materials` — material index events
 * - `draft:{draftId}` — draft lock/save/export events
 */

type EventHandler = (event: Record<string, unknown>) => void;

interface WsConnection {
  ws: WebSocket | null;
  channel: string;
  handlers: Set<EventHandler>;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  closed: boolean;
  retryCount: number;
}

const connections = new Map<string, WsConnection>();

function getWsUrl(channel: string): string {
  const base = import.meta.env.VITE_WS_BASE ??
    `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;
  const apiKey = getApiKey();
  const params = new URLSearchParams({ channel });
  if (apiKey) params.set("token", apiKey);
  // Backend WS endpoint is at /ws/ with trailing slash per FastAPI router
  return `${base}/api/ws/?${params.toString()}`;
}

function getApiKey(): string | null {
  try {
    const raw = localStorage.getItem("pptagent.auth");
    if (raw) {
      const { apiKey } = JSON.parse(raw) as { apiKey?: string };
      return apiKey ?? null;
    }
  } catch { /* ignore */ }
  return null;
}

/** Subscribe to a WebSocket channel. Returns an unsubscribe function. */
export function subscribe(channel: string, handler: EventHandler): () => void {
  let conn = connections.get(channel);

  if (!conn) {
    conn = {
      ws: null,
      channel,
      handlers: new Set(),
      reconnectTimer: null,
      closed: false,
      retryCount: 0,
    };
    connections.set(channel, conn);
    _connect(conn);
  }

  conn.handlers.add(handler);

  return () => {
    conn!.handlers.delete(handler);
    if (conn!.handlers.size === 0) {
      _disconnect(conn!);
      connections.delete(channel);
    }
  };
}

/** Send a JSON message on a channel's connection. */
export function send(channel: string, data: Record<string, unknown>): void {
  const conn = connections.get(channel);
  if (conn?.ws?.readyState === WebSocket.OPEN) {
    conn.ws.send(JSON.stringify(data));
  }
}

function _connect(conn: WsConnection): void {
  if (conn.closed) return;

  const url = getWsUrl(conn.channel);
  const ws = new WebSocket(url);
  conn.ws = ws;

  ws.onopen = () => {
    // Reset reconnect delay on successful connection
    conn.retryCount = 0;
  };

  ws.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data) as Record<string, unknown>;
      // Skip internal hello/pong messages
      if (data.type === "hello" || data.type === "pong") return;
      for (const handler of conn.handlers) {
        try { handler(data); } catch { /* handler error */ }
      }
    } catch { /* parse error */ }
  };

  ws.onclose = (evt) => {
    conn.ws = null;
    if (!conn.closed && evt.code !== 1000) {
      // Reconnect with exponential backoff (1s, 2s, 4s, 8s, … max 30s)
      const delay = Math.min(30_000, 1000 * Math.pow(2, conn.retryCount));
      conn.retryCount++;
      conn.reconnectTimer = setTimeout(() => _connect(conn), delay);
    }
  };

  ws.onerror = () => {
    ws.close();
  };

  // Heartbeat ping every 30s
  const pingInterval = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping", ts: Date.now() }));
    } else {
      clearInterval(pingInterval);
    }
  }, 30_000);

  ws.addEventListener("close", () => clearInterval(pingInterval));
}

function _disconnect(conn: WsConnection): void {
  conn.closed = true;
  if (conn.reconnectTimer) {
    clearTimeout(conn.reconnectTimer);
    conn.reconnectTimer = null;
  }
  if (conn.ws) {
    conn.ws.close(1000);
    conn.ws = null;
  }
}
