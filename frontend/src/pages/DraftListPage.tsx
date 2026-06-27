import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDrafts, useCreateDraft, useDeleteDraft } from "@/hooks/useDrafts";
import { toast } from "sonner";
import { Plus, FileText, Trash2, Edit, Lock, Unlock } from "lucide-react";

const STATUS_LABELS: Record<string, { label: string; className: string }> = {
  active: { label: "编辑中", className: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" },
  archived: { label: "已归档", className: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200" },
  exported: { label: "已导出", className: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" },
};

export default function DraftListPage() {
  const navigate = useNavigate();
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");

  const { data: drafts, isLoading } = useDrafts();
  const createMutation = useCreateDraft();
  const deleteMutation = useDeleteDraft();

  const handleCreate = () => {
    if (!newTitle.trim()) {
      toast.warning("请输入草稿标题");
      return;
    }
    createMutation.mutate(newTitle.trim(), {
      onSuccess: (resp) => {
        toast.success("草稿已创建");
        setShowCreate(false);
        setNewTitle("");
        navigate(`/drafts/${resp.data.id}`);
      },
    });
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">方案草稿</h1>
          <p className="text-sm text-muted-foreground">
            素材复用 + AI 生成 + 手动编辑，一键导出 PPTX
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)} className="gap-1">
          <Plus className="h-3.5 w-3.5" />
          新建草稿
        </Button>
      </div>

      {/* Create dialog */}
      {showCreate && (
        <Card className="border-primary">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">新建草稿</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="输入草稿标题，如：Q3 储能方案"
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => { setShowCreate(false); setNewTitle(""); }}>
                取消
              </Button>
              <Button size="sm" onClick={handleCreate} disabled={createMutation.isPending}>
                {createMutation.isPending ? "创建中…" : "创建"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* List */}
      {isLoading ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
          加载中…
        </div>
      ) : !drafts?.length ? (
        <Card>
          <CardContent className="flex h-48 flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
            <FileText className="h-10 w-10" />
            <p>暂无草稿</p>
            <Button variant="outline" size="sm" onClick={() => setShowCreate(true)}>
              创建第一个草稿
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>标题</TableHead>
                <TableHead className="w-[100px]">状态</TableHead>
                <TableHead className="w-[100px]">锁定</TableHead>
                <TableHead className="w-[120px]">更新时间</TableHead>
                <TableHead className="w-[100px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {drafts.map((draft) => {
                const { label, className } = STATUS_LABELS[draft.status] ?? STATUS_LABELS.active;
                const isLocked = draft.lock_expires_at && new Date(draft.lock_expires_at) > new Date();
                return (
                  <TableRow key={draft.id}>
                    <TableCell>
                      <Link to={`/drafts/${draft.id}`} className="font-medium hover:underline">
                        {draft.title}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
                        {label}
                      </span>
                    </TableCell>
                    <TableCell>
                      {isLocked ? (
                        <span className="flex items-center gap-1 text-xs text-amber-600">
                          <Lock className="h-3 w-3" /> 锁定中
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Unlock className="h-3 w-3" /> 未锁定
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(draft.updated_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => navigate(`/drafts/${draft.id}`)}>
                          <Edit className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => deleteMutation.mutate(draft.id, { onSuccess: () => toast.success("草稿已删除") })}
                          disabled={deleteMutation.isPending}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
