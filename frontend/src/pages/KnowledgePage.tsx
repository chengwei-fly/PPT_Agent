import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, FileText, RefreshCw, AlertTriangle, Loader2, FileStack, Images } from "lucide-react";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/services/api";
import { formatBytes, formatLocalDateTime } from "@/lib/utils";
import type { ParseStatus, Sample } from "@/types/api";
import { UploadDropzone } from "@/components/knowledge/UploadDropzone";
import { PiiBadge, PiiDetail } from "@/components/knowledge/PiiBadge";
import { MaterialAssetsTab } from "@/components/knowledge/MaterialAssetsTab";
import { useSampleUpload } from "@/hooks/useSampleUpload";

/** T068 — US2 RAG 知识库统一管理页。
 *
 * 整合后包含两个子库：
 *   - 「文档」: 用户上传 PPTX/PDF/DOCX，系统解析文本与版式并向量化，用于风格对齐 + 内容 RAG 召回
 *   - 「素材资产」: 精选共享库 + 用户样本的视觉单页素材，用于生成时复用视觉资产
 *
 * 二者共用同一个 Embedder，但底层表不同（samples/embeddings vs slide_assets），
 * 检索侧由后端 KnowledgeRetriever（文本）+ MaterialSearchService（视觉）提供。
 *
 * 行为:
 *   - 解析中样本自动轮询刷新（10s 间隔）
 *   - 上传后 SHA-256 自动去重；删除为软删除（30 天保留后清理）
 */

const PARSE_STATUS_LABEL: Record<ParseStatus, string> = {
  pending: "等待解析",
  parsing: "解析中",
  parsed: "已就绪",
  failed: "解析失败",
};

const PARSE_STATUS_CLASS: Record<ParseStatus, string> = {
  pending: "bg-slate-100 text-slate-700",
  parsing: "bg-blue-50 text-blue-700",
  parsed: "bg-emerald-50 text-emerald-700",
  failed: "bg-red-50 text-red-700",
};

const FILE_TYPE_LABEL: Record<Sample["file_type"], string> = {
  pptx: "PPTX",
  pdf: "PDF",
  docx: "DOCX",
};

type KnowledgeTab = "documents" | "assets";

export default function KnowledgePage() {
  const [tab, setTab] = useState<KnowledgeTab>("documents");
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">知识库</h1>
          <p className="text-sm text-muted-foreground">
            构建 RAG 知识库：上传文档以提取内容与风格，导入或抽取视觉资产以复用版式
          </p>
        </div>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as KnowledgeTab)}>
        <TabsList>
          <TabsTrigger value="documents" className="gap-1.5">
            <FileStack className="h-3.5 w-3.5" />
            文档
          </TabsTrigger>
          <TabsTrigger value="assets" className="gap-1.5">
            <Images className="h-3.5 w-3.5" />
            素材资产
          </TabsTrigger>
        </TabsList>

        <TabsContent value="documents">
          <DocumentsTab />
        </TabsContent>
        <TabsContent value="assets">
          <MaterialAssetsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/** 「文档」Tab — 样本上传、解析状态、PII 处置、删除（原 KnowledgePage 内容） */
