import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

import OtpInput from '../OtpInput';

function Harness({ onComplete = vi.fn(), ...props }) {
  const [value, setValue] = useState('');
  return (
    <OtpInput
      id="otp"
      value={value}
      onChange={(next) => {
        setValue(next);
        if (next.length === 6) onComplete(next);
      }}
      {...props}
    />
  );
}

it('normalizes typing and paste to six digits and completes once', () => {
  const onComplete = vi.fn();
  render(<Harness onComplete={onComplete} />);
  const input = screen.getByLabelText('Verification code');
  fireEvent.change(input, { target: { value: ' 12a 3456 ' } });
  expect(input).toHaveValue('123456');
  expect(onComplete).toHaveBeenCalledTimes(1);
  fireEvent.change(input, { target: { value: '123456' } });
  expect(onComplete).toHaveBeenCalledTimes(1);
  fireEvent.change(input, { target: { value: '12345' } });
  expect(input).toHaveValue('12345');
});

it('associates errors and supports disabled state', () => {
  render(<Harness error="That code expired." disabled />);
  const input = screen.getByLabelText('Verification code');
  expect(input).toBeDisabled();
  expect(input).toHaveAttribute('aria-describedby', 'otp-error');
  expect(screen.getByRole('alert')).toHaveTextContent('That code expired.');
});
