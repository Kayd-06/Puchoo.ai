import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import { AuthProvider } from './context/AuthContext';
import { GuestRoute, ProtectedRoute } from './components/ProtectedRoute';
import AppShell from './components/layout/AppShell';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Signup from './pages/Signup';
import ForgotPassword from './pages/ForgotPassword';
import Legal from './pages/Legal';
import AskData from './pages/AskData';
import ConnectData from './pages/ConnectData';
import History from './pages/History';
import Settings from './pages/Settings';
import CookieNotice from './components/CookieNotice';

function ProductLayout() {
  return (
    <AppProvider>
      <AppShell />
    </AppProvider>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
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
        <CookieNotice />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
