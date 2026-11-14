/**
 * Industry processing patterns that the file portal can start.
 *
 * UC1 to UC28 follow the numbering of the industry patterns under
 * `solutions/industry/` in this repository (see the table in the top-level
 * README). A pattern key is `UC<n>_<DIRECTORY_NAME>`, so the directory name,
 * and with it the state machine name `fsxn-s3ap-<directory>-workflow`, can be
 * derived from the key. `amplify/data/resolvers/start-processing.js` does the
 * same derivation on the server side.
 *
 * `amplify/data/resource.ts` lists the same keys in the `ProcessingPattern`
 * enum. `src/lib/industryUseCases.test.ts` fails when the two drift apart.
 */
export const INDUSTRY_USE_CASES = [
  "UC1_LEGAL_COMPLIANCE",
  "UC2_FINANCIAL_IDP",
  "UC3_MANUFACTURING_ANALYTICS",
  "UC4_MEDIA_VFX",
  "UC5_HEALTHCARE_DICOM",
  "UC6_SEMICONDUCTOR_EDA",
  "UC7_GENOMICS_PIPELINE",
  "UC8_ENERGY_SEISMIC",
  "UC9_AUTONOMOUS_DRIVING",
  "UC10_CONSTRUCTION_BIM",
  "UC11_RETAIL_CATALOG",
  "UC12_LOGISTICS_OCR",
  "UC13_EDUCATION_RESEARCH",
  "UC14_INSURANCE_CLAIMS",
  "UC15_DEFENSE_SATELLITE",
  "UC16_GOVERNMENT_ARCHIVES",
  "UC17_SMART_CITY_GEOSPATIAL",
  "UC18_TELECOM_NETWORK_ANALYTICS",
  "UC19_ADTECH_CREATIVE_MANAGEMENT",
  "UC20_TRAVEL_DOCUMENT_PROCESSING",
  "UC21_AGRI_FOOD_TRACEABILITY",
  "UC22_TRANSPORTATION_MAINTENANCE",
  "UC23_SUSTAINABILITY_ESG_REPORTING",
  "UC24_NONPROFIT_GRANT_MANAGEMENT",
  "UC25_UTILITIES_ASSET_INSPECTION",
  "UC26_REAL_ESTATE_PORTFOLIO",
  "UC27_HR_DOCUMENT_SCREENING",
  "UC28_CHEMICAL_SDS_MANAGEMENT",
] as const;

export type IndustryUseCaseKey = (typeof INDUSTRY_USE_CASES)[number];

/** Operations patterns that are not tied to an industry. */
export const OPERATIONS_PATTERNS = ["OPS1_CAPACITY_RIGHTSIZING"] as const;

export type SelectablePattern = IndustryUseCaseKey | (typeof OPERATIONS_PATTERNS)[number];

export const SELECTABLE_PATTERNS: readonly SelectablePattern[] = [
  ...INDUSTRY_USE_CASES,
  ...OPERATIONS_PATTERNS,
];

/** Directory name under `solutions/industry/`, for example `legal-compliance`. */
export function patternSlug(key: string): string | null {
  const match = /^UC\d+_(.+)$/.exec(key);
  return match ? match[1].toLowerCase().replace(/_/g, "-") : null;
}
