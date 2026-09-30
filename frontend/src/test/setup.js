import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

/**
 * Vitest setup.
 *
 * Three environment gaps are patched here; all three are jsdom limitations rather
 * than application problems:
 *
 * 1. **DOM cleanup** between tests, otherwise queries match the previous render.
 * 2. **localStorage** -- jsdom in this environment exposes a partial implementation
 *    without `clear()`, and the token store persists across tests in the same file.
 *    A small in-memory polyfill keeps tests isolated without touching app code.
 * 3. **matchMedia / scrollTo**, which jsdom does not implement at all but the navbar,
 *    toast host and pagination call.
 */

afterEach(() => {
  cleanup();
  try {
    window.localStorage.clear();
  } catch {
    /* the polyfill below owns cleanup */
  }
});

/* -------------------------------------------------------------------------- */
/* localStorage polyfill                                                      */
/* -------------------------------------------------------------------------- */
class MemoryStorage {
  #store = new Map();

  get length() {
    return this.#store.size;
  }

  key(index) {
    return Array.from(this.#store.keys())[index] ?? null;
  }

  getItem(key) {
    return this.#store.has(String(key)) ? this.#store.get(String(key)) : null;
  }

  setItem(key, value) {
    this.#store.set(String(key), String(value));
  }

  removeItem(key) {
    this.#store.delete(String(key));
  }

  clear() {
    this.#store.clear();
  }
}

if (typeof window.localStorage?.clear !== "function") {
  Object.defineProperty(window, "localStorage", {
    writable: true,
    configurable: true,
    value: new MemoryStorage(),
  });
}

/* -------------------------------------------------------------------------- */
/* Missing browser APIs                                                       */
/* -------------------------------------------------------------------------- */
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

window.scrollTo = vi.fn();
