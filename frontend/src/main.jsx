import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import './styles/site.css';

const root = createRoot(document.getElementById('root'));
const pageModule = window.location.pathname === '/'
  ? import('./pages/Landing.jsx')
  : import('./App.jsx');

pageModule.then(({ default: Page }) => {
  root.render(<StrictMode><Page /></StrictMode>);
});
