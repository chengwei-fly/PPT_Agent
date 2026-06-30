import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { to: "/generate", label: "生成 PPT" },
  { to: "/knowledge", label: "知识库" },
  { to: "/drafts", label: "方案草稿" },
  { to: "/preferences", label: "我的偏好" },
  { to: "/settings", label: "模型设置" },
  { to: "/security", label: "安全事件" },
] as const;

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { userEmail, clear } = useAuthStore();

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="border-b">
        <div className="container flex h-14 items-center justify-between">
          <div className="flex items-center gap-8">
            <h1 className="text-lg font-semibold">PPTagent</h1>
            <nav className="flex items-center gap-1">
              {NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    cn(
                      "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-secondary text-secondary-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            {userEmail && <span>{userEmail}</span>}
            <Button variant="ghost" size="sm" onClick={clear}>
              退出
            </Button>
          </div>
        </div>
      </header>
      <main className="container flex-1 py-6">{children}</main>
    </div>
  );
}
