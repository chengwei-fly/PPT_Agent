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
import { Download, Trash2 } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/services/api";
import { toast } from "sonner";

/** T108: Data lifecycle action buttons (export / delete / archive).
 *
 * Each destructive action requires user confirmation via dialog.
 */

export function DataActions() {
  const [showExportConfirm, setShowExportConfirm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const exportMutation = useMutation({
    mutationFn: () => api.post("/data/export"),
    onSuccess: () => {
      toast.success("导出任务已创建，完成后将通过邮件通知");
      setShowExportConfirm(false);
    },
    onError: (err: Error) => {
      toast.error(`导出失败: ${err.message}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.post("/data/delete-all"),
    onSuccess: () => {
      toast.success("数据删除请求已提交，将在 24 小时内完成");
      setShowDeleteConfirm(false);
    },
    onError: (err: Error) => {
      toast.error(`删除失败: ${err.message}`);
    },
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border p-4">
        <h3 className="text-sm font-medium mb-2">数据导出</h3>
        <p className="text-sm text-muted-foreground mb-3">
          导出所有数据（原始文件、解析结果、偏好设置）为 ZIP 包，包含 SHA-256 校验清单。
        </p>
        <Button
          variant="outline"
          onClick={() => setShowExportConfirm(true)}
          disabled={exportMutation.isPending}
          className="gap-1.5"
        >
          <Download className="h-4 w-4" />
          {exportMutation.isPending ? "导出中..." : "一键导出"}
        </Button>
      </div>

      <div className="rounded-lg border border-destructive/50 p-4">
        <h3 className="text-sm font-medium mb-2 text-destructive">危险操作</h3>
        <p className="text-sm text-muted-foreground mb-3">
          一键删除所有数据。生产库数据将在 24 小时内清除，备份数据将在 7 天内清除。此操作不可撤销。
        </p>
        <Button
          variant="destructive"
          onClick={() => setShowDeleteConfirm(true)}
          disabled={deleteMutation.isPending}
          className="gap-1.5"
        >
          <Trash2 className="h-4 w-4" />
          {deleteMutation.isPending ? "处理中..." : "一键删除所有数据"}
        </Button>
      </div>

      {/* Export confirmation dialog */}
      <Dialog open={showExportConfirm} onOpenChange={setShowExportConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认导出数据</DialogTitle>
            <DialogDescription>
              将导出您的所有数据，包括原始样本文件、解析结果和个人偏好设置。
              导出文件将包含 SHA-256 校验清单以验证数据完整性。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowExportConfirm(false)}
              disabled={exportMutation.isPending}
            >
              取消
            </Button>
            <Button
              onClick={() => exportMutation.mutate()}
              disabled={exportMutation.isPending}
            >
              {exportMutation.isPending ? "导出中..." : "确认导出"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除所有数据</DialogTitle>
            <DialogDescription className="text-destructive">
              此操作将永久删除您的所有数据，包括：
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>所有上传的样本文件</li>
                <li>解析结果和向量索引</li>
                <li>个人偏好设置</li>
                <li>生成任务和轨迹记录</li>
              </ul>
              <p className="mt-2">生产库数据将在 24 小时内清除，备份数据将在 7 天内清除。此操作不可撤销。</p>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDeleteConfirm(false)}
              disabled={deleteMutation.isPending}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "处理中..." : "确认删除所有数据"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
