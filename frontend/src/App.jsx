import { BrowserRouter } from "react-router-dom";

import { AuthProvider } from "./context/AuthContext";
import ErrorBoundary from "./components/ErrorBoundary";
import { UIProvider } from "./context/UIContext";
import AppRoutes from "./routes/AppRoutes";

/**
 * Provider composition.
 *
 * Order matters: `UIProvider` reads `isAuthenticated` from `AuthContext` (to poll
 * the unread badge only when signed in), so `AuthProvider` must be the outer one.
 *
 * `ErrorBoundary` sits outside everything so that a failure anywhere below it,
 * including the providers and the router, shows a recovery screen, not a blank page.
 */
export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <UIProvider>
            <AppRoutes />
          </UIProvider>
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
