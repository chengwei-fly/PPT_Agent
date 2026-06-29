import axios, { type AxiosError, type AxiosInstance } from "axios";
import { toast } from "sonner";

/** Base axios instance for the PPTagent backend.
 *
 * - Uses Vite proxy in dev: `/api` → `http://localhost:8000`
 * - Auth via `Authorization: Bearer <dev-key>` (stored in zustand)
 * - Surfaces RFC 7807 errors as toast messages
 */

const DEV_KEY = "dev-key";
const DEV_EMAIL = "dev@pptagent.local";

// Ensure dev credentials are always available
function ensureDevAuth(): void {
  const raw = localStorage.getItem("pptagent.auth");
  if (!raw) {
    localStorage.setItem("pptagent.auth", JSON.stringify({ apiKey: DEV_KEY, email: DEV_EMAIL }));
    return;
  }
  try {
    const parsed = JSON.parse(raw) as { apiKey?: string };
    if (!parsed.apiKey) {
      localStorage.setItem("pptagent.auth", JSON.stringify({ apiKey: DEV_KEY, email: DEV_EMAIL }));
    }
  } catch {
    localStorage.setItem("pptagent.auth", JSON.stringify({ apiKey: DEV_KEY, email: DEV_EMAIL }));
  }
}
ensureDevAuth();

export const api: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? "/api",
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${DEV_KEY}`,
  },
});

// ── Request interceptor — attach bearer + idempotency keys ─────────
api.interceptors.request.use((config) => {
  config.headers = config.headers ?? {};
  // Always attach dev key for development
  config.headers["Authorization"] = `Bearer ${DEV_KEY}`;
  return config;
});

// ── Response interceptor — uniform error handling ──────────────────
api.interceptors.response.use(
  (resp) => resp,
  (err: AxiosError<{ code?: string; title?: string; message?: string }>) => {
    const data = err.response?.data ?? {};
    const code = (data as { code?: string }).code ?? "HTTP_ERROR";
    const message =
      (data as { title?: string }).title ??
      (data as { message?: string }).message ??
      err.message;
    if (err.response?.status && err.response.status >= 500) {
      toast.error(`[${code}] ${message}`);
    } else if (err.response?.status === 429) {
      toast.warning(`请求过于频繁：${message}`);
    } else {
      toast.error(message);
    }
    return Promise.reject(err);
  },
);
