/**
 * Why an ONTAP-backed panel has no data, and what to do about it.
 *
 * Every panel used to render the same block: "ONTAP connection required", followed by
 * advice about the VPC subnet, the security group and the management LIF. That block was
 * correct for exactly one of the five ways this can fail.
 *
 * On the verification environment it said that while the real cause was a password ONTAP
 * no longer accepted. The AWS control plane listed the volume as CREATED, the request had
 * reached the cluster over TLS, and the panel sent the reader to go and look at subnets.
 * The backend now classifies the failure (see shared/ontap_diagnosis.py) and this renders
 * the guidance for the class it reports.
 *
 * The heading and the next step are translated. The detail is not: it is ONTAP's own
 * message plus an HTTP status, and it goes in a support case verbatim.
 */
import { useTranslation, type TranslationKeys } from "../i18n";

/** Kept in step with OntapFailure in shared/ontap_diagnosis.py. */
export type OntapErrorClass =
  | "NOT_CONFIGURED"
  | "UNREACHABLE"
  | "CREDENTIALS_REJECTED"
  | "NOT_FOUND"
  | "ONTAP_ERROR";

interface OntapFailureNoticeProps {
  /** ONTAP's own message, or the handler's. Shown verbatim under "error details". */
  error: string;
  /** The class the handler reported. Absent for a panel that has not been migrated yet,
      or for an older deployment, in which case the guidance stays general. */
  errorClass?: string | null;
  /** The HTTP status, when ONTAP answered. */
  errorStatus?: number | null;
  /** ONTAP's error code, which is the first thing a support case asks for. */
  errorCode?: string | null;
}

const HEADINGS: Record<OntapErrorClass, TranslationKeys> = {
  NOT_CONFIGURED: "ontapFailNotConfiguredTitle",
  UNREACHABLE: "ontapFailUnreachableTitle",
  CREDENTIALS_REJECTED: "ontapFailCredentialsTitle",
  NOT_FOUND: "ontapFailNotFoundTitle",
  ONTAP_ERROR: "ontapFailOntapErrorTitle",
};

const NEXT_STEPS: Record<OntapErrorClass, TranslationKeys> = {
  NOT_CONFIGURED: "ontapFailNotConfiguredStep",
  UNREACHABLE: "ontapFailUnreachableStep",
  CREDENTIALS_REJECTED: "ontapFailCredentialsStep",
  NOT_FOUND: "ontapFailNotFoundStep",
  ONTAP_ERROR: "ontapFailOntapErrorStep",
};

/** The classes where the network is demonstrably fine, so saying so saves the reader a
    detour that a colleague already made. */
const REACHED_ONTAP: OntapErrorClass[] = ["CREDENTIALS_REJECTED", "NOT_FOUND", "ONTAP_ERROR"];

/** A command to copy, per class. Not translated: it is shell. */
function commandFor(failure: OntapErrorClass): string | null {
  switch (failure) {
    case "CREDENTIALS_REJECTED":
      return [
        "# 1. Reset the ONTAP admin password on the file system",
        "aws fsx update-file-system --file-system-id <fs-id> \\",
        "  --ontap-configuration FsxAdminPassword='<new-password>'",
        "",
        "# 2. Put the same value in the secret the portal reads",
        "aws secretsmanager put-secret-value --secret-id <secret-name> \\",
        "  --secret-string '{\"username\":\"fsxadmin\",\"password\":\"<new-password>\"}'",
      ].join("\n");
    case "NOT_FOUND":
      return [
        "# What this SVM actually has, by name",
        "aws fsx describe-volumes \\",
        "  --query \"Volumes[?OntapConfiguration.StorageVirtualMachineId=='<svm-id>']\" \\",
        "  --query 'Volumes[].{Name:Name,State:Lifecycle}' --output table",
      ].join("\n");
    case "UNREACHABLE":
      return [
        "# Does the Lambda subnet have a route, and does the SG allow TCP/443?",
        "aws ec2 describe-route-tables \\",
        "  --filters 'Name=association.subnet-id,Values=<subnet-id>'",
      ].join("\n");
    default:
      return null;
  }
}

function isKnown(value: string | null | undefined): value is OntapErrorClass {
  return value === "NOT_CONFIGURED" || value === "UNREACHABLE" || value === "CREDENTIALS_REJECTED" || value === "NOT_FOUND" || value === "ONTAP_ERROR";
}

export function OntapFailureNotice({ error, errorClass, errorStatus, errorCode }: OntapFailureNoticeProps) {
  const { t } = useTranslation();
  const failure: OntapErrorClass | null = isKnown(errorClass) ? errorClass : null;
  const command = failure ? commandFor(failure) : null;

  return (
    <div className="protection-section ontap-failure" style={{ marginTop: "1rem" }}>
      <div className="protection-info">
        <h3>{failure ? t(HEADINGS[failure]) : t("ontapFailUnknownTitle")}</h3>
        <p>{failure ? t(NEXT_STEPS[failure]) : t("ontapFailUnknownStep")}</p>

        {failure && REACHED_ONTAP.includes(failure) && (
          <p className="ontap-failure-reassurance">✅ {t("ontapFailReachedOntap")}</p>
        )}

        {command && (
          <details>
            <summary>{t("ontapFailHowToFix")}</summary>
            <pre className="ontap-failure-command">{command}</pre>
          </details>
        )}

        <details>
          <summary>{t("errorDetails")}</summary>
          <pre className="ontap-failure-detail">
            {error}
            {errorStatus ? `\n\nHTTP ${errorStatus}` : ""}
            {errorCode ? `\nONTAP code ${errorCode}` : ""}
          </pre>
        </details>

        <p className="integration-note">{t("ontapFailPreflightHint")}</p>
      </div>
    </div>
  );
}
