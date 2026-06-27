import { useCallback, useRef, useState } from "react";
import { UploadCloud, FileText, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatBytes } from "@/lib/utils";

/** T069 — Drag-and-drop upload zone for PPTX / PDF / DOCX samples.
 *
 * Validates client-side:
 *   - Extension allowlist (mirrors backend `FileType` enum)
 *   - 50 MB per-file cap (FR-006)
 *   - 20 files per batch cap (FR-006)
 *
 * Emits the selected File[] via `onFilesSelected`. The parent owns the
 * upload lifecycle (progress + axios request) so we can reuse the same
 * zone for both create + re-upload flows. */

const ALLOWED_EXT = ["pptx", "pdf", "docx"] as const;
const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_BATCH_COUNT = 20;

export interface UploadDropzoneProps {
  onFilesSelected: (files: File[]) => void;
  disabled?: boolean;
  className?: string;
}

interface ValidationIssue {
  file: File;
  reason: string;
}

export function UploadDropzone({
  onFilesSelected,
  disabled,
  className,
}: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isOver, setIsOver] = useState(false);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);

  const validate = useCallback((files: File[]): { ok: File[]; bad: ValidationIssue[] } => {
    const ok: File[] = [];
    const bad: ValidationIssue[] = [];
    if (files.length > MAX_BATCH_COUNT) {
      bad.push({
        file: files[0]!,
        reason: `单次最多 ${MAX_BATCH_COUNT} 个文件（已选 ${files.length}）`,
      });
      return { ok, bad };
    }
    for (const f of files) {
      const ext = (f.name.split(".").pop() ?? "").toLowerCase();
      if (!ALLOWED_EXT.includes(ext as (typeof ALLOWED_EXT)[number])) {
        bad.push({ file: f, reason: `不支持的格式 .${ext || "?"}（仅 ${ALLOWED_EXT.join(" / ")}）` });
        continue;
      }
      if (f.size > MAX_FILE_BYTES) {
        bad.push({ file: f, reason: `超过 50MB（${formatBytes(f.size)}）` });
        continue;
      }
      ok.push(f);
    }
    return { ok, bad };
  }, []);

  const handleFiles = useCallback(
    (rawList: FileList | File[]) => {
      const files = Array.from(rawList);
      if (!files.length) return;
      const { ok, bad } = validate(files);
      setIssues(bad);
      if (ok.length) onFilesSelected(ok);
    },
    [onFilesSelected, validate],
  );

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsOver(false);
    if (disabled) return;
    handleFiles(e.dataTransfer.files);
  };

  const onDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;
    setIsOver(true);
  };

  const onDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsOver(false);
  };

  return (
    <div className={cn("space-y-3", className)}>
      <div
        role="button"
        tabIndex={0}
        aria-disabled={disabled}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center transition-colors",
          isOver ? "border-primary bg-primary/5" : "border-muted-foreground/30 hover:border-primary/60",
          disabled && "pointer-events-none opacity-50",
        )}
      >
        <UploadCloud className="h-10 w-10 text-muted-foreground" aria-hidden />
        <div className="space-y-1">
          <p className="text-sm font-medium">
            {isOver ? "松开鼠标即可上传" : "拖拽样本到此处，或点击选择文件"}
          </p>
          <p className="text-xs text-muted-foreground">
            支持 PPTX / PDF / DOCX · 单文件 ≤ 50MB · 单次 ≤ {MAX_BATCH_COUNT} 个
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            inputRef.current?.click();
          }}
          disabled={disabled}
        >
          <FileText className="mr-2 h-4 w-4" />
          选择文件
        </Button>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          multiple
          accept=".pptx,.pdf,.docx"
          onChange={(e) => {
            if (e.target.files) handleFiles(e.target.files);
            // Reset so the same file can be picked again
            e.target.value = "";
          }}
        />
      </div>

      {issues.length > 0 && (
        <ul className="space-y-1 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs">
          {issues.map((it, i) => (
            <li key={i} className="flex items-start gap-2 text-destructive">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              <span>
                <span className="font-medium">{it.file.name}</span> — {it.reason}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
