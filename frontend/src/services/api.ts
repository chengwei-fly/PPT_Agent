import axios, { type AxiosError, type AxiosInstance } from "axios";
import { toast } from "sonner";

/** Base axios instance for the PPTagent backend.
 *
 * - Uses Vite proxy in dev: `/api` → `http://localhost:8000`
 * - Auth via `Authorization: Bearer <dev-key>` (stored in zustand)
 * - Surfaces RFC 7807 errors as toast messages
 */
export const api: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? "/api",
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
});

// ── Request interceptor — attach bearer + idempotency keys ─────────
api.interceptors.request.use((config) => {
  const authRaw = localStorage.getItem("pptagent.auth");
  if (authRaw) {
    try {
      const { apiKey } = JSON.parse(authRaw) as { apiKey?: string };
      if (apiKey) {
        config.headers = config.headers ?? {};
        config.headers["Authorization"] = `Bearer ${apiKey}`;
      }
    } catch {
      /* ignore */
    }
  }
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
