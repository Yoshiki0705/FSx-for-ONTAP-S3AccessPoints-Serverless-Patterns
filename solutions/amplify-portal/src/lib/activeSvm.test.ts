import { beforeEach, describe, expect, it, vi } from "vitest";
import { getActiveSvm, setActiveSvm, subscribeActiveSvm } from "./activeSvm";
import { ACTIONS_ACCEPTING_SVM } from "./dispatchActions";

describe("activeSvm", () => {
  beforeEach(() => setActiveSvm(""));

  it("starts as the backend's default rather than a guessed name", () => {
    expect(getActiveSvm()).toBe("");
  });

  it("notifies subscribers only when the value changes", () => {
    const seen = vi.fn();
    const unsubscribe = subscribeActiveSvm(seen);

    setActiveSvm("svm_a");
    setActiveSvm("svm_a");
    setActiveSvm("svm_b");
    unsubscribe();
    setActiveSvm("svm_c");

    // Two changes while subscribed, and nothing after unsubscribing. Without the
    // equality check `useSyncExternalStore` would re-render on every identical write.
    expect(seen).toHaveBeenCalledTimes(2);
    expect(getActiveSvm()).toBe("svm_c");
  });
});

describe("ACTIONS_ACCEPTING_SVM", () => {
  it("holds the actions that read an SVM and not the ones that cannot", () => {
    // Generated from the handlers, so this is a sanity check on the generation rather
    // than a second list to maintain: an action keyed by UUID has no SVM to scope.
    expect(ACTIONS_ACCEPTING_SVM.has("listVolumes")).toBe(true);
    expect(ACTIONS_ACCEPTING_SVM.has("createQtree")).toBe(true);
    expect(ACTIONS_ACCEPTING_SVM.has("resizeVolume")).toBe(false);
    expect(ACTIONS_ACCEPTING_SVM.has("deleteSnapmirror")).toBe(false);
  });
});
