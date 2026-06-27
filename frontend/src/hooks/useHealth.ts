import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { HealthResponse } from "@/types/api";

/** Polls `/healthz` to show backend status in the app header (T110). */
export function useHealth(intervalMs = 30_000) {
  return useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: async () => (await api.get<HealthResponse>("/healthz")).data,
    refetchInterval: intervalMs,
    retry: false,
  });
}
