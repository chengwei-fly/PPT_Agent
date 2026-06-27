import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/services/api";
import type { SlideAsset } from "@/types/api";
import { toast } from "sonner";
import { X, Plus, Trash2, Image, Code2 } from "lucide-react";

const VISUAL_TYPE_LABELS: Record<string, string> = {
  cover: "封面",
  toc: "目录",
  architecture: "架构图",
  flowchart: "流程图",
  data: "数据页",
  body: "正文页",
  closing: "结尾页",
  mixed: "综合页",
};

interface Props {
  asset: SlideAsset | null;
  onClose: () => void;
  onInsert?: (assetId: string) => void;
}

export function MaterialDetailDrawer({ asset, onClose, onInsert }: Props) {
  const queryClient = useQueryClient();
  const [showSvg, setShowSvg] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/materials/${id}`),
    onSuccess: () => {
      toast.success("素材已删除");
      queryClient.invalidateQueries({ queryKey: ["materials"] });
      onClose();
    },
  });

  if (!asset) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />

      {/* Drawer */}
      <div className="relative w-full max-w-md bg-background shadow-xl overflow-y-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-background p-4">
          <h2 className="text-lg font-semibold">素材详情</h2>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-4 p-4">
          {/* Thumbnail / SVG toggle */}
          {asset.svg_payload && (
            <div className="flex gap-1 mb-2">
              <Button
                variant={!showSvg ? "secondary" : "ghost"}
                size="sm"
                className="text-xs"
                onClick={() => setShowSvg(false)}
              >
                <Image className="h-3 w-3 mr-1" /> 缩略图
              </Button>
              <Button
                variant={showSvg ? "secondary" : "ghost"}
                size="sm"
                className="text-xs"
                onClick={() => setShowSvg(true)}
              >
                <Code2 className="h-3 w-3 mr-1" /> SVG 预览
              </Button>
            </div>
          )}
          <div className="aspect-video rounded-lg border bg-muted flex items-center justify-center overflow-hidden">
            {showSvg && asset.svg_payload ? (
              <div
                className="h-full w-full bg-white"
                dangerouslySetInnerHTML={{ __html: asset.svg_payload }}
              />
            ) : asset.thumbnail_path ? (
              <img
                src={asset.thumbnail_path}
                alt={asset.title ?? "素材缩略图"}
                className="h-full w-full object-contain"
              />
            ) : (
              <Image className="h-12 w-12 text-muted-foreground" />
            )}
          </div>

          {/* Metadata */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">基本信息</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">标题</span>
                <span>{asset.title ?? "—"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">类型</span>
                <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs">
                  {VISUAL_TYPE_LABELS[asset.visual_type] ?? asset.visual_type}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">页码</span>
                <span>第 {asset.page_index + 1} 页</span>
              </div>
              {asset.font_family && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">字体</span>
                  <span>{asset.font_family}</span>
                </div>
              )}
              {asset.color_palette.length > 0 && (
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">配色</span>
                  <div className="flex gap-1">
                    {asset.color_palette.slice(0, 6).map((c, i) => (
                      <div
                        key={i}
                        className="h-4 w-4 rounded-full border"
                        style={{ backgroundColor: c }}
                        title={c}
                      />
                    ))}
                  </div>
                </div>
              )}
              {asset.industry_tags.length > 0 && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">行业标签</span>
                  <div className="flex gap-1">
                    {asset.industry_tags.map((tag) => (
                      <span key={tag} className="rounded bg-muted px-1.5 py-0.5 text-xs">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Body text preview */}
          {asset.body_text && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">文本内容</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground line-clamp-8 whitespace-pre-wrap">
                  {asset.body_text}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            {onInsert && (
              <Button className="flex-1 gap-1" onClick={() => onInsert(asset.id)}>
                <Plus className="h-3.5 w-3.5" />
                插入草稿
              </Button>
            )}
            <Button
              variant="destructive"
              size="icon"
              onClick={() => deleteMutation.mutate(asset.id)}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
