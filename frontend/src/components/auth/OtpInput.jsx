export default function OtpInput({
  value = '',
  onChange,
  error = '',
  disabled = false,
  id = 'verification-code',
  autoFocus = false,
}) {
  const normalized = String(value).replace(/\D/g, '').slice(0, 6);
  const update = (raw) => {
    const next = String(raw).replace(/\D/g, '').slice(0, 6);
    if (next !== normalized) onChange(next);
  };
  return (
    <div className="otp-field">
      <label htmlFor={id}>Verification code</label>
      <div className={`otp-cells${error ? ' has-error' : ''}`}>
        {Array.from({ length: 6 }, (_, index) => (
          <span key={index} aria-hidden="true">
            {normalized[index] || ''}
          </span>
        ))}
        <input
          id={id}
          aria-label="Verification code"
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : undefined}
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete="one-time-code"
          maxLength={12}
          value={normalized}
          onChange={(event) => update(event.target.value)}
          onPaste={(event) => {
            event.preventDefault();
            update(event.clipboardData.getData('text'));
          }}
          disabled={disabled}
          autoFocus={autoFocus}
        />
      </div>
      {error && (
        <p id={`${id}-error`} className="otp-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
