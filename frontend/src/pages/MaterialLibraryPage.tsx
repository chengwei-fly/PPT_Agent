import { useState, useCallback } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/services/api";
import { useMaterials, useMaterial } from "@/hooks/useMaterials";
import { MaterialDetailDrawer } from "@/components/material/MaterialDetailDrawer";
import type { SlideAsset } from "@/types/api";
import { toast } from "sonner";
import { Search, Image, Filter, X } from "lucide-react";

const VISUAL_TYPES = [
  { value: "cover", label: "封面" },
  { value: "toc", label: "目录" },
  { value: "architecture", label: "架构图" },
  { value: "flowchart", label: "流程图" },
  { value: "data", label: "数据页" },
  { value: "body", label: "正文页" },
  { value: "closing", label: "结尾页" },
  { value: "mixed", label: "综合页" },
];

export default function MaterialLibraryPage() {
  const [query, setQuery] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [selectedAsset, setSelectedAsset] = useState<SlideAsset | null>(null);
  const { data, isLoading } = useMaterials({
    q: query || undefined,
    visual_types: selectedTypes.length > 0 ? selectedTypes : undefined,
  });

  // Fetch full detail (with svg_payload) when an asset is selected
  const { data: fullDetail } = useMaterial(selectedAsset?.id ?? "");

  const insertMutation = useMutation({
    mutationFn: (assetId: string) => api.post(`/materials/${assetId}/insert`),
    onSuccess: () => {
      toast.success("已插入草稿");
    },
  });

  const toggleType = useCallback((type: string) => {
    setSelectedTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  }, []);

  const clearFilters = useCallback(() => {
    setQuery("");
    setSelectedTypes([]);
  }, []);

  const assets = data?.items ?? [];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">素材库</h1>
          <p className="text-sm text-muted-foreground">
            从历史 PPT 抽取的单页素材，按类型、行业、关键词检索
          </p>
        </div>
        {data && (
          <span className="text-xs text-muted-foreground">
            {data.total} 个素材 · {data.duration_ms}ms
          </span>
        )}
      </div>

      {/* Search + Filters */}
      <Card>
        <CardContent className="space-y-3 pt-4">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索素材标题、内容…"
                className="pl-9"
              />
            </div>
            {(query || selectedTypes.length > 0) && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="h-3.5 w-3.5 mr-1" />
                清除
              </Button>
            )}
          </div>

          {/* Visual type filters */}
          <div className="flex flex-wrap gap-2">
            <Filter className="h-4 w-4 text-muted-foreground mt-0.5" />
            {VISUAL_TYPES.map(({ value, label }) => (
              <Button
                key={value}
                variant={selectedTypes.includes(value) ? "default" : "outline"}
                size="sm"
                className="h-7"
                onClick={() => toggleType(value)}
              >
                {label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Grid */}
      {isLoading ? (
        <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
          加载中…
        </div>
      ) : assets.length === 0 ? (
        <Card>
          <CardContent className="flex h-64 flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
            <Image className="h-10 w-10" />
            <p>暂无素材 — 上传 PPT 样本后，系统会自动抽取单页素材</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {assets.map((asset) => (
            <MaterialCard
              key={asset.id}
              asset={asset}
              onClick={() => setSelectedAsset(asset)}
            />
          ))}
        </div>
      )}

      {/* Detail drawer — use full detail (with SVG) when available */}
      <MaterialDetailDrawer
        asset={fullDetail ?? selectedAsset}
        onClose={() => setSelectedAsset(null)}
        onInsert={(id) => insertMutation.mutate(id)}
      />
    </div>
  );
}

function MaterialCard({ asset, onClick }: { asset: SlideAsset; onClick: () => void }) {
  const typeLabels: Record<string, string> = {
    cover: "封面", toc: "目录", architecture: "架构", flowchart: "流程",
    data: "数据", body: "正文", closing: "结尾", mixed: "综合",
  };

  return (
    <button
      onClick={onClick}
      className="group relative overflow-hidden rounded-lg border bg-card text-left transition-all hover:shadow-md hover:border-primary/50"
    >
      {/* Thumbnail */}
      <div className="aspect-[4/3] bg-muted flex items-center justify-center overflow-hidden">
        {asset.thumbnail_path ? (
          <img
            src={asset.thumbnail_path}
            alt={asset.title ?? ""}
            className="h-full w-full object-cover transition-transform group-hover:scale-105"
          />
        ) : (
          <Image className="h-8 w-8 text-muted-foreground" />
        )}
      </div>

      {/* Info */}
      <div className="p-2">
        <div className="text-xs font-medium truncate">
          {asset.title ?? `第 ${asset.page_index + 1} 页`}
        </div>
        <div className="mt-1 flex items-center gap-1">
          <span className="inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 text-[10px]">
            {typeLabels[asset.visual_type] ?? asset.visual_type}
          </span>
          {asset.color_palette.length > 0 && (
            <div className="flex gap-0.5">
              {asset.color_palette.slice(0, 3).map((c, i) => (
                <div
                  key={i}
                  className="h-2.5 w-2.5 rounded-full border"
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}
