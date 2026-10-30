import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
Object.defineProperty(window, "scrollTo", { value: vi.fn(), writable: true });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

beforeEach(() => vi.stubGlobal("BroadcastChannel", undefined));
afterEach(() => vi.restoreAllMocks());
