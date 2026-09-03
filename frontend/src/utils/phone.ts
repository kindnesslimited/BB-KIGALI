/**
 * Strict E.164 phone normalizer used everywhere we send a phone to the
 * backend. Kept identical to `_canonicalize_phone` in server.py so the same
 * user record matches whether they typed the number as '+250 794 230 137',
 * '250794230137', or '(250) 794-230-137'.
 *
 * Always returns a leading '+' when there are digits. Empty in → empty out.
 */
export function toE164(raw: string | null | undefined): string {
  if (!raw) return "";
  const s = String(raw).trim();
  let digits = s.replace(/\D/g, "");
  if (!digits) return "";
  // '00' international prefix → strip
  if (digits.startsWith("00")) digits = digits.slice(2);
  return "+" + digits;
}

/** Loose validator — used to gate the "Continue" button on the phone screen. */
export function isLikelyE164(raw: string): boolean {
  const normalized = toE164(raw);
  const digits = normalized.replace(/\D/g, "");
  return digits.length >= 9 && digits.length <= 15;
}
