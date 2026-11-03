import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown } from 'lucide-react';
import './memberRoleDropdown.css';

export default function MemberRoleDropdown({ value, options, label, onChange }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({});
  const trigger = useRef(null);
  const menu = useRef(null);
  const id = useId();
  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };
  const show = () => {
    const rect = trigger.current.getBoundingClientRect();
    const width = Math.max(160, rect.width);
    const height = options.length * 42 + 16;
    setPosition({
      left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)),
      width,
      top:
        rect.bottom + height + 8 > window.innerHeight
          ? Math.max(8, rect.top - height - 6)
          : rect.bottom + 6,
    });
    setOpen(true);
  };
  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector('[aria-selected="true"]')?.focus();
    const dismiss = (event) => {
      if (!menu.current?.contains(event.target) && !trigger.current?.contains(event.target))
        setOpen(false);
    };
    const hide = () => setOpen(false);
    document.addEventListener('pointerdown', dismiss);
    window.addEventListener('resize', hide);
    window.addEventListener('scroll', hide, true);
    return () => {
      document.removeEventListener('pointerdown', dismiss);
      window.removeEventListener('resize', hide);
      window.removeEventListener('scroll', hide, true);
    };
  }, [open]);
  return (
    <>
      <button
        ref={trigger}
        type="button"
        value={value}
        className="workspace-member-role member-role-trigger"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => (open ? close() : show())}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            show();
          }
        }}
      >
        <span>{value}</span>
        <ChevronDown size={15} className={open ? 'is-open' : ''} aria-hidden="true" />
      </button>
      {open &&
        createPortal(
          <div
            ref={menu}
            id={id}
            role="listbox"
            aria-label={label}
            className="member-role-menu"
            style={position}
            onKeyDown={(event) => {
              const items = [...menu.current.querySelectorAll('[role="option"]')];
              const index = items.indexOf(document.activeElement);
              if (event.key === 'Escape') {
                event.preventDefault();
                close();
              }
              if (event.key === 'Tab') setOpen(false);
              if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
                event.preventDefault();
                const next =
                  event.key === 'Home'
                    ? 0
                    : event.key === 'End'
                      ? items.length - 1
                      : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) %
                        items.length;
                items[next]?.focus();
              }
            }}
          >
            {options.map((option) => (
              <button
                key={option}
                type="button"
                role="option"
                aria-selected={option === value}
                onClick={() => {
                  if (option !== value) onChange(option);
                  close();
                }}
              >
                <span>{option}</span>
                {option === value && <Check size={15} aria-hidden="true" />}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}
