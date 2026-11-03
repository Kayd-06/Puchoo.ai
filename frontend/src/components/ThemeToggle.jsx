import './themeToggle.css';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

export default function ThemeToggle({ className = '' }) {
  const { theme, toggleTheme } = useTheme();
  const nextTheme = theme === 'dark' ? 'light' : 'dark';
  const isDark = theme === 'dark';

  return (
    <button
      type="button"
      className={`theme-toggle theme-switch ${isDark ? 'is-dark' : 'is-light'} ${className}`.trim()}
      aria-label={`Switch to ${nextTheme} mode`}
      aria-pressed={theme === 'light'}
      onClick={toggleTheme}
    >
      <span className="theme-switch-track" aria-hidden="true">
        <Sun className="theme-switch-sun" size={12} />
        <Moon className="theme-switch-moon" size={12} />
      </span>
      <span className="theme-switch-thumb" aria-hidden="true">
        {isDark ? <Moon size={16} /> : <Sun size={16} />}
        {isDark && <span className="theme-switch-star">✦</span>}
      </span>
    </button>
  );
}
