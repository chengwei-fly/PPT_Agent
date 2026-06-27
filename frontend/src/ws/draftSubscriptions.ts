import { subscribe } from "./client";

/** Draft WS event types. */
export interface DraftWsEvent {
  type:
    | "draft.locked"
    | "draft.unlocked"
    | "draft.saved"
    | "draft.slide.inserted"
    | "draft.slide.deleted"
    | "draft.exported";
  draft_id: string;
  user_id?: string;
  timestamp?: string;
  [key: string]: unknown;
}

/** Subscribe to draft events on the `draft:{draftId}` channel. */
export function subscribeDraftEvents(
  draftId: string,
  handler: (event: DraftWsEvent) => void,
): () => void {
  return subscribe(`draft:${draftId}`, (raw) => {
    handler(raw as unknown as DraftWsEvent);
  });
}

/** Subscribe to material index events on `user:{userId}:materials`. */
export function subscribeMaterialEvents(
  userId: string,
  handler: (event: Record<string, unknown>) => void,
): () => void {
  return subscribe(`user:${userId}:materials`, handler);
}
