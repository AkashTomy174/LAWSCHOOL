import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ErrorBoundary from "./ErrorBoundary";

function Boom() {
  throw new Error("kaboom: secret internal detail");
}

describe("ErrorBoundary", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>All good</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("All good")).toBeInTheDocument();
  });

  it("catches a throwing child, offers a way out and hides the details", () => {
    // React logs caught render errors itself; silence that and watch ours.
    const log = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "This page failed to load" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload page" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to home" })).toHaveAttribute("href", "/");

    // Nothing technical reaches the user...
    expect(document.body).not.toHaveTextContent("kaboom");
    // ...but the developer gets the real error.
    const ours = log.mock.calls.find(([tag]) => tag === "[ErrorBoundary] render failed:");
    expect(ours?.[1]).toBeInstanceOf(Error);
    expect(ours?.[1].message).toMatch("kaboom");
  });

  it("reloads the page from the fallback", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const reload = vi.fn();
    vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, reload });

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    screen.getByRole("button", { name: "Reload page" }).click();
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
