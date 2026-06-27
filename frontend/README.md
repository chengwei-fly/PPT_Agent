# PPTagent Frontend

React 18 + Vite + TypeScript + Tailwind + shadcn/ui — PPTagent MVP web app.

## Quick start

```bash
pnpm install
cp .env.example .env
pnpm dev
```

App runs at http://localhost:5173.

## Scripts

| Script | Purpose |
|--------|---------|
| `pnpm dev` | Start dev server with HMR |
| `pnpm build` | Type-check + production build |
| `pnpm preview` | Preview production build |
| `pnpm lint` | ESLint |
| `pnpm typecheck` | TypeScript only |
| `pnpm test` | Run vitest unit tests |
| `pnpm test:e2e` | Run Playwright E2E |
| `pnpm gen:api` | Regenerate TS client from OpenAPI spec |

## Project structure

```
src/
├── components/
│   ├── ui/             # shadcn/ui primitives
│   ├── generation/     # US1: 一句话输入、进度、下载
│   ├── knowledge/      # US2: 样本管理
│   ├── preferences/    # US3: 我的偏好
│   ├── trace/          # US4: 生成轨迹可视化
│   ├── security/       # US5: 安全事件
│   ├── data_lifecycle/ # US5: 导出/删除
│   └── material/       # US6: 素材库
├── pages/              # 路由级页面
├── services/           # API client (auto-generated)
├── stores/             # Zustand
├── hooks/              # useGeneration, useSamples, etc.
├── router/             # React Router 6
├── ws/                 # WebSocket subscriptions
└── main.tsx
```

## Architecture

- **Data fetching**: SWR + axios (mutations via React Query)
- **State**: Zustand for UI state (queue position, drawer, modals)
- **Forms**: react-hook-form + zod resolvers
- **UI**: shadcn/ui (Radix primitives) + Tailwind CSS
- **Real-time**: native WebSocket (with auto-reconnect)
- **Type safety**: TypeScript + auto-generated API client from OpenAPI
