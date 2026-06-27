import { useCallback, useState } from "react";
import axios from "axios";
import { api } from "@/services/api";
import { toast } from "sonner";
import type { Sample } from "@/types/api";

/** US2 upload orchestration hook (T068 / T069).
 *
 * - Tracks per-file progress for the active batch
 * - Calls `POST /samples/batch` (multipart)
 * - Resolves with the created Sample[]; surfaces errors via toast
 * - Idempotent: if a file's SHA-256 already exists, backend returns 200 (no-op)
 */

export interface UploadItem {
  file: File;
  /** 0-100. `null` = not started. */
  progress: number | null;
  status: "queued" | "uploading" | "done" | "error";
  error?: string;
}

export interface UseSampleUpload {
  items: UploadItem[];
  inProgress: boolean;
  upload: (files: File[]) => Promise<Sample[]>;
  reset: () => void;
}

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_BATCH_COUNT = 20;

export function useSampleUpload(): UseSampleUpload {
  const [items, setItems] = useState<UploadItem[]>([]);
  const [inProgress, setInProgress] = useState(false);

  const reset = useCallback(() => setItems([]), []);

  const upload = useCallback(async (files: File[]): Promise<Sample[]> => {
    if (!files.length) return [];
    if (files.length > MAX_BATCH_COUNT) {
      toast.error(`单次最多 ${MAX_BATCH_COUNT} 个文件`);
      return [];
    }
    for (const f of files) {
      if (f.size > MAX_FILE_BYTES) {
        toast.error(`"${f.name}" 超过 50MB，已跳过`);
        return [];
      }
    }

    setItems(files.map((f) => ({ file: f, progress: 0, status: "queued" })));
    setInProgress(true);

    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));

    try {
      const resp = await api.post<Sample[]>("/samples/batch", form, {
        headers: { "Content-Type": "multipart/form-data" },
        // We can't track per-file progress with FormData in one request,
        // so we show indeterminate progress on the first item.
        onUploadProgress: (e) => {
          if (!e.total) return;
          const pct = Math.round((e.loaded * 100) / e.total);
          setItems((prev) =>
            prev.map((it, i) =>
              i === 0
                ? { ...it, progress: pct, status: pct >= 100 ? "done" : "uploading" }
                : it,
            ),
          );
        },
      });

      // Mark remaining items as done (they were sent in the same request)
      setItems((prev) =>
        prev.map((it) => ({ ...it, progress: 100, status: "done" as const })),
      );
      toast.success(`已上传 ${resp.data.length} 个样本`);
      return resp.data;
    } catch (err) {
      const msg =
        axios.isAxiosError(err)
          ? err.response?.data?.message ?? err.message
          : "上传失败";
      setItems((prev) =>
        prev.map((it) => ({
          ...it,
          status: "error" as const,
          error: msg,
        })),
      );
      toast.error(msg);
      return [];
    } finally {
      setInProgress(false);
    }
  }, []);

  return { items, inProgress, upload, reset };
}
