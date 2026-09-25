import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function SessionGate() {
  return (
    <div className="site grid min-h-screen place-items-center bg-[#F9FAFB] text-[#111827]">
      <p className="text-base">Checking your session…</p>
    </div>
  );
}

export function ProtectedRoute({ children }) {
  const { user, status } = useAuth();
  if (status === 'loading') return <SessionGate />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export function GuestRoute({ children }) {
  const { user, status } = useAuth();
  if (status === 'loading') return <SessionGate />;
  if (user) return <Navigate to="/ask" replace />;
  return children;
}
