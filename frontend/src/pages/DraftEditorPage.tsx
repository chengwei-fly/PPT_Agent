import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/services/api";
import { subscribe } from "@/ws/client";
import {
  useDraft, useUpdateDraft, useInsertSlide, useDeleteSlide,
  useReorderSlides, useLockDraft, useUnlockDraft, useExportDraft, useExportJob,
} from "@/hooks/useDrafts";
import type { DraftSlide, SlideAsset } from "@/types/api";
import { toast } from "sonner";
import {
  ArrowLeft, Plus, Trash2, Download, Lock, Unlock,
  GripVertical, Image, FileText, Wand2,
} from "lucide-react";

const SOURCE_TYPE_CONFIG: Record<string, { label: string; icon: typeof Image; className: string }> = {
  reused: { label: "复用", icon: Image, className: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" },
  generated: { label: "AI 生成", icon: Wand2, className: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200" },
  manual: { label: "手动", icon: FileText, className: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200" },
};

export default function DraftEditorPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleValue, setTitleValue] = useState("");
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [showInsert, setShowInsert] = useState(false);
  const [exportJobId, setExportJobId] = useState<string | null>(null);

  const { data: draft, isLoading } = useDraft(draftId);
  const updateDraft = useUpdateDraft(draftId ?? "");
  const insertSlide = useInsertSlide(draftId ?? "");
  const deleteSlide = useDeleteSlide(draftId ?? "");
  const reorderSlides = useReorderSlides(draftId ?? "");
  const lockDraft = useLockDraft(draftId ?? "");
  const unlockDraft = useUnlockDraft(draftId ?? "");
  const exportDraft = useExportDraft(draftId ?? "");
  const { data: exportJob } = useExportJob(draftId ?? "", exportJobId);

  const { data: materialsData } = useQuery({
    queryKey: ["materials-for-insert"],
    queryFn: () => api.get<{ items: SlideAsset[] }>("/materials?limit=30").then((r) => r.data),
    enabled: showInsert,
  });

  // Handle export job completion
  useEffect(() => {
    if (!exportJob) return;
    if (exportJob.status === "ready") {
      toast.success("PPTX 导出完成");
      if (exportJob.pptx_path) window.open(exportJob.pptx_path, "_blank");
      setExportJobId(null);
    } else if (exportJob.status === "failed") {
      toast.error(`导出失败：${exportJob.error_message ?? "未知错误"}`);
      setExportJobId(null);
    }
  }, [exportJob]);

  // Subscribe to draft WS events
  useEffect(() => {
    if (!draftId) return;
    const unsub = subscribe(`draft:${draftId}`, (event) => {
      const type = event.type as string;
      if (type === "draft.saved" || type === "draft.slide.inserted") {
        queryClient.invalidateQueries({ queryKey: ["draft", draftId] });
      }
    });
    return unsub;
  }, [draftId, queryClient]);

  // Lock/unlock
  const handleLock = useCallback(() => {
    lockDraft.mutate(undefined, {
      onSuccess: () => toast.success("已锁定编辑"),
    });
  }, [lockDraft]);

  const handleUnlock = useCallback(() => {
    unlockDraft.mutate(undefined, {
      onSuccess: () => toast.success("已释放锁"),
    });
  }, [unlockDraft]);

  // Title update
  const handleTitleSave = useCallback(() => {
    if (!titleValue.trim() || titleValue === draft?.title) {
      setEditingTitle(false);
      return;
    }
    updateDraft.mutate(
      { title: titleValue.trim(), last_saved_revision: draft!.last_saved_revision },
      { onSuccess: () => setEditingTitle(false) },
    );
  }, [titleValue, draft, updateDraft]);

  // Insert slide
  const handleInsert = useCallback((materialId: string) => {
    insertSlide.mutate(
      { material_id: materialId },
      {
        onSuccess: () => {
          toast.success("已插入素材页");
          setShowInsert(false);
        },
      },
    );
  }, [insertSlide]);

  // Delete slide
  const handleDeleteSlide = useCallback((slideId: string) => {
    deleteSlide.mutate(slideId, {
      onSuccess: () => toast.success("已删除"),
    });
  }, [deleteSlide]);

  // Reorder slides
  const handleReorder = useCallback((fromIdx: number, toIdx: number) => {
    if (!draft) return;
    const sorted = [...draft.slides].sort((a, b) => a.slide_order - b.slide_order);
    const [moved] = sorted.splice(fromIdx, 1);
    sorted.splice(toIdx, 0, moved);
    const slideOrders = sorted.map((s, i) => ({ id: s.id, slide_order: i }));
    reorderSlides.mutate(slideOrders, {
      onSuccess: () => toast.success("排序已保存"),
    });
  }, [draft, reorderSlides]);

  // Export
  const handleExport = useCallback(() => {
    exportDraft.mutate(undefined, {
      onSuccess: (resp) => {
        setExportJobId(resp.job_id);
        toast.success("导出任务已提交");
      },
    });
  }, [exportDraft]);

  // Drag handlers
  const handleDragStart = (idx: number) => setDragIdx(idx);
  const handleDragOver = (e: React.DragEvent) => e.preventDefault();
  const handleDrop = (targetIdx: number) => {
    if (dragIdx === null || dragIdx === targetIdx) { setDragIdx(null); return; }
    handleReorder(dragIdx, targetIdx);
    setDragIdx(null);
  };

  const slides = draft?.slides ?? [];
  const isLocked = draft?.lock_expires_at && new Date(draft.lock_expires_at) > new Date();

  if (isLoading) {
    return <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">加载中…</div>;
  }
  if (!draft) {
    return <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">草稿不存在</div>;
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate("/drafts")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1 min-w-0">
          {editingTitle ? (
            <Input
              value={titleValue}
              onChange={(e) => setTitleValue(e.target.value)}
              onBlur={handleTitleSave}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleTitleSave();
                if (e.key === "Escape") setEditingTitle(false);
              }}
              className="h-8 text-lg font-semibold"
              autoFocus
            />
          ) : (
            <h1
              className="text-lg font-semibold cursor-pointer hover:text-primary truncate"
              onClick={() => { setTitleValue(draft.title); setEditingTitle(true); }}
            >
              {draft.title}
            </h1>
          )}
          <p className="text-xs text-muted-foreground">
            {slides.length} 页 · 版本 {draft.last_saved_revision}
          </p>
        </div>

        <div className="flex gap-2">
          {isLocked ? (
            <Button variant="outline" size="sm" onClick={handleUnlock} className="gap-1">
              <Unlock className="h-3.5 w-3.5" /> 解锁
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={handleLock} className="gap-1">
              <Lock className="h-3.5 w-3.5" /> 锁定
            </Button>
          )}
          <Button
            size="sm"
            onClick={handleExport}
            disabled={!!exportJobId || slides.length === 0}
            className="gap-1"
          >
            <Download className="h-3.5 w-3.5" />
            {exportJobId ? "导出中…" : "导出 PPTX"}
          </Button>
        </div>
      </div>

      {/* Lock warning */}
      {isLocked && draft.editor_user_id && (
        <Card className="border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950">
          <CardContent className="flex items-center gap-2 py-2 text-sm">
            <Lock className="h-4 w-4 text-amber-600" />
            <span>此草稿已锁定编辑，锁到期时间：{new Date(draft.lock_expires_at!).toLocaleString()}</span>
          </CardContent>
        </Card>
      )}

      {/* Slides */}
      {slides.length === 0 ? (
        <Card>
          <CardContent className="flex h-48 flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
            <FileText className="h-10 w-10" />
            <p>草稿为空 — 从素材库插入页面或等待 AI 生成</p>
            <Button variant="outline" size="sm" onClick={() => setShowInsert(true)}>
              <Plus className="h-3.5 w-3.5 mr-1" /> 插入素材
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {slides
            .sort((a, b) => a.slide_order - b.slide_order)
            .map((slide, idx) => (
              <SlideRow
                key={slide.id}
                slide={slide}
                index={idx}
                onDragStart={() => handleDragStart(idx)}
                onDragOver={handleDragOver}
                onDrop={() => handleDrop(idx)}
                onDelete={() => handleDeleteSlide(slide.id)}
              />
            ))}

          <div className="flex justify-center pt-2">
            <Button variant="outline" size="sm" onClick={() => setShowInsert(true)} className="gap-1">
              <Plus className="h-3.5 w-3.5" /> 插入素材页
            </Button>
          </div>
        </div>
      )}

      {/* Insert dialog */}
      <Dialog open={showInsert} onOpenChange={setShowInsert}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>选择素材插入</DialogTitle>
          </DialogHeader>
          <div className="overflow-y-auto max-h-[50vh] space-y-2 mt-2">
            {materialsData?.items?.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                暂无素材 — 先到素材库页上传 PPT 样本
              </p>
            ) : (
              <div className="grid grid-cols-3 gap-2">
                {materialsData?.items?.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => handleInsert(m.id)}
                    className="rounded border p-2 text-left hover:border-primary transition-colors"
                  >
                    <div className="aspect-[4/3] bg-muted rounded flex items-center justify-center mb-1 overflow-hidden">
                      {m.thumbnail_path ? (
                        <img src={m.thumbnail_path} alt="" className="h-full w-full object-cover" />
                      ) : (
                        <Image className="h-6 w-6 text-muted-foreground" />
                      )}
                    </div>
                    <div className="text-xs truncate">{m.title ?? `第 ${m.page_index + 1} 页`}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SlideRow({
  slide,
  index,
  onDragStart,
  onDragOver,
  onDrop,
  onDelete,
}: {
  slide: DraftSlide;
  index: number;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: () => void;
  onDelete: () => void;
}) {
  const config = SOURCE_TYPE_CONFIG[slide.source_type] ?? SOURCE_TYPE_CONFIG.manual;
  const Icon = config.icon;

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      className="flex items-center gap-3 rounded-lg border bg-card p-3 cursor-grab active:cursor-grabbing hover:shadow-sm transition-shadow"
    >
      <GripVertical className="h-4 w-4 text-muted-foreground shrink-0" />

      <div className="flex h-8 w-8 items-center justify-center rounded bg-muted text-xs font-medium shrink-0">
        {index + 1}
      </div>

      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">
          {slide.title ?? `幻灯片 ${index + 1}`}
        </div>
        {slide.body_text && (
          <div className="text-xs text-muted-foreground truncate">{slide.body_text}</div>
        )}
        {slide.notes && (
          <div className="text-xs text-muted-foreground/60 truncate mt-0.5">备注: {slide.notes}</div>
        )}
      </div>

      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium shrink-0 ${config.className}`}>
        <Icon className="h-3 w-3" />
        {config.label}
      </span>

      <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onDelete}>
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}
