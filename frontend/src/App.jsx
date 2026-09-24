import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider, useAppContext } from './context/AppContext';

// Layout
import AppShell from './components/layout/AppShell';

// Pages
import Login from './pages/Login';
import AskData from './pages/AskData';
import ConnectData from './pages/ConnectData';
import History from './pages/History';
import Settings from './pages/Settings';

function ProtectedRoute({ children }) {
  const { profile, loading } = useAppContext();
  
  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>Loading...</div>;
  }
  
  if (!profile) {
    return <Navigate to="/login" replace />;
  }
  
  return children;
}

function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          
          <Route element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }>
            <Route path="/" element={<Navigate to="/ask" replace />} />
            <Route path="/ask" element={<AskData />} />
            <Route path="/connect" element={<ConnectData />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  );
}

export default App;
