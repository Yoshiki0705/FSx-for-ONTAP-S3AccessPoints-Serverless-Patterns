import { useState } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

type ProcessingPattern =
  | "UC1_LEGAL_COMPLIANCE"
  | "UC3_HEALTHCARE_IMAGING"
  | "UC6_SEMICONDUCTOR_EDA"
  | "UC10_MEDIA_PRODUCTION"
  | "UC15_MANUFACTURING_QC"
  | "OPS1_CAPACITY_RIGHTSIZING";

interface JobSubmitFormProps {
  initialPrefix: string;
  onJobStarted: (executionArn: string) => void;
}

const PATTERN_DESCRIPTIONS: Record<ProcessingPattern, string> = {
  UC1_LEGAL_COMPLIANCE: "Legal document classification and compliance check",
  UC3_HEALTHCARE_IMAGING: "Medical imaging analysis and DICOM processing",
  UC6_SEMICONDUCTOR_EDA: "EDA file validation and design rule check",
  UC10_MEDIA_PRODUCTION: "Media asset transcoding and metadata extraction",
  UC15_MANUFACTURING_QC: "Manufacturing quality control image inspection",
  OPS1_CAPACITY_RIGHTSIZING: "Volume capacity analysis and recommendations",
};

/**
 * Job submission form.
 *
 * Allows users to:
 * - Select a processing pattern (UC1-UC28, OPS1-OPS6)
 * - Specify input prefix (pre-filled from FileExplorer)
 * - Add optional parameters
 * - Submit and trigger Step Functions execution
 */
export function JobSubmitForm({ initialPrefix, onJobStarted }: JobSubmitFormProps) {
  const [prefix, setPrefix] = useState(initialPrefix);
  const [pattern, setPattern] = useState<ProcessingPattern>("UC1_LEGAL_COMPLIANCE");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await client.mutations.startProcessing({
        pattern,
        inputPrefix: prefix,
        parameters: JSON.stringify({
          submittedAt: new Date().toISOString(),
          source: "amplify-portal",
        }),
      });

      if (response.data?.executionArn) {
        setSuccess(`Job started: ${response.data.executionArn}`);
        onJobStarted(response.data.executionArn);
      } else if (response.errors) {
        setError(response.errors.map((e) => e.message).join(", "));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start processing");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="job-submit-form">
      <h2>Start Processing Job</h2>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="pattern">Processing Pattern</label>
          <select
            id="pattern"
            value={pattern}
            onChange={(e) => setPattern(e.target.value as ProcessingPattern)}
          >
            {Object.entries(PATTERN_DESCRIPTIONS).map(([key, desc]) => (
              <option key={key} value={key}>
                {key.replace(/_/g, " ")} — {desc}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="prefix">Input Prefix (S3 AP path)</label>
          <input
            id="prefix"
            type="text"
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
            placeholder="e.g., documents/contracts/2024/"
          />
          <small>
            Files under this prefix will be processed by the selected pattern.
          </small>
        </div>

        {error && <div className="error-message">{error}</div>}
        {success && <div className="success-message">{success}</div>}

        <button type="submit" disabled={submitting || !prefix}>
          {submitting ? "Starting..." : "Start Processing"}
        </button>
      </form>
    </div>
  );
}
