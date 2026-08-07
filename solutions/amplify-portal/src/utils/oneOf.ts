/**
 * Narrow a value that came from the DOM back to the set an action accepts.
 *
 * A `<select>` hands back a `string` however few options it has, so a form bound to
 * an action's enumerated parameter loses the type between the markup and the call.
 * Widening the state to `string` to make that compile is what let `snaplockType`
 * reach ONTAP misspelled, where it produced a volume with no SnapLock rather than an
 * error.
 *
 * The fallback is required rather than optional: there is no sensible default for
 * "the operator chose something impossible", and choosing one silently is how the
 * wrong value travels.
 *
 * @example
 * onChange={(e) => setStyle(oneOf(["unix", "ntfs", "mixed"], e.target.value, "unix"))}
 */
export function oneOf<const T extends readonly string[]>(
  allowed: T,
  value: string,
  fallback: T[number]
): T[number] {
  return (allowed as readonly string[]).includes(value) ? (value as T[number]) : fallback;
}
