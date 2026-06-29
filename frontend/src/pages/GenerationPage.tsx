import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { api } from "@/services/api";
import { toast } from "sonner";
import { GenerationRunner } from "@/components/generation/GenerationRunner";
import { UploadDropzone } from "@/components/knowledge/UploadDropzone";
import { useSampleUpload } from "@/hooks/useSampleUpload";
import type { GenerationTask, VisualStyleOption, CommunicationModeOption } from "@/types/api";
import { Palette, MessageSquare, Sparkles, Database, FileText, X } from "lucide-react";

type Mode = "knowledge_base" | "general";

/** US1 — one-prompt generation entry page + task runner. */
export default function GenerationPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();

  // If we have a taskId, show the runner
  if (taskId) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <GenerationRunner taskId={taskId} />
        <Button variant="outline" onClick={() => navigate("/generate")}>
          新建任务
        </Button>
      </div>
    );
  }

  return <GenerationForm />;
}

function GenerationForm() {
  const [mode, setMode] = useState<Mode>("general");
  const [prompt, setPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  // General mode options
  const [visualStyle, setVisualStyle] = useState<string | null>(null);
  const [communicationMode, setCommunicationMode] = useState<string | null>(null);
  const [styles, setStyles] = useState<VisualStyleOption[]>([]);
  const [modes, setModes] = useState<CommunicationModeOption[]>([]);

  // Source file upload
  const { items: uploadItems, inProgress: uploading, upload } = useSampleUpload();
  const [attachedFiles, setAttachedFiles] = useState<{ id: string; name: string }[]>([]);

  // Fetch available styles and modes
  useEffect(() => {
    api.get<VisualStyleOption[]>("/generations/styles").then((r) => setStyles(r.data)).catch(() => {});
    api.get<CommunicationModeOption[]>("/generations/modes").then((r) => setModes(r.data)).catch(() => {});
  }, []);

  const handleFilesSelected = async (files: File[]) => {
    const samples = await upload(files);
    if (samples.length > 0) {
      setAttachedFiles((prev) => [
        ...prev,
        ...samples.map((s) => ({ id: s.id, name: s.file_name })),
      ]);
    }
  };

  const removeAttached = (id: string) => {
    setAttachedFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const submit = async () => {
    if (!prompt.trim()) {
      toast.warning("请输入一句话需求");
      return;
    }
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = { prompt, mode };
      if (attachedFiles.length > 0) {
        if (mode === "general") {
          body.source_files = attachedFiles.map((f) => f.id);
        } else {
          body.sample_ids = attachedFiles.map((f) => f.id);
        }
      }
      if (mode === "general") {
        if (visualStyle) body.visual_style = visualStyle;
        if (communicationMode) body.communication_mode = communicationMode;
      }
      // POST response uses "task_id" (QueuedGenerationResponse), not "id"
      const resp = await api.post<{ task_id: string; queue_position: number }>("/generations", body);
      toast.success(`已入队，位置 #${resp.data.queue_position ?? "?"}`);
      navigate(`/generate/${resp.data.task_id}`);
    } catch {
      // Toast already shown by interceptor
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Mode toggle */}
      <div className="flex gap-2">
        <Button
          variant={mode === "general" ? "default" : "outline"}
          onClick={() => setMode("general")}
          className="flex-1 gap-2"
        >
          <Sparkles className="h-4 w-4" />
          通用生成
        </Button>
        <Button
          variant={mode === "knowledge_base" ? "default" : "outline"}
          onClick={() => setMode("knowledge_base")}
          className="flex-1 gap-2"
        >
          <Database className="h-4 w-4" />
          知识库生成
        </Button>
      </div>

      {/* Prompt card */}
      <Card>
        <CardHeader>
          <CardTitle>{mode === "general" ? "通用 PPT 生成" : "知识库 PPT 生成"}</CardTitle>
          <CardDescription>
            {mode === "general"
              ? "描述你的 PPT 主题和需求，AI 将生成专业的大纲、内容和设计。"
              : "用一句自然语言描述需求，基于知识库样本风格对齐生成 PPTX。"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={
              mode === "general"
                ? "例如：做一份 12 页的 AI 技术趋势报告，面向投资人，风格要科技感。"
                : "例如：做一份 12 页的 Q3 储能立项汇报，目标读者是集团战略部。"
            }
            rows={4}
            disabled={submitting}
          />

          {/* Source document upload (available in both modes) */}
          <div className="space-y-2">
            <label className="flex items-center gap-1.5 text-sm font-medium">
              <FileText className="h-3.5 w-3.5" />
              附件材料
              <span className="text-muted-foreground font-normal">（可选，基于文档内容生成）</span>
            </label>
            <UploadDropzone
              onFilesSelected={handleFilesSelected}
              disabled={submitting || uploading}
            />
            {/* Upload progress */}
            {uploadItems.length > 0 && uploading && (
              <div className="space-y-1 text-xs text-muted-foreground">
                {uploadItems.map((it, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="truncate flex-1">{it.file.name}</span>
                    <span>{it.status === "done" ? "✓" : it.status === "error" ? "✗" : "…"}</span>
                  </div>
                ))}
              </div>
            )}
            {/* Attached files */}
            {attachedFiles.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {attachedFiles.map((f) => (
                  <span
                    key={f.id}
                    className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary"
                  >
                    <FileText className="h-3 w-3" />
                    {f.name}
                    <button
                      type="button"
                      onClick={() => removeAttached(f.id)}
                      className="ml-0.5 rounded-full hover:bg-primary/20"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* General mode options */}
          {mode === "general" && (
            <div className="space-y-4">
              {/* Communication mode */}
              <div className="space-y-2">
                <label className="flex items-center gap-1.5 text-sm font-medium">
                  <MessageSquare className="h-3.5 w-3.5" />
                  沟通模式
                  <span className="text-muted-foreground font-normal">（可选）</span>
                </label>
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                  <button
                    type="button"
                    onClick={() => setCommunicationMode(null)}
                    className={`rounded-lg border p-2 text-left text-xs transition-colors ${
                      !communicationMode
                        ? "border-primary bg-primary/5"
                        : "hover:border-primary/50"
                    }`}
                  >
                    <div className="font-medium">自动</div>
                  </button>
                  {modes.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => setCommunicationMode(m.id)}
                      className={`rounded-lg border p-2 text-left text-xs transition-colors ${
                        communicationMode === m.id
                          ? "border-primary bg-primary/5"
                          : "hover:border-primary/50"
                      }`}
                      title={m.best_for}
                    >
                      <div className="font-medium">{m.name}</div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground line-clamp-2">
                        {m.narrative_skeleton}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Visual style */}
              <div className="space-y-2">
                <label className="flex items-center gap-1.5 text-sm font-medium">
                  <Palette className="h-3.5 w-3.5" />
                  视觉风格
                  <span className="text-muted-foreground font-normal">（可选）</span>
                </label>
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
                  <button
                    type="button"
                    onClick={() => setVisualStyle(null)}
                    className={`rounded-lg border p-2 text-left text-xs transition-colors ${
                      !visualStyle
                        ? "border-primary bg-primary/5"
                        : "hover:border-primary/50"
                    }`}
                  >
                    <div className="font-medium">自动</div>
                  </button>
                  {styles.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => setVisualStyle(s.id)}
                      className={`rounded-lg border p-2 text-left text-xs transition-colors ${
                        visualStyle === s.id
                          ? "border-primary bg-primary/5"
                          : "hover:border-primary/50"
                      }`}
                      title={s.best_for}
                    >
                      <div className="font-medium">{s.name}</div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground line-clamp-2">
                        {s.character}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setPrompt("")} disabled={submitting}>
              清空
            </Button>
            <Button onClick={submit} disabled={submitting}>
              {submitting ? "提交中…" : "开始生成"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Tips */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">提示</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          {mode === "general" ? (
            <>
              <p>• 上传附件（PDF / DOCX / PPTX）后，AI 会基于文档内容生成 PPT，无需手动整理素材。</p>
              <p>• 选择沟通模式可以控制叙事结构（金字塔、故事线、教学式等）。</p>
              <p>• 选择视觉风格可以控制设计语言（瑞士极简、暗黑科技、编辑排版等）。</p>
              <p>• 生成的 PPTX 使用原生 DrawingML 形状，可在 PowerPoint 中直接编辑。</p>
            </>
          ) : (
            <>
              <p>• 上传附件后，系统会自动解析文档内容并纳入生成上下文。</p>
              <p>• 知识库为空时，生成的 PPT 不会"风格对齐"——先到"知识库"页上传 3 份样本。</p>
              <p>• 单用户最多 2 个并发任务；超过会进入排队状态（5 分钟内入队）。</p>
              <p>• 任务执行中可随时取消，5 秒内生效。</p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
