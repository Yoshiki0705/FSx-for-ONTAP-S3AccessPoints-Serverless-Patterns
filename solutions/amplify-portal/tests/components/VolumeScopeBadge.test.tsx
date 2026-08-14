import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { VolumeScopeBadge } from "../../src/components/VolumeScopeBadge";
import { I18nProvider } from "../../src/i18n";

/**
 * The badge answers "why this volume", not just "which one". Before a pick, the name on
 * screen is the deployment's configured volume — and a reader who has not chosen
 * anything has no way to know that from a name alone.
 */
const renderBadge = (props: { volumeName: string; isDefault: boolean }) =>
  render(
    <I18nProvider>
      <VolumeScopeBadge {...props} />
    </I18nProvider>,
  );

describe("VolumeScopeBadge", () => {
  it("says the volume is the default one when nothing has been picked", () => {
    renderBadge({ volumeName: "vol1", isDefault: true });

    expect(screen.getByText("vol1")).toBeTruthy();
    expect(screen.getByText("default")).toBeTruthy();
    // The muted styling is the other half of the distinction, so the class carrying it
    // is part of the contract with the stylesheet.
    expect(document.querySelector(".volume-badge-default")).toBeTruthy();
  });

  it("drops the qualifier once a volume has been picked", () => {
    renderBadge({ volumeName: "iot_data", isDefault: false });

    expect(screen.getByText("iot_data")).toBeTruthy();
    expect(screen.queryByText("default")).toBeNull();
    expect(document.querySelector(".volume-badge-default")).toBeNull();
  });

  it("renders nothing without a volume, rather than a label with an empty value", () => {
    const { container } = renderBadge({ volumeName: "", isDefault: true });

    expect(container.querySelector(".volume-badge")).toBeNull();
  });
});
