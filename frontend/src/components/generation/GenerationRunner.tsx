import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/services/api";
import { subscribe } from "@/ws/client";
import { useGenerationStore } from "@/stores/generation";
import { QueueIndicator } from "./QueueIndicator";
import type { GenerationTask, TraceStage, StageName, StageStatus } from "@/types/api";
import { toast } from "sonner";

const STAGE_LABELS: Record<StageName, string> = {
  outline: "大纲生成",
  points: "要点提取",
  svg: "SVG 渲染",
  pptx: "PPTX 导出",
};

const STAGE_ORDER: StageName[] = ["outline", "points", "svg", "pptx"];

interface Props {
  taskId: string;
}

export function GenerationRunner({ taskId }: Props) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { appendStageEvent, stagesByTask, setActiveTask } = useGenerationStore();
  const [cancelling, setCancelling] = useState(false);

  // Track active task
  useEffect(() => {
    setActiveTask(taskId);
    return () => setActiveTask(null);
  }, [taskId, setActiveTask]);

  // Fetch task data
  const { data: task, isLoading } = useQuery({
    queryKey: ["generation", taskId],
    queryFn: () => api.get<GenerationTask>(`/generations/${taskId}`).then((r) => r.data),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "success" || status === "failed" || status === "cancelled") return false;
      return 3000;
    },
  });

  // Fetch trace stages
  const { data: traceStages } = useQuery({
    queryKey: ["trace", taskId],
    queryFn: () => api.get<TraceStage[]>(`/generations/${taskId}/trace`).then((r) => r.data),
    enabled: !!task && task.status !== "queued",
    refetchInterval: task?.status === "running" ? 5000 : false,
  });

  // Subscribe to WS events
  useEffect(() => {
    const unsub = subscribe(`task:${taskId}`, (event) => {
      const evtType = event.type as string;
      if (evtType === "task.progress") {
        appendStageEvent(taskId, {
          stage_name: event.stage as StageName,
          status: event.status as StageStatus,
        });
        // Invalidate to refetch latest data
        queryClient.invalidateQueries({ queryKey: ["generation", taskId] });
        queryClient.invalidateQueries({ queryKey: ["trace", taskId] });
      }
      if (evtType === "task.completed" || evtType === "task.failed") {
        queryClient.invalidateQueries({ queryKey: ["generation", taskId] });
        queryClient.invalidateQueries({ queryKey: ["trace", taskId] });
      }
    });
    return unsub;
  }, [taskId, appendStageEvent, queryClient]);

  // Cancel mutation
  const cancelMutation = useMutation({
    mutationFn: () => api.delete(`/generations/${taskId}`),
    onSuccess: () => {
      toast.success("任务已取消");
      queryClient.invalidateQueries({ queryKey: ["generation", taskId] });
    },
    onSettled: () => setCancelling(false),
  });

  const handleCancel = useCallback(() => {
    setCancelling(true);
    cancelMutation.mutate();
  }, [cancelMutation]);

  const handleDownload = useCallback(() => {
    if (task?.result_pptx_path) {
      // Trigger download via presigned URL or direct API
      window.open(`/api/generations/${taskId}/download`, "_blank");
    }
  }, [task, taskId]);

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex h-32 items-center justify-center text-sm text-muted-foreground">
          加载中…
        </CardContent>
      </Card>
    );
  }

  if (!task) {
    return (
      <Card>
        <CardContent className="flex h-32 items-center justify-center text-sm text-destructive">
          任务不存在
        </CardContent>
      </Card>
    );
  }

  // Use server trace stages if available, fallback to WS store
  const stages = traceStages ?? stagesByTask[taskId] ?? [];
  const stagesByName = new Map(stages.map((s) => [s.stage_name, s]));

  return (
    <div className="space-y-4">
      {/* Queue indicator */}
      {task.status === "queued" && task.queue_position != null && (
        <QueueIndicator position={task.queue_position} />
      )}

      {/* Progress card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              生成进度
              {task.mode === "general" && (
                <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                  通用生成
                  {task.visual_style && ` · ${task.visual_style}`}
                </span>
              )}
            </span>
            <StatusBadge status={task.status} />
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Stage timeline */}
          <div className="space-y-2">
            {STAGE_ORDER.map((name, idx) => {
              const stage = stagesByName.get(name);
              const status = stage?.status ?? "pending";
              return (
                <div key={name} className="flex items-center gap-3">
                  <StageIndicator status={status} index={idx + 1} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">{STAGE_LABELS[name]}</div>
                    {stage?.duration_ms ? (
                      <div className="text-xs text-muted-foreground">
                        {(stage.duration_ms / 1000).toFixed(1)}s
                        {stage.redo_count > 0 && ` · 重做 ${stage.redo_count} 次`}
                      </div>
                    ) : null}
                  </div>
                  {status === "failed" && stage?.error_message && (
                    <span className="text-xs text-destructive truncate max-w-[200px]">
                      {stage.error_message}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Token info */}
          {task.token_consumed > 0 && (
            <div className="text-xs text-muted-foreground border-t pt-2">
              已消耗 {task.token_consumed.toLocaleString()} tokens
              {task.estimated_tokens && ` / 预估 ${task.estimated_tokens.toLocaleString()}`}
            </div>
          )}

          {/* Error message */}
          {task.status === "failed" && task.error_message && (
            <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              {task.error_message}
            </div>
          )}

          {/* Style fit score */}
          {task.status === "success" && task.style_fit_score && (
            <div className="rounded-md bg-green-50 dark:bg-green-950 p-3 text-sm">
              <span className="font-medium">风格契合度：</span>
              整体 {(task.style_fit_score.overall * 100).toFixed(0)}%
              （布局 {(task.style_fit_score.layout * 100).toFixed(0)}% ·
              配色 {(task.style_fit_score.palette * 100).toFixed(0)}% ·
              字体 {(task.style_fit_score.font * 100).toFixed(0)}%）
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 border-t pt-3">
            {task.status === "running" && (
              <Button variant="destructive" size="sm" onClick={handleCancel} disabled={cancelling}>
                {cancelling ? "取消中…" : "取消任务"}
              </Button>
            )}
            {task.status === "success" && task.result_pptx_path && (
              <Button size="sm" onClick={handleDownload}>
                下载 PPTX
              </Button>
            )}
            {(task.status === "success" || task.status === "failed") && (
              <Button variant="outline" size="sm" onClick={() => navigate(`/trace/${taskId}`)}>
                查看轨迹
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; className: string }> = {
    queued: { label: "排队中", className: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200" },
    running: { label: "生成中", className: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" },
    success: { label: "已完成", className: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" },
    failed: { label: "失败", className: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200" },
    cancelled: { label: "已取消", className: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200" },
  };
  const { label, className } = config[status] ?? { label: status, className: "" };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {label}
    </span>
  );
}

function StageIndicator({ status, index }: { status: string; index: number }) {
  const base = "flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium";
  const styles: Record<string, string> = {
    pending: `${base} bg-muted text-muted-foreground`,
    running: `${base} bg-blue-500 text-white animate-pulse`,
    success: `${base} bg-green-500 text-white`,
    failed: `${base} bg-red-500 text-white`,
  };
  return (
    <div className={styles[status] ?? styles.pending}>
      {status === "success" ? "✓" : status === "failed" ? "✗" : index}
    </div>
  );
}
