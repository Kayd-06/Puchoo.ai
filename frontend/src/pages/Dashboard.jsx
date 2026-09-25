import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mark, PillButton, focusRing } from '../components/landing/ui';
import { useAuth } from '../context/AuthContext';

function workspaceLabel(user) {
  if (user.workspace_type === 'institute') return user.institute_name || 'Institute members';
  return 'Personal';
}

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const [toast, setToast] = useState('');

  async function onLogout() {
    setPending(true);
    try {
      navigate('/');
      await logout();
    } catch (error) {
      setToast(error.message || 'Unable to log out.');
      setPending(false);
    }
  }

  if (!user) return null;

  return (
    <div className="site min-h-screen bg-[#F9FAFB] text-[#111827]">
      <title>Workspace · Puchoo.ai</title>
      <header className="flex items-center justify-between px-5 py-5 md:px-10">
        <Link
          to="/"
          className={`flex items-center gap-2 font-medium tracking-[-0.03em] ${focusRing} rounded-full`}
        >
          <Mark className="h-6 w-6" />
          Puchoo.ai
        </Link>
        <PillButton variant="dark" onClick={onLogout} disabled={pending}>
          {pending ? 'Logging out…' : 'Log out'}
        </PillButton>
      </header>
      <main className="mx-auto max-w-3xl px-5 py-16 md:px-10">
        <p className="text-sm text-[#6B7280]">Workspace</p>
        <h1 className="mt-3 text-[clamp(40px,6vw,64px)] leading-[1.02] font-medium tracking-[-0.04em]">
          Welcome, {user.full_name}
        </h1>
        <p className="mt-6 inline-flex rounded-full bg-[#111827] px-4 py-2 text-sm text-white">
          {workspaceLabel(user)}
        </p>
        <p className="mt-8 max-w-xl text-[17px] leading-relaxed text-[#6B7280]">
          Ask a question in your language, review the SQL, and approve it before anything runs. The
          analytics workspace is ready when you are.
        </p>
        <Link
          to="/ask"
          className={`mt-6 inline-flex text-sm text-[#111827] underline-offset-4 hover:underline ${focusRing} rounded-full`}
        >
          Open the analytics workspace
        </Link>
      </main>
      {toast ? (
        <div
          role="alert"
          className="fixed right-4 bottom-4 z-50 max-w-sm rounded-2xl bg-[#111827] px-4 py-3 text-sm text-white"
        >
          {toast}
        </div>
      ) : null}
    </div>
  );
}
