import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

class TestResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver = TestResizeObserver;
afterEach(() => cleanup());
