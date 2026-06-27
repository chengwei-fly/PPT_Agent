import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { RotateCcw } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api";
import { toast } from "sonner";

/** T092: Stage redo button with confirmation dialog.
 *
 * Triggers re-execution of a specific generation stage and all downstream stages.
 * The user must confirm before the redo is initiated.
 */
export interface RedoButtonProps {
  taskId: string;
  stageName: string;
  disabled?: boolean;
}

export function RedoButton({
  taskId,
  stageName,
  disabled = false,
}: RedoButtonProps) {
  const [showConfirm, setShowConfirm] = useState(false);
  const qc = useQueryClient();

  const redoMutation = useMutation({
    mutationFn: () =>
      api.post(`/generations/${taskId}/stages/${stageName}/redo`),
    onSuccess: () => {
      toast.success(`已重新执行 ${stageName} 阶段`);
      qc.invalidateQueries({ queryKey: ["trace", taskId] });
      setShowConfirm(false);
    },
    onError: (err: Error) => {
      toast.error(`重做失败: ${err.message}`);
    },
  });

  const stageLabels: Record<string, string> = {
    outline: "大纲生成",
    points: "要点提取",
    svg: "SVG 渲染",
    pptx: "PPTX 导出",
  };

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setShowConfirm(true)}
        disabled={disabled || redoMutation.isPending}
        className="gap-1.5"
      >
        <RotateCcw className="h-3.5 w-3.5" />
        <span>{redoMutation.isPending ? "执行中..." : "重做"}</span>
      </Button>

      <Dialog open={showConfirm} onOpenChange={setShowConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认重做阶段</DialogTitle>
            <DialogDescription>
              即将重新执行「{stageLabels[stageName] ?? stageName}」阶段及其下游所有阶段。
              上游阶段的输出将被保留，但当前及下游阶段的结果将被重置。
              此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowConfirm(false)}
              disabled={redoMutation.isPending}
            >
              取消
            </Button>
            <Button
              onClick={() => redoMutation.mutate()}
              disabled={redoMutation.isPending}
            >
              {redoMutation.isPending ? "执行中..." : "确认重做"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
