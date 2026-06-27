import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import type { SecurityEvent } from "@/types/api";
import { Shield, AlertTriangle, ChevronLeft, ChevronRight } from "lucide-react";
import { DataActions } from "@/components/data_lifecycle/DataActions";

const EVENT_TYPE_LABELS: Record<string, string> = {
  pii_hit: "PII 命中",
  pii_blocked: "PII 拦截",
  pii_replaced: "PII 替换",
  pii_acknowledged: "PII 确认",
  unauth_access: "未授权访问",
  bulk_export: "批量导出",
  bulk_delete: "批量删除",
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  pii_hit: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  pii_blocked: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  pii_replaced: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  pii_acknowledged: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  unauth_access: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  bulk_export: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
  bulk_delete: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const ACTION_LABELS: Record<string, string> = {
  replace: "已替换",
  block: "已拦截",
  allow: "已放行",
};

export default function SecurityPage() {
  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([]);
  const [filterType, setFilterType] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["security-events", cursor, filterType],
    queryFn: () => {
      const params = new URLSearchParams();
      if (cursor) params.set("cursor", cursor);
      params.set("limit", "20");
      if (filterType) params.set("event_type", filterType);
      return api.get<{ items: SecurityEvent[]; next_cursor: string | null; has_more: boolean }>(
        `/security/events?${params.toString()}`,
      ).then((r) => r.data);
    },
  });

  const goNext = () => {
    if (data?.next_cursor) {
      setCursorHistory((h) => [...h, cursor]);
      setCursor(data.next_cursor);
    }
  };

  const goPrev = () => {
    setCursorHistory((h) => {
      const prev = h[h.length - 1];
      setCursor(prev ?? null);
      return h.slice(0, -1);
    });
  };

  const eventTypes = Object.keys(EVENT_TYPE_LABELS);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            安全事件
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Filters */}
          <div className="flex flex-wrap gap-2">
            <Button
              variant={filterType === null ? "default" : "outline"}
              size="sm"
              onClick={() => { setFilterType(null); setCursor(null); setCursorHistory([]); }}
            >
              全部
            </Button>
            {eventTypes.map((t) => (
              <Button
                key={t}
                variant={filterType === t ? "default" : "outline"}
                size="sm"
                onClick={() => { setFilterType(t); setCursor(null); setCursorHistory([]); }}
              >
                {EVENT_TYPE_LABELS[t]}
              </Button>
            ))}
          </div>

          {/* Data actions */}
          <div className="border-b pb-3">
            <DataActions />
          </div>

          {/* Table */}
          {isLoading ? (
            <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : !data?.items?.length ? (
            <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
              <AlertTriangle className="mr-2 h-4 w-4" />
              暂无安全事件
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[120px]">类型</TableHead>
                    <TableHead>命中字段</TableHead>
                    <TableHead className="w-[80px]">处置</TableHead>
                    <TableHead className="w-[160px]">时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((evt) => (
                    <TableRow key={evt.id}>
                      <TableCell>
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                            EVENT_TYPE_COLORS[evt.event_type] ?? ""
                          }`}
                        >
                          {EVENT_TYPE_LABELS[evt.event_type] ?? evt.event_type}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm font-mono">
                        {evt.hit_field ?? "—"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {ACTION_LABELS[evt.action_taken] ?? evt.action_taken}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(evt.created_at).toLocaleString()}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              <div className="flex items-center justify-between pt-2">
                <div className="text-xs text-muted-foreground">
                  {data.items.length} 条记录
                </div>
                <div className="flex gap-1">
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-7 w-7"
                    onClick={goPrev}
                    disabled={cursorHistory.length === 0}
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-7 w-7"
                    onClick={goNext}
                    disabled={!data.has_more}
                  >
                    <ChevronRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
