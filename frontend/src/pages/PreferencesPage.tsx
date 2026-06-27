import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/services/api";
import type { Preference } from "@/types/api";
import { toast } from "sonner";
import { Trash2, Lock, Unlock } from "lucide-react";
import { LockToggle } from "@/components/generation/LockToggle";

const SCOPE_LABELS: Record<string, string> = {
  cover: "封面",
  toc: "目录",
  body: "正文",
  closing: "结尾",
  all: "全局",
};

export default function PreferencesPage() {
  const queryClient = useQueryClient();

  const { data: preferences, isLoading } = useQuery({
    queryKey: ["preferences"],
    queryFn: () => api.get<Preference[]>("/preferences").then((r) => r.data),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/preferences/${id}`),
    onSuccess: () => {
      toast.success("偏好已删除");
      queryClient.invalidateQueries({ queryKey: ["preferences"] });
    },
  });

  const toggleLockMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      api.patch(`/preferences/${id}`, { is_active: !isActive }),
    onSuccess: () => {
      toast.success("偏好状态已更新");
      queryClient.invalidateQueries({ queryKey: ["preferences"] });
    },
  });

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>我的偏好</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            Agent 会学习您的修改习惯，当同一修改出现 5 次后自动生成偏好规则。偏好会在后续生成中自动应用。
          </p>

          {isLoading ? (
            <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : !preferences?.length ? (
            <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
              暂无偏好 — 多次修改同一类元素后，Agent 会自动提取偏好规则
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[80px]">ID</TableHead>
                  <TableHead>规则</TableHead>
                  <TableHead className="w-[80px]">范围</TableHead>
                  <TableHead className="w-[80px]">状态</TableHead>
                  <TableHead className="w-[80px] text-right">应用次数</TableHead>
                  <TableHead className="w-[80px] text-right">忽略次数</TableHead>
                  <TableHead className="w-[100px]">最后应用</TableHead>
                  <TableHead className="w-[120px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {preferences.map((pref) => (
                  <TableRow key={pref.id}>
                    <TableCell className="font-mono text-xs">{pref.id}</TableCell>
                    <TableCell className="text-sm max-w-[300px] truncate">
                      {pref.rule_text}
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs">
                        {SCOPE_LABELS[pref.applies_to] ?? pref.applies_to}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center gap-1 text-xs ${pref.is_active ? "text-green-600" : "text-muted-foreground"}`}>
                        {pref.is_active ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
                        {pref.is_active ? "已锁定" : "活跃"}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">{pref.apply_count}</TableCell>
                    <TableCell className="text-right">{pref.ignore_count}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {pref.last_applied_at
                        ? new Date(pref.last_applied_at).toLocaleDateString()
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <LockToggle
                          preferenceId={pref.id}
                          isActive={pref.is_active}
                          onToggle={() => toggleLockMutation.mutate({ id: pref.id, isActive: pref.is_active })}
                          disabled={toggleLockMutation.isPending}
                        />
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => deleteMutation.mutate(pref.id)}
                          disabled={deleteMutation.isPending}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
