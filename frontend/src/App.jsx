import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import { AuthProvider } from './context/AuthContext';
import { GuestRoute, ProtectedRoute } from './components/ProtectedRoute';
import SessionPrivacyNotice from './components/SessionPrivacyNotice';

// Keep the marketing page independent from the authenticated product bundle.
// This removes dashboard, database, and workspace code from the first visit.
const AppShell = lazy(() => import('./components/layout/AppShell'));
const Landing = lazy(() => import('./pages/Landing'));
const Login = lazy(() => import('./pages/Login'));
const Signup = lazy(() => import('./pages/Signup'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const Legal = lazy(() => import('./pages/Legal'));
const AskData = lazy(() => import('./pages/AskData'));
const ConnectData = lazy(() => import('./pages/ConnectData'));
const History = lazy(() => import('./pages/History'));
const Settings = lazy(() => import('./pages/Settings'));

function ProductLayout() {
  return (
    <AppProvider>
      <AppShell />
    </AppProvider>
  );
}

// Account pages still verify an existing session so GuestRoute can redirect an
// already signed-in person. The marketing and legal pages stay network-clean.
const sessionFreePaths = new Set(['/', '/privacy', '/terms']);

function RoutedApplication() {
  const { pathname } = useLocation();
  const loadSession = !sessionFreePaths.has(pathname);

  return (
    <AuthProvider key={loadSession ? 'private' : 'public'} loadSession={loadSession}>
        <a className="puchoo-skip-link" href="#main-content">Skip to main content</a>
        <Suspense fallback={<main className="puchoo-route-loading" aria-label="Loading Puchoo.si" />}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route
            path="/login"
            element={
              <GuestRoute>
                <Login />
              </GuestRoute>
            }
          />
          <Route path="/forgot-password" element={<GuestRoute><ForgotPassword /></GuestRoute>} />
          <Route
            path="/signup"
            element={
              <GuestRoute>
                <Signup />
              </GuestRoute>
            }
          />
          <Route path="/app" element={<Navigate to="/ask" replace />} />
          <Route path="/privacy" element={<Legal kind="privacy" />} />
          <Route path="/terms" element={<Legal kind="terms" />} />
          <Route
            element={(
              <ProtectedRoute>
                <ProductLayout />
              </ProtectedRoute>
            )}
          >
            <Route path="/ask" element={<AskData />} />
            <Route path="/connect" element={<ConnectData />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
        <SessionPrivacyNotice />
    </AuthProvider>
  );
}

function App() {
  return <BrowserRouter><RoutedApplication /></BrowserRouter>;
}

export default App;
