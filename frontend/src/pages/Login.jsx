import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, Database, SearchCheck } from 'lucide-react';
import { useAppContext } from '../context/AppContext';

export default function Login() {
  const navigate = useNavigate();
  const { setProfile } = useAppContext();
  
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleLogin = (e) => {
    e.preventDefault();
    if (email) {
      setProfile({
        name: email.split('@')[0],
        email: email,
        department: 'Operations',
        timezone: 'UTC'
      });
      navigate('/ask');
    }
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: 'var(--bg-main)' }}>
      {/* Left Panel */}
      <div style={{ 
        flex: 1, 
        padding: '4rem', 
        display: 'flex', 
        flexDirection: 'column', 
        borderRight: '1px solid var(--border-color)',
        backgroundColor: '#f8faff', // Light panel from screenshot
        color: '#0f1117'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '4rem' }}>
          <div style={{
            width: '32px', height: '32px',
            background: 'var(--bg-primary)',
            borderRadius: '8px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontWeight: 'bold'
          }}>P</div>
          <h2 style={{ fontSize: '1.25rem', margin: 0, fontWeight: 700 }}>Pucho AI</h2>
          <span className="badge badge-ok" style={{ marginLeft: '0.5rem' }}>SOC2 Ready</span>
        </div>

        <h1 style={{ fontSize: '3.5rem', fontWeight: 700, lineHeight: 1.1, marginBottom: '1rem', color: '#0f1117' }}>
          Ask your data <span style={{ color: 'var(--bg-primary)' }}>anything.</span>
        </h1>
        <p style={{ fontSize: '1.25rem', color: '#4b5563', marginBottom: '3rem', maxWidth: '400px' }}>
          Get trusted answers from your database without writing SQL.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          <div style={{ display: 'flex', gap: '1rem' }}>
            <div style={{ color: 'var(--accent-green)', padding: '0.5rem', background: 'var(--accent-green-bg)', borderRadius: '8px', height: 'fit-content' }}>
              <ShieldCheck size={24} />
            </div>
            <div>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.25rem', color: '#0f1117' }}>Read-only by design</h3>
              <p style={{ color: '#4b5563', fontSize: '0.875rem' }}>Pucho cannot alter, delete, or write data. Strict database sandboxing.</p>
            </div>
          </div>
          
          <div style={{ display: 'flex', gap: '1rem' }}>
            <div style={{ color: 'var(--bg-primary)', padding: '0.5rem', background: 'rgba(79, 110, 247, 0.1)', borderRadius: '8px', height: 'fit-content' }}>
              <Database size={24} />
            </div>
            <div>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.25rem', color: '#0f1117' }}>Transparent SQL</h3>
              <p style={{ color: '#4b5563', fontSize: '0.875rem' }}>Inspect every query before or after execution with plain-English summaries.</p>
            </div>
          </div>
          
          <div style={{ display: 'flex', gap: '1rem' }}>
            <div style={{ color: 'var(--accent-green)', padding: '0.5rem', background: 'var(--accent-green-bg)', borderRadius: '8px', height: 'fit-content' }}>
              <SearchCheck size={24} />
            </div>
            <div>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.25rem', color: '#0f1117' }}>Verified answers</h3>
              <p style={{ color: '#4b5563', fontSize: '0.875rem' }}>Automatic statistical sanity checks and instant row consistency audits.</p>
            </div>
          </div>
        </div>

      </div>

      {/* Right Panel */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#ffffff' }}>
        <div style={{ width: '100%', maxWidth: '400px' }}>
          
          <div style={{ display: 'flex', background: '#f1f5f9', borderRadius: '8px', padding: '0.25rem', marginBottom: '2rem' }}>
            <button style={{ flex: 1, padding: '0.5rem', background: '#fff', border: 'none', borderRadius: '6px', fontWeight: 500, boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>Log in</button>
            <button style={{ flex: 1, padding: '0.5rem', background: 'transparent', border: 'none', color: '#64748b', fontWeight: 500 }}>Sign up</button>
          </div>

          <button style={{ 
            width: '100%', padding: '0.75rem', background: '#f8fafc', border: '1px solid #e2e8f0', 
            borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
            fontWeight: 500, color: '#0f1117', marginBottom: '2rem', cursor: 'pointer'
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
            Continue with Google
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
            <div style={{ flex: 1, height: '1px', background: '#e2e8f0' }}></div>
            <span style={{ color: '#94a3b8', fontSize: '0.875rem' }}>OR</span>
            <div style={{ flex: 1, height: '1px', background: '#e2e8f0' }}></div>
          </div>

          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500, color: '#0f1117' }}>Work Email</label>
              <input 
                type="email" 
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@company.com"
                style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid #e2e8f0', outline: 'none' }}
              />
            </div>
            
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <label style={{ fontSize: '0.875rem', fontWeight: 500, color: '#0f1117' }}>Password</label>
                <a href="#" style={{ fontSize: '0.875rem', color: 'var(--bg-primary)' }}>Forgot password?</a>
              </div>
              <input 
                type="password" 
                required
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••••••"
                style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid #e2e8f0', outline: 'none' }}
              />
            </div>

            <div style={{ background: 'var(--accent-green-bg)', color: 'var(--accent-green)', padding: '0.75rem', borderRadius: '8px', display: 'flex', gap: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
              <ShieldCheck size={18} />
              Zero database write permissions granted by default
            </div>

            <button type="submit" className="btn btn-primary" style={{ width: '100%', padding: '0.875rem' }}>
              Continue →
            </button>
          </form>

        </div>
      </div>
    </div>
  );
}
