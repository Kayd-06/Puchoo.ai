import { expect, it } from 'vitest';
import { splitAnalyses } from '../splitAnalyses';
it('separates independent questions even without spaces', () => {
  expect(
    splitAnalyses('Which customers owe money?For each month, which expense category grew?'),
  ).toEqual(['Which customers owe money?', 'For each month, which expense category grew?']);
});
it('keeps dependent follow-ups and individual multi-part questions together', () => {
  expect(
    splitAnalyses(
      'Which region has highest sales? Does its ranking change without its biggest customer?',
    ),
  ).toHaveLength(1);
  expect(splitAnalyses('Which category grew and how much did it contribute?')).toHaveLength(1);
});

it('separates questions with trailing instructions before the next analysis', () => {
  expect(
    splitAnalyses(
      'Which customers owe money? Include partial payments.For each month, which expenses grew?',
    ),
  ).toEqual([
    'Which customers owe money? Include partial payments.',
    'For each month, which expenses grew?',
  ]);
});

it('handles references within the second analysis such as its category and previous month', () => {
  const text =
    'Which customers have unpaid invoices? Show how much each customer owes.For each month in the last year, which expense category accounted for the largest share, and when did that category’s spending increase compared with the previous month?';
  expect(splitAnalyses(text)).toHaveLength(2);
});
