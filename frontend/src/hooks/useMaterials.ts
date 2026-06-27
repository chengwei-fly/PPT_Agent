import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { SlideAsset } from "@/types/api";

export interface MaterialSearchResult {
  items: SlideAsset[];
  total: number;
  duration_ms: number;
}

/** Fetch paginated materials with optional filters. */
export function useMaterials(params?: {
  q?: string;
  visual_types?: string[];
  industry_tags?: string[];
  limit?: number;
}) {
  return useQuery({
    queryKey: ["materials", params],
    queryFn: async () => {
      const searchParams = new URLSearchParams();
      if (params?.q) searchParams.set("q", params.q);
      searchParams.set("limit", String(params?.limit ?? 50));
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
