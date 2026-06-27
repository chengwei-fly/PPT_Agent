import { create } from "zustand";
import type { GenerationTask, StageName, TraceStage } from "@/types/api";

/** Per-task UI state — combines server data (refetched via React Query)
 * with ephemeral UI state (queue position, cancel button, etc.). */
export interface GenerationState {
  activeTaskId: string | null;
  stagesByTask: Record<string, TraceStage[]>;
  setActiveTask: (id: string | null) => void;
  appendStageEvent: (taskId: string, stage: Partial<TraceStage>) => void;
  reset: () => void;
}

export const useGenerationStore = create<GenerationState>((set) => ({
  activeTaskId: null,
  stagesByTask: {},
  setActiveTask: (id) => set({ activeTaskId: id }),
  appendStageEvent: (taskId, stage) =>
    set((s) => {
      const existing = s.stagesByTask[taskId] ?? [];
      const idx = existing.findIndex((x) => x.stage_name === (stage.stage_name as StageName));
      const merged: TraceStage[] =
        idx >= 0
          ? existing.map((x, i) => (i === idx ? { ...x, ...stage } : x))
          : [...existing, stage as TraceStage];
      return { stagesByTask: { ...s.stagesByTask, [taskId]: merged } };
    }),
  reset: () => set({ activeTaskId: null, stagesByTask: {} }),
}));

/** Hook helpers — selector shortcuts. */
export const useActiveTask = (): string | null =>
  useGenerationStore((s) => s.activeTaskId);

/** Type guard for completed task state. */
export const isTerminal = (t: GenerationTask): boolean =>
  t.status === "success" || t.status === "failed" || t.status === "cancelled";
