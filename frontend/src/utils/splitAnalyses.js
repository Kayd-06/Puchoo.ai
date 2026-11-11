// Split only explicit, standalone questions. Keep dependent follow-ups together.
export function splitAnalyses(text) {
  const input = text.trim();
  const fragments = input
    .split(
      /(?:(?<=\?)\s*(?=(?:which|what|who|how|for each|show|list|compare|do |does |did |are |is )\b)|(?<=\.)\s*(?=for each\b))/i,
    )
    .map((s) => s.trim())
    .filter(Boolean);
  const parts = [];
  for (const fragment of fragments) {
    if (parts.length && !fragment.endsWith('?')) parts[parts.length - 1] += ' ' + fragment;
    else parts.push(fragment);
  }
  if (parts.length < 2 || parts.length > 5 || parts.some((part) => !/[?.]$/.test(part)))
    return [input];
  if (
    parts.some(
      (part, index) =>
        index > 0 &&
        /\b(it|its|they|their|these|those|above|previous (?:result|answer|question|analysis)|same|that (?:customer|region|result|class))\b/i.test(
          part,
        ),
    )
  )
    return [input];
  return parts;
}
