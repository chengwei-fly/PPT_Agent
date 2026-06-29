import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { SlideAsset } from "@/types/api";

export type MaterialScope = "curated" | "mine" | "all";

export interface MaterialSearchResult {
  items: SlideAsset[];
  total: number;
  duration_ms: number;
}

export interface CuratedImportResult {
  files_seen: number;
  files_failed: number;
  assets_extracted: number;
  assets_inserted: number;
  assets_updated: number;
  assets_skipped: number;
  inserted_ids: string[];
  failures: string[];
  classification_counts: Record<string, number>;
}

export interface CuratedStats {
  total: number;
  by_visual_type: Record<string, number>;
  by_source_file: Record<string, number>;
  last_import_at: string | null;
}

/** Fetch paginated materials with optional filters. */
export function useMaterials(params?: {
  q?: string;
  visual_types?: string[];
  industry_tags?: string[];
  scope?: MaterialScope;
  limit?: number;
}) {
  return useQuery({
    queryKey: ["materials", params],
    queryFn: async () => {
      const searchParams = new URLSearchParams();
      if (params?.q) searchParams.set("q", params.q);
      searchParams.set("limit", String(params?.limit ?? 50));
      if (params?.scope && params.scope !== "all") {
        searchParams.set("scope", params.scope);
      }
      params?.visual_types?.forEach((t) => searchParams.append("visual_types", t));
      params?.industry_tags?.forEach((t) => searchParams.append("industry_tags", t));
      const { data } = await api.get<MaterialSearchResult>(`/materials?${searchParams.toString()}`);
      return data;
    },
  });
}

/** Fetch a single material by ID. */
export function useMaterial(id: string | undefined) {
  return useQuery({
    queryKey: ["materials", id],
    queryFn: async () => {
      const { data } = await api.get<SlideAsset>(`/materials/${id}`);
      return data;
    },
    enabled: !!id,
  });
}

/** Delete a material. */
export function useDeleteMaterial() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/materials/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["materials"] }),
  });
}

/** Admin: upload a single PPTX for curated import. */
export function useCuratedImport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      // Admin endpoint requires ``X-Admin-Token`` in addition to the
      // standard bearer — fall back to the dev-key used in dev mode.
      const adminToken =
        (import.meta.env.VITE_ADMIN_TOKEN as string | undefined) ?? "dev-key";
      const { data } = await api.post<CuratedImportResult>(
        "/admin/material-library/import",
        form,
        {
          headers: {
            "Content-Type": "multipart/form-data",
            "X-Admin-Token": adminToken,
          },
        },
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["materials"] }),
  });
}

/** Admin: get stats of the curated library. */
export function useCuratedStats(enabled = true) {
  return useQuery({
    queryKey: ["materials", "curated-stats"],
    queryFn: async () => {
      const { data } = await api.get<CuratedStats>("/admin/material-library/stats");
      return data;
    },
    enabled,
  });
}
