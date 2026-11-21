import "@testing-library/jest-dom/vitest";
import * as matchers from "vitest-axe/matchers";
import { cleanup } from "@testing-library/react";
import { afterEach, expect } from "vitest";

expect.extend(matchers);
afterEach(cleanup);

// jsdom has no <dialog> modal support; emulate the parts the components use.
if (typeof HTMLDialogElement !== "undefined") {
  HTMLDialogElement.prototype.showModal ??= function showModal(
    this: HTMLDialogElement,
  ) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function close(
    this: HTMLDialogElement,
  ) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
      onchange: null,
    }) as MediaQueryList;
}

// axe probes canvas for icon-ligature detection; jsdom has no canvas.
HTMLCanvasElement.prototype.getContext = (() => null) as never;
