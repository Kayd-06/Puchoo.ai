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

it('splits the reported run-together questions that start with "Among" after "?"', () => {
  const first =
    "For each month in the last year, which expense category accounted for the largest share of total expenses, and in which months did that category's spending increase even though total monthly expenses decreased from the previous month?";
  const second =
    'Among customers with an unpaid invoice, which have made payments totaling more than half of their total invoiced amount but still owe more than the average outstanding balance of customers in their region? Include partially paid invoices and show how much each customer owes.';
  expect(splitAnalyses(first + second)).toEqual([first, second]);
  expect(splitAnalyses(`${first} ${second}`)).toEqual([first, second]);
});

it('keeps questions that open with "their" or continue with "or" attached', () => {
  expect(splitAnalyses('Which customers owe money? What is their average balance?')).toHaveLength(
    1,
  );
  expect(splitAnalyses('Is revenue up this month? Or is it flat?')).toHaveLength(1);
  expect(splitAnalyses('Show monthly revenue? or by quarter?')).toHaveLength(1);
});