function DocumentsTab() {
  const qc = useQueryClient();
  const [detailSample, setDetailSample] = useState<Sample | null>(null);
  const { items, inProgress, upload, reset } = useSampleUpload();

  const samplesQuery = useQuery<Sample[]>({
    queryKey: ["samples"],
    queryFn: async () => (await api.get<Sample[]>("/samples?limit=100")).data,
  });

  const hasInflight = useMemo(
    () =>
      (samplesQuery.data ?? []).some(
        (s) => s.parse_status === "pending" || s.parse_status === "parsing",
      ),
    [samplesQuery.data],
  );

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/samples/${id}`);
    },
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ["samples"] });
      const prev = qc.getQueryData<Sample[]>(["samples"]) ?? [];
      qc.setQueryData<Sample[]>(
        ["samples"],
        prev.map((s) => (s.id === id ? { ...s, deleted_at: new Date().toISOString() } : s)),
      );
      return { prev };
    },
    onError: (_e, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(["samples"], ctx.prev);
      toast.error("删除失败");
    },
    onSuccess: () => toast.success("样本已删除"),
    onSettled: () => qc.invalidateQueries({ queryKey: ["samples"] }),
  });

  const handleFiles = useCallback(
    async (files: File[]) => {
      const created = await upload(files);
      if (created.length) {
        await qc.invalidateQueries({ queryKey: ["samples"] });
        // Auto-clear progress chips after 1.5s
        setTimeout(reset, 1500);
      } else {
        reset();
      }
    },
    [upload, qc, reset],
  );

  const visibleSamples = useMemo(
    () => (samplesQuery.data ?? []).filter((s) => !s.deleted_at),
    [samplesQuery.data],
  );

  return (
    <div className="space-y-6">
      {/* ── Upload area ───────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>上传文档</CardTitle>
          <CardDescription>
            上传 PPTX / PDF / DOCX 样本，系统会解析文本与版式并提取风格特征，用于生成时的风格对齐与双模检索。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <UploadDropzone
            onFilesSelected={handleFiles}
            disabled={inProgress}
          />
          {items.length > 0 && (
            <ul className="space-y-2 rounded-md border bg-muted/30 p-3">
              {items.map((it, i) => (
                <li key={i} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2 truncate">
                      <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      <span className="truncate font-medium">{it.file.name}</span>
                      <span className="shrink-0 text-muted-foreground">
                        {formatBytes(it.file.size)}
                      </span>
                    </span>
                    <span className="shrink-0 text-muted-foreground">
                      {it.status === "error" ? (
                        <span className="text-destructive">{it.error ?? "失败"}</span>
                      ) : it.status === "done" ? (
                        "完成"
                      ) : (
                        `${it.progress ?? 0}%`
                      )}
                    </span>
                  </div>
                  <Progress
                    value={it.progress ?? (it.status === "done" ? 100 : 0)}
                    className="h-1"
                  />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* ── Sample list ───────────────────────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="text-base">已上传文档 ({visibleSamples.length})</CardTitle>
            <CardDescription>
              同一文件 SHA-256 已自动去重；删除为软删除（30 天保留后清理）。
            </CardDescription>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => qc.invalidateQueries({ queryKey: ["samples"] })}
            disabled={samplesQuery.isFetching}
          >
            {samplesQuery.isFetching ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="mr-1 h-3.5 w-3.5" />
            )}
            刷新
          </Button>
        </CardHeader>
        <CardContent>
          {samplesQuery.isLoading ? (
            <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载中…
            </div>
          ) : visibleSamples.length === 0 ? (
            <div className="flex h-32 flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
              <FileText className="h-6 w-6" aria-hidden />
              <p>还没有样本。至少上传 3 份以获得最佳风格对齐效果。</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr className="border-b">
                    <th className="py-2 pr-3 font-medium">文件</th>
                    <th className="py-2 pr-3 font-medium">类型</th>
                    <th className="py-2 pr-3 font-medium">解析状态</th>
                    <th className="py-2 pr-3 font-medium">PII</th>
                    <th className="py-2 pr-3 font-medium">上传时间</th>
                    <th className="py-2 pr-3 font-medium text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleSamples.map((s) => (
                    <tr
                      key={s.id}
                      className="border-b last:border-b-0 hover:bg-muted/40"
                    >
                      <td className="py-3 pr-3">
                        <div className="flex flex-col">
                          <span className="font-medium">{s.file_name}</span>
                          {s.parse_page_count != null && (
                            <span className="text-xs text-muted-foreground">
                              {s.parse_page_count} 页
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 pr-3">
                        <span className="rounded bg-secondary px-1.5 py-0.5 text-xs font-mono">
                          {FILE_TYPE_LABEL[s.file_type]}
                        </span>
                      </td>
                      <td className="py-3 pr-3">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${PARSE_STATUS_CLASS[s.parse_status]}`}
                        >
                          {s.parse_status === "parsing" && (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          )}
                          {PARSE_STATUS_LABEL[s.parse_status]}
                        </span>
                      </td>
                      <td className="py-3 pr-3">
                        <PiiBadge
                          summary={s.pii_summary}
                          onClick={() => s.pii_summary && setDetailSample(s)}
                        />
                      </td>
                      <td className="py-3 pr-3 text-xs text-muted-foreground">
                        <div>{formatLocalDateTime(s.uploaded_at)}</div>
                        <div>
                          {formatDistanceToNow(new Date(s.uploaded_at), {
                            addSuffix: true,
                            locale: zhCN,
                          })}
                        </div>
                      </td>
                      <td className="py-3 pr-3 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (confirm(`确认删除「${s.file_name}」？`)) {
                              deleteMutation.mutate(s.id);
                            }
                          }}
                          disabled={deleteMutation.isPending}
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {hasInflight && (
                <p className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  解析中…本页面会自动刷新。
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── PII detail dialog ─────────────────────────────────────── */}
      <Dialog open={!!detailSample} onOpenChange={(open) => { if (!open) setDetailSample(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>PII 处置详情</DialogTitle>
            <DialogDescription className="truncate">
              {detailSample?.file_name}
            </DialogDescription>
          </DialogHeader>
          {detailSample?.pii_summary && (
            <div className="space-y-3">
              <PiiDetail summary={detailSample.pii_summary} />
              {detailSample.parse_status === "failed" && (
                <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>解析失败时 PII 处置可能未执行，请重新上传样本。</span>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
