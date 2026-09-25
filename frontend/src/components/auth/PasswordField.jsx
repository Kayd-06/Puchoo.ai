import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { focusRing } from '../landing/ui';
import { Field, inputClass } from './AuthShell';

export function passwordIsValid(password) {
  return (
    password.length >= 10 &&
    password.length <= 128 &&
    /[A-Za-z]/.test(password) &&
    /\d/.test(password)
  );
}

export function strengthOf(password) {
  if (!password) return { score: 0, label: '' };
  const checks = [
    password.length >= 10,
    /[A-Za-z]/.test(password),
    /\d/.test(password),
    password.length >= 14 || /[^A-Za-z0-9]/.test(password),
  ];
  const score = checks.filter(Boolean).length;
  return { score, label: ['Too short', 'Weak', 'Fair', 'Good', 'Strong'][score] };
}

export default function PasswordField({ id, label, value, onChange, error, autoComplete }) {
  const [visible, setVisible] = useState(false);
  const strength = strengthOf(value);
  return (
    <Field id={id} label={label} error={error}>
      <div className="relative">
        <input
          id={id}
          name={id}
          type={visible ? 'text' : 'password'}
          autoComplete={autoComplete}
          value={value}
          onChange={onChange}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error ${id}-strength` : `${id}-strength`}
          className={`${inputClass(Boolean(error))} pr-12`}
        />
        <button
          type="button"
          className={`absolute top-1/2 right-3 -translate-y-1/2 rounded-full p-1 text-[#6B7280] ${focusRing}`}
          aria-label={visible ? 'Hide password' : 'Show password'}
          aria-pressed={visible}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? (
            <EyeOff className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Eye className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
      </div>
      <div className="mt-2" id={`${id}-strength`}>
        <div className="flex gap-1" aria-hidden="true">
          {[0, 1, 2, 3].map((segment) => (
            <span
              key={segment}
              className={`h-1 flex-1 rounded-full ${strength.score > segment ? 'bg-[#111827]' : 'bg-black/10'}`}
            />
          ))}
        </div>
        <p className="mt-1 text-xs text-[#6B7280]" aria-live="polite">
          {strength.label
            ? `Password strength: ${strength.label}`
            : 'Use at least 10 characters, with a letter and a number.'}
        </p>
      </div>
    </Field>
  );
}
