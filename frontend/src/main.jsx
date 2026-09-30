import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";

/**
 * Application entry point.
 *
 * `StrictMode` is enabled deliberately: it surfaces effects that are not
 * idempotent (double-invoked in development), which is exactly the class of bug
 * that would otherwise appear as duplicate progress heartbeats or double payment
 * requests in production.
 */
const container = document.getElementById("root");

if (!container) {
  throw new Error("Root element #root was not found in index.html.");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
