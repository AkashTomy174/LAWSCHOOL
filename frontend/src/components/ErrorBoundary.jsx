import { Component } from "react";

/**
 * Last line of defence against a blank screen.
 *
 * React unmounts the whole tree when a component throws while rendering, which
 * leaves the visitor with an empty page and no way out.  This catches that, shows a
 * plain recovery screen, and logs the real error for developers.  It does not catch
 * errors in event handlers or async code; those are handled where they happen.
 *
 * The fallback deliberately avoids the router, contexts and shared components: any
 * of them may be what broke.  A plain link and a full reload always work.
 */
export default class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    // The user sees no stack trace; this is where it goes instead (dev and
    // production alike).  Forward to a monitoring service from here if one is added.
    console.error("[ErrorBoundary] render failed:", error, info?.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;

    return (
      <div className="ls min-h-dvh">
        <main role="alert" className="wrap flex flex-col items-start gap-6 py-24 lg:py-32">
          <span className="mono cap">Something went wrong</span>
          <h1 className="d2">This page failed to load</h1>
          <p className="lead">
            It is not you, and your progress is safe. Reload to try again, or go back
            to the home page.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <button
              type="button"
              className="btn btn-gold btn-lg"
              onClick={() => window.location.reload()}
            >
              Reload page
            </button>
            <a href="/" className="btn btn-line btn-lg">
              Go to home
            </a>
          </div>
        </main>
      </div>
    );
  }
}
