/**
 * Whether a path is in a folder whose contents must not be sent to a managed
 * AI service.
 *
 * The predicate lived inside FileExplorer, which was fine while the folder
 * processing button was the only thing it guarded. Textract and Comprehend send
 * document contents to a service too, so a second copy would have been a second
 * definition of the same boundary — and the two could disagree after an edit to
 * either. One definition, used by both.
 *
 * This is a convenience guard in the UI, not the enforcement point: the folder
 * naming convention is a hint, and a deployment that must guarantee the boundary
 * enforces it with IAM and the group path prefixes, not with a regex.
 *
 * The endpoints enforce the same convention themselves, because hiding a button
 * does not stop a call to AppSync. `shared/portal_regulated_path.py` is the Python
 * half, imported by every endpoint that hands file contents to a managed AI
 * service, and `shared/tests/test_portal_regulated_path.py` asserts the pattern
 * and the roots below still match it -- an edit here has to be an edit there.
 */
const REGULATED_SEGMENT = /\/(dicom|phi|pii|hipaa|protected-health)[/-]/;
const REGULATED_ROOTS = ["dicom/", "phi/", "pii/"];

export function isRegulatedPath(path: string): boolean {
  const lower = path.toLowerCase();
  return (
    REGULATED_SEGMENT.test(`/${lower}`) ||
    REGULATED_ROOTS.some((root) => lower.startsWith(root))
  );
}
