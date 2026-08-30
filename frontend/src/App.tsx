/**
 * App.tsx
 * -------
 * Top-level routing decision based on authentication and user role:
 *   - No session → AuthPage
 *   - Reviewer/admin role → AdminPage
 *   - Merchant role → DashboardPage
 *
 * The MVP has a linear flow per role (see UI/UX doc), so a full router
 * library is unnecessary complexity — this simple conditional is enough.
 */

import { AuthProvider, useAuth } from "./AuthContext";
import { AuthPage } from "./pages/AuthPage";
import { DashboardPage } from "./pages/DashboardPage";
import { AdminPage } from "./pages/AdminPage";

function AppContent() {
  const { session } = useAuth();
  if (!session) return <AuthPage />;
  if (session.role === "reviewer" || session.role === "admin") return <AdminPage />;
  return <DashboardPage />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
