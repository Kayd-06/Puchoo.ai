// Split only explicit, standalone questions. Keep dependent follow-ups together.
// A new question may start right after "?" even without a space ("month?Among").
const QUESTION_BREAK = /(?<=\?)\s*(?=[A-Za-z])|(?<=\.)\s*(?=for each\b)/i;
// Fragments that continue the previous question instead of starting a new one.
const CONTINUATION_START = /^(?:or|and|but|also|then|else|plus)\b/i;
// References to an earlier answer anywhere in a later part.
const BACK_REFERENCE =
  /\b(it|its|they|them|these|those|above|previous (?:result|answer|question|analysis)|same|that (?:customer|region|result|class))\b/i;
// "their" refers back only when it opens the question, e.g. "What is their average?".
// Later uses ("customers ... in their region") point at the part's own subject.
const LEADING_THEIR = /^(?:\S+\s+){0,3}their\b/i;

export function splitAnalyses(text) {
  const input = text.trim();
  const fragments = input
    .split(QUESTION_BREAK)
    .map((s) => s.trim())
    .filter(Boolean);
  const parts = [];
  for (const fragment of fragments) {
    if (parts.length && (!fragment.endsWith('?') || CONTINUATION_START.test(fragment)))
      parts[parts.length - 1] += ' ' + fragment;
    else parts.push(fragment);
  }
  if (parts.length < 2 || parts.length > 5 || parts.some((part) => !/[?.]$/.test(part)))
    return [input];
  if (
    parts.some(
      (part, index) => index > 0 && (BACK_REFERENCE.test(part) || LEADING_THEIR.test(part)),
    )
  )
    return [input];
  return parts;
}
