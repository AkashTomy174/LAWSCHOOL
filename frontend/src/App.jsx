import { BrowserRouter } from "react-router-dom";

import { AuthProvider } from "./context/AuthContext";
import { UIProvider } from "./context/UIContext";
import AppRoutes from "./routes/AppRoutes";

/**
 * Provider composition.
 *
 * Order matters: `UIProvider` reads `isAuthenticated` from `AuthContext` (to poll
 * the unread badge only when signed in), so `AuthProvider` must be the outer one.
 */
export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <UIProvider>
          <AppRoutes />
        </UIProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
