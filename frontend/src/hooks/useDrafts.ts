import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { Draft, DraftSlide } from "@/types/api";

/** Fetch all drafts for the current user. */
export function useDrafts() {
  return useQuery({
    queryKey: ["drafts"],
    queryFn: async () => {
      const { data } = await api.get<Draft[]>("/drafts");
      return data;
    },
  });
}

/** Fetch a single draft with slides. */
export function useDraft(id: string | undefined) {
  return useQuery({
    queryKey: ["drafts", id],
    queryFn: async () => {
      const { data } = await api.get<Draft>(`/drafts/${id}`);
      return data;
    },
    enabled: !!id,
    refetchOnWindowFocus: false,
  });
}

/** Create a new draft. */
export function useCreateDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title: string) =>
      api.post<Draft>("/drafts", { title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["drafts"] }),
  });
}

/** Delete a draft. */
export function useDeleteDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/drafts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["drafts"] }),
  });
}

/** Update draft title with optimistic locking. */
export function useUpdateDraft(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { title?: string; last_saved_revision: number }) =>
      api.patch<Draft>(`/drafts/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["drafts", id] }),
  });
}

/** Insert a slide into a draft. */
export function useInsertSlide(draftId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      material_id?: string;
      generated_stage_id?: string;
      insert_at?: number;
    }) => api.post<DraftSlide>(`/drafts/${draftId}/slides`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["drafts", draftId] }),
  });
}

/** Delete a slide from a draft. */
export function useDeleteSlide(draftId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slideId: string) =>
      api.delete(`/drafts/${draftId}/slides/${slideId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["drafts", draftId] }),
  });
}

/** Reorder slides in a draft. */
export function useReorderSlides(draftId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slideOrders: Array<{ id: string; slide_order: number }>) =>
      api.patch(`/drafts/${draftId}/slides/reorder`, { slides: slideOrders }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["drafts", draftId] }),
  });
}

/** Acquire draft lock. */
export function useLockDraft(draftId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post(`/drafts/${draftId}/lock`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["drafts", draftId] }),
  });
}

/** Release draft lock. */
export function useUnlockDraft(draftId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete(`/drafts/${draftId}/lock`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["drafts", draftId] }),
  });
}

/** Start draft export. Returns job_id. */
export function useExportDraft(draftId: string) {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ job_id: string; status: string }>(
        `/drafts/${draftId}/export`,
      );
      return data;
    },
  });
}

/** Poll export job status. */
export function useExportJob(draftId: string, jobId: string | null) {
  return useQuery({
    queryKey: ["drafts", draftId, "export", jobId],
    queryFn: async () => {
      const { data } = await api.get<{
        job_id: string;
        status: string;
        progress: number;
        pptx_path: string | null;
        error_message?: string;
      }>(`/drafts/${draftId}/export/${jobId}`);
      return data;
    },
    enabled: !!jobId,
    refetchInterval: (query) =>
      query.state.data?.status === "completed" ||
      query.state.data?.status === "failed"
        ? false
        : 2000,
  });
}
