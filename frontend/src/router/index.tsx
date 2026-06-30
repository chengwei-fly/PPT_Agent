import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

// Lazy-load pages — keeps initial bundle small.
const GenerationPage = lazy(() => import("@/pages/GenerationPage"));
const KnowledgePage = lazy(() => import("@/pages/KnowledgePage"));
const PreferencesPage = lazy(() => import("@/pages/PreferencesPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const TracePage = lazy(() => import("@/pages/TracePage"));
const SecurityPage = lazy(() => import("@/pages/SecurityPage"));
const DraftListPage = lazy(() => import("@/pages/DraftListPage"));
const DraftEditorPage = lazy(() => import("@/pages/DraftEditorPage"));

const PageFallback = () => (
  <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
    加载中…
  </div>
);

export function AppRouter() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/" element={<Navigate to="/generate" replace />} />
        <Route path="/generate" element={<GenerationPage />} />
        <Route path="/generate/:taskId" element={<GenerationPage />} />
        <Route path="/knowledge" element={<KnowledgePage />} />
        <Route path="/preferences" element={<PreferencesPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/trace/:taskId" element={<TracePage />} />
        <Route path="/security" element={<SecurityPage />} />
        {/* 旧素材库路由 — 已整合进 /knowledge 的"素材资产" Tab */}
        <Route path="/materials" element={<Navigate to="/knowledge" replace />} />
        <Route path="/drafts" element={<DraftListPage />} />
        <Route path="/drafts/:draftId" element={<DraftEditorPage />} />
        <Route path="*" element={<Navigate to="/generate" replace />} />
      </Routes>
    </Suspense>
  );
}
