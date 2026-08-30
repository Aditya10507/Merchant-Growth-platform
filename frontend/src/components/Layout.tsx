/**
 * Layout.tsx
 * ----------
 * Persistent sidebar shell for the admin panel. Monochrome per
 * FEATURE_3's design tokens — the active nav item is distinguished by
 * fill and a left accent bar, never by color.
 */
import type { ReactNode } from "react";
import { LayoutDashboard, LogOut } from "lucide-react";
import { useAuth } from "../AuthContext";

export function Layout({ children }: { children: ReactNode }) {
  const { session, logout } = useAuth();

  return (
    <div className="flex min-h-screen bg-white">
      {/* Sidebar */}
      <aside className="flex w-56 flex-col bg-gray-900 text-gray-300">
        <div className="border-b border-gray-800 px-4 py-4 text-sm font-semibold text-white">
          Admin Panel
        </div>
        <nav className="flex-1 px-2 py-4">
          <a className="flex items-center gap-2 rounded-md border-l-2 border-white bg-gray-800 px-3 py-2 text-sm font-medium text-white">
            <LayoutDashboard className="h-4 w-4" />
            Applications
          </a>
        </nav>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-gray-200 px-6 py-3">
          <span className="text-sm text-gray-500">{session?.business_name}</span>
          <button onClick={logout} className="flex items-center gap-1 text-sm text-gray-700 hover:text-black">
            <LogOut className="h-4 w-4" /> Log out
          </button>
        </header>
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
