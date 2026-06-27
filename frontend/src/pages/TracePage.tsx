import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/services/api";
import type { TraceStage, GenerationTask, StageName } from "@/types/api";
import { ArrowLeft, Clock, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { RedoButton } from "@/components/trace/RedoButton";

const STAGE_LABELS: Record<StageName, string> = {
  outline: "大纲生成",
  points: "要点提取",
  svg: "SVG 渲染",
  pptx: "PPTX 导出",
};

const STAGE_DESCRIPTIONS: Record<StageName, string> = {
  outline: "基于需求和知识库生成 PPT 结构大纲",
  points: "为每页提取核心要点和数据支撑",
  svg: "将要点渲染为可视化的 SVG 幻灯片",
  pptx: "将 SVG 转换为可下载的 PPTX 文件",
};

export default function TracePage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();

  const { data: task } = useQuery({
    queryKey: ["generation", taskId],
    queryFn: () => api.get<GenerationTask>(`/generations/${taskId}`).then((r) => r.data),
    enabled: !!taskId,
  });

  const { data: stages, isLoading } = useQuery({
    queryKey: ["trace", taskId],
    queryFn: () => api.get<TraceStage[]>(`/generations/${taskId}/trace`).then((r) => r.data),
    enabled: !!taskId,
  });

  if (!taskId) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        未指定任务 ID
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-lg font-semibold">生成轨迹</h1>
          {task && (
            <p className="text-sm text-muted-foreground truncate max-w-[400px]">
              {task.prompt}
            </p>
          )}
        </div>
      </div>

      {/* Stages */}
      {isLoading ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
          加载中…
        </div>
      ) : !stages?.length ? (
        <Card>
          <CardContent className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            暂无轨迹数据 — 任务可能还在排队中
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {stages.map((stage) => (
            <TraceStageCard
              key={stage.id}
              stage={stage}
              taskId={taskId!}
              canRedo={
                task?.status === "success" || task?.status === "failed"
              }
            />
          ))}
        </div>
      )}

      {/* Summary */}
      {task?.style_fit_score && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">风格契合度评分</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-4 text-center">
              {(["overall", "layout", "palette", "font"] as const).map((key) => (
                <div key={key}>
                  <div className="text-2xl font-bold">
                    {((task.style_fit_score?.[key] ?? 0) * 100).toFixed(0)}%
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {key === "overall" ? "整体" : key === "layout" ? "布局" : key === "palette" ? "配色" : "字体"}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function TraceStageCard({
  stage,
  taskId,
  canRedo,
}: {
  stage: TraceStage;
  taskId: string;
  canRedo: boolean;
}) {
  const name = stage.stage_name as StageName;
  const label = STAGE_LABELS[name] ?? name;
  const desc = STAGE_DESCRIPTIONS[name] ?? "";

  const StatusIcon =
    stage.status === "success"
      ? CheckCircle2
      : stage.status === "failed"
        ? XCircle
        : stage.status === "running"
          ? Loader2
          : Clock;

  const statusColor =
    stage.status === "success"
      ? "text-green-500"
      : stage.status === "failed"
        ? "text-red-500"
        : stage.status === "running"
          ? "text-blue-500"
          : "text-muted-foreground";

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <StatusIcon
            className={`h-5 w-5 ${statusColor} ${stage.status === "running" ? "animate-spin" : ""}`}
          />
          <span>阶段 {stage.stage_order}：{label}</span>
          {stage.redo_count > 0 && (
            <span className="text-xs text-muted-foreground font-normal">
              (已重做 {stage.redo_count} 次)
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{desc}</p>

        {/* Input/Output summaries */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            <div className="font-medium mb-1">输入</div>
            <div className="rounded bg-muted p-2 text-muted-foreground line-clamp-3">
              {stage.input_summary || "—"}
            </div>
          </div>
          <div>
            <div className="font-medium mb-1">输出</div>
            <div className="rounded bg-muted p-2 text-muted-foreground line-clamp-3">
              {stage.output_summary || "—"}
            </div>
          </div>
        </div>

        {/* Timing + error */}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-3">
            {stage.duration_ms > 0 && (
              <span>耗时 {(stage.duration_ms / 1000).toFixed(1)}s</span>
            )}
            {stage.started_at && (
              <span>
                {new Date(stage.started_at).toLocaleTimeString()}
              </span>
            )}
          </div>
          {canRedo && (
            <RedoButton
              taskId={taskId}
              stageName={stage.stage_name}
              disabled={stage.status === "pending"}
            />
          )}
        </div>

        {stage.error_message && (
          <div className="rounded bg-destructive/10 p-2 text-xs text-destructive">
            {stage.error_message}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
