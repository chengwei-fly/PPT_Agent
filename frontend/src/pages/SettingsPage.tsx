import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/services/api";
import { toast } from "sonner";
import { Plus, Trash2, Key, Star, Settings } from "lucide-react";

interface CredentialSchema {
  provider_type: string;
  schema: Record<string, unknown>;
}

interface Credential {
  id: string;
  provider_type: string;
  name: string;
  is_default: boolean;
  credential_data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  dashscope: "DashScope (通义)",
  deepseek: "DeepSeek",
  gemini: "Gemini",
  moonshot: "Moonshot (月之暗面)",
  ollama: "Ollama (本地)",
  xai: "xAI (Grok)",
  kimi: "Kimi",
};

const PROVIDER_COLORS: Record<string, string> = {
  openai: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  anthropic: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
  dashscope: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  deepseek: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
  gemini: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  moonshot: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200",
  ollama: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200",
  xai: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200",
};

export default function SettingsPage() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);

  const { data: schemas } = useQuery<CredentialSchema[]>({
    queryKey: ["credential-schemas"],
    queryFn: async () => (await api.get<CredentialSchema[]>("/credentials/schemas")).data,
  });

  const { data: credentials, isLoading } = useQuery<Credential[]>({
    queryKey: ["credentials"],
    queryFn: async () => (await api.get<Credential[]>("/credentials")).data,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/credentials/${id}`),
    onSuccess: () => {
      toast.success("凭证已删除");
      qc.invalidateQueries({ queryKey: ["credentials"] });
    },
  });

  const defaultMutation = useMutation({
    mutationFn: ({ id }: { id: string }) =>
      api.put(`/credentials/${id}`, { is_default: true }),
    onSuccess: () => {
      toast.success("已设为默认");
      qc.invalidateQueries({ queryKey: ["credentials"] });
    },
  });

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold flex items-center gap-2">
            <Settings className="h-5 w-5" /> 模型 API 设置
          </h1>
          <p className="text-sm text-muted-foreground">
            管理 LLM 和 Embedding 模型的 API 凭证，支持 OpenAI、Anthropic、DashScope 等多种提供商
          </p>
        </div>
        <Button onClick={() => setShowAdd(true)} className="gap-1">
          <Plus className="h-3.5 w-3.5" /> 添加凭证
        </Button>
      </div>

      {/* Credential list */}
      {isLoading ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">加载中…</div>
      ) : !credentials?.length ? (
        <Card>
          <CardContent className="flex h-48 flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
            <Key className="h-10 w-10" />
            <p>尚未配置任何模型 API 凭证</p>
            <p className="text-xs">添加凭证后即可使用 AI 生成 PPT</p>
            <Button variant="outline" size="sm" onClick={() => setShowAdd(true)}>
              添加第一个凭证
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {credentials.map((cred) => (
            <Card key={cred.id} className={cred.is_default ? "border-primary" : ""}>
              <CardContent className="flex items-center gap-4 py-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                  <Key className="h-5 w-5 text-muted-foreground" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{cred.name || PROVIDER_LABELS[cred.provider_type] || cred.provider_type}</span>
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${PROVIDER_COLORS[cred.provider_type] || "bg-gray-100 text-gray-800"}`}>
                      {PROVIDER_LABELS[cred.provider_type] || cred.provider_type}
                    </span>
                    {cred.is_default && (
                      <span className="inline-flex items-center gap-0.5 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                        <Star className="h-2.5 w-2.5" /> 默认
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {Object.entries(cred.credential_data)
                      .filter(([k]) => k !== "type" && k !== "id")
                      .map(([k, v]) => `${k}: ${String(v).substring(0, 30)}`)
                      .join(" · ")}
                  </div>
                </div>
                <div className="flex gap-1">
                  {!cred.is_default && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => defaultMutation.mutate({ id: cred.id })}
                      title="设为默认"
                    >
                      <Star className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => {
                      if (confirm("确认删除此凭证？")) deleteMutation.mutate(cred.id);
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Add credential dialog */}
      <Dialog open={showAdd} onOpenChange={(open) => { setShowAdd(open); if (!open) setSelectedProvider(null); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>添加模型 API 凭证</DialogTitle>
          </DialogHeader>
          {!selectedProvider ? (
            <ProviderPicker
              schemas={schemas || []}
              onSelect={setSelectedProvider}
            />
          ) : (
            <CredentialForm
              providerType={selectedProvider}
              schema={schemas?.find((s) => s.provider_type === selectedProvider)?.schema}
              onBack={() => setSelectedProvider(null)}
              onDone={() => { setShowAdd(false); setSelectedProvider(null); qc.invalidateQueries({ queryKey: ["credentials"] }); }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ProviderPicker({
  schemas,
  onSelect,
}: {
  schemas: CredentialSchema[];
  onSelect: (provider: string) => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">选择模型提供商：</p>
      <div className="grid grid-cols-2 gap-2">
        {schemas.map((s) => (
          <button
            key={s.provider_type}
            onClick={() => onSelect(s.provider_type)}
            className="flex items-center gap-3 rounded-lg border p-3 text-left transition-colors hover:border-primary hover:bg-muted/50"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded bg-muted text-xs font-bold">
              {(PROVIDER_LABELS[s.provider_type] || s.provider_type).charAt(0)}
            </div>
            <div>
              <div className="text-sm font-medium">
                {PROVIDER_LABELS[s.provider_type] || s.provider_type}
              </div>
              <div className="text-xs text-muted-foreground">
                {s.provider_type}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function CredentialForm({
  providerType,
  schema,
  onBack,
  onDone,
}: {
  providerType: string;
  schema?: Record<string, unknown>;
  onBack: () => void;
  onDone: () => void;
}) {
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [isDefault, setIsDefault] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Parse schema properties
  const properties = (schema?.properties || {}) as Record<string, Record<string, unknown>>;
  const required = (schema?.required || []) as string[];
  const fields = Object.entries(properties).filter(
    ([key]) => key !== "type" && key !== "id" && key !== "name"
  );

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const credentialData: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(formData)) {
        if (value) credentialData[key] = value;
      }
      // Add the type discriminator
      const typeField = properties.type;
      if (typeField?.default) {
        credentialData.type = typeField.default;
      }

      await api.post("/credentials", {
        provider_type: providerType === "openai" ? "openai_credential" : `${providerType}_credential`,
        name: name || PROVIDER_LABELS[providerType] || providerType,
        credential_data: credentialData,
        is_default: isDefault,
      });
      toast.success("凭证已保存");
      onDone();
    } catch {
      // toast by interceptor
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          ← 返回
        </Button>
        <span className="text-sm font-medium">
          {PROVIDER_LABELS[providerType] || providerType}
        </span>
      </div>

      <div className="space-y-3">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">显示名称（可选）</label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={PROVIDER_LABELS[providerType] || providerType}
          />
        </div>

        {fields.map(([key, prop]) => {
          const isSecret = key.toLowerCase().includes("key") || key.toLowerCase().includes("secret") || key.toLowerCase().includes("token");
          const isRequired = required.includes(key);
          const description = (prop.description as string) || key;
          return (
            <div key={key} className="space-y-1">
              <label className="text-xs text-muted-foreground">
                {description}
                {isRequired && <span className="text-destructive ml-1">*</span>}
              </label>
              <Input
                type={isSecret ? "password" : "text"}
                value={formData[key] || ""}
                onChange={(e) => setFormData((prev) => ({ ...prev, [key]: e.target.value }))}
                placeholder={prop.default ? String(prop.default) : key}
              />
            </div>
          );
        })}

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
            className="rounded"
          />
          设为默认凭证
        </label>
      </div>

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onBack}>取消</Button>
        <Button onClick={handleSubmit} disabled={submitting}>
          {submitting ? "保存中…" : "保存凭证"}
        </Button>
      </div>
    </div>
  );
}
