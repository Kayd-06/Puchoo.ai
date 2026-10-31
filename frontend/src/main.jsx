import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { applyStoredTheme, ThemeProvider } from './context/ThemeContext';
import './index.css';
import './styles/site.css';
import './styles/buttons.css';
import './styles/history.css';

applyStoredTheme();

const root = createRoot(document.getElementById('root'));
const pageModule =
  window.location.pathname === '/' ? import('./pages/Landing.jsx') : import('./App.jsx');

pageModule.then(({ default: Page }) => {
  root.render(
    <StrictMode>
      <ThemeProvider>
        <Page />
      </ThemeProvider>
    </StrictMode>,
  );
});
