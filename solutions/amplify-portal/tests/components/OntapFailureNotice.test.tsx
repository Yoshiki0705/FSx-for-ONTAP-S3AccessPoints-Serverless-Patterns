import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";

import { OntapFailureNotice } from "../../src/components/OntapFailureNotice";
import { DispatchError, failureDiagnosis } from "../../src/lib/portalQuery";
import { I18nProvider } from "../../src/i18n";
// English, because that is what I18nProvider resolves to under jsdom: there is no
// stored preference and navigator.language is en-US. Asserting on the table rather
// than on literals keeps the wording editable in one place.
import { en } from "../../src/i18n/locales/en";

const renderNotice = (ui: ReactElement) => render(<I18nProvider>{ui}</I18nProvider>);

/**
 * The regression these guard.
 *
 * Every ONTAP panel used to render one block -- "ONTAP connection required", then advice
 * about the VPC, the subnet and the security group -- whatever had actually gone wrong.
 * On the verification environment the cause was a password ONTAP no longer accepted: the
 * request had reached the cluster over TLS and the AWS control plane listed the volume as
 * CREATED, and the panel still sent the reader to inspect subnets. Naming the wrong layer
 * is worse than saying nothing, because the reader believes it.
 */
describe("OntapFailureNotice", () => {
  it("names the credentials, and not the network, when ONTAP rejected the password", () => {
    renderNotice(
      <OntapFailureNotice
        error="User is not authorized."
        errorClass="CREDENTIALS_REJECTED"
        errorStatus={401}
      />
    );

    expect(screen.getByText(en.ontapFailCredentialsTitle)).toBeInTheDocument();
    expect(screen.getByText(en.ontapFailCredentialsStep)).toBeInTheDocument();
    // The reassurance is the point: it stops the detour the guidance used to invite.
    expect(screen.getByText(en.ontapFailReachedOntap, { exact: false })).toBeInTheDocument();
  });

  it("keeps ONTAP's own wording and the status, which is what a support case needs", () => {
    renderNotice(
      <OntapFailureNotice
        error="User is not authorized."
        errorClass="CREDENTIALS_REJECTED"
        errorStatus={401}
        errorCode="6684732"
      />
    );

    const detail = screen.getByText(/User is not authorized\./);
    expect(detail.textContent).toContain("HTTP 401");
    expect(detail.textContent).toContain("6684732");
  });

  it("offers the two commands that repair a rejected password", () => {
    renderNotice(
      <OntapFailureNotice error="User is not authorized." errorClass="CREDENTIALS_REJECTED" />
    );

    const command = screen.getByText(/aws fsx update-file-system/);
    // Resetting the file system's password without writing the same value into the
    // secret leaves the portal exactly as broken, so both halves have to be shown.
    expect(command.textContent).toContain("aws secretsmanager put-secret-value");
  });

  it("does not claim ONTAP was reached when nothing answered on 443", () => {
    renderNotice(<OntapFailureNotice error="timed out" errorClass="UNREACHABLE" />);

    expect(screen.getByText(en.ontapFailUnreachableTitle)).toBeInTheDocument();
    expect(screen.queryByText(en.ontapFailReachedOntap, { exact: false })).not.toBeInTheDocument();
  });

  it("sends an unconfigured deployment to the config file, not to the network", () => {
    renderNotice(<OntapFailureNotice error="ONTAP_MGMT_IP is not set" errorClass="NOT_CONFIGURED" />);

    expect(screen.getByText(en.ontapFailNotConfiguredTitle)).toBeInTheDocument();
    expect(screen.queryByText(en.ontapFailReachedOntap, { exact: false })).not.toBeInTheDocument();
  });

  it("stays general, rather than guessing, when the handler reported no class", () => {
    // An older deployment, or a handler not yet migrated. Guidance that admits it does
    // not know beats guidance that picks one of five causes at random.
    renderNotice(<OntapFailureNotice error="Volume 'vol1' not found" />);

    expect(screen.getByText(en.ontapFailUnknownTitle)).toBeInTheDocument();
    expect(screen.queryByText(en.ontapFailReachedOntap, { exact: false })).not.toBeInTheDocument();
  });

  it("ignores a class it does not recognise instead of rendering an empty heading", () => {
    renderNotice(<OntapFailureNotice error="?" errorClass="SOMETHING_NEWER" />);

    expect(screen.getByText(en.ontapFailUnknownTitle)).toBeInTheDocument();
  });
});

describe("failureDiagnosis", () => {
  it("carries the class through the rejection the panels read", () => {
    const error = new DispatchError("User is not authorized.", {
      errorClass: "CREDENTIALS_REJECTED",
      errorStatus: 401,
      errorCode: "6684732",
    });

    expect(failureDiagnosis(error)).toEqual({
      errorClass: "CREDENTIALS_REJECTED",
      errorStatus: 401,
      errorCode: "6684732",
    });
  });

  it("returns an empty diagnosis for a plain Error, so the caller need not branch", () => {
    expect(failureDiagnosis(new Error("boom"))).toEqual({});
    expect(failureDiagnosis(null)).toEqual({});
  });
});
