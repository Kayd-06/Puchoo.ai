import { useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { ShieldCheck, Database, SearchCheck, Eye, EyeOff } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { fetchApi } from '../api/client';

export default function Login() {
  const navigate = useNavigate();
  const { setProfile, profile, loading } = useAppContext();
  
  const [activeTab, setActiveTab] = useState('login'); // 'login' | 'signup'
  const [loginMethod, setLoginMethod] = useState('password'); // 'password' | 'otp'
  const [otpSent, setOtpSent] = useState(false);
  
  // Form fields
  const [name, setName] = useState('');
  const [identifier, setIdentifier] = useState(''); // email or phone
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [accountType, setAccountType] = useState('personal');
  const [otp, setOtp] = useState('');
  
  const [showPassword, setShowPassword] = useState(false);
  const [signupOtpSent, setSignupOtpSent] = useState(false);
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // If already logged in, redirect
  if (!loading && profile) {
    return <Navigate to="/ask" replace />;
  }

  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg('');
    setSuccessMsg('');
    
    try {
      if (loginMethod === 'password') {
        const data = await fetchApi('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ identifier, password })
        });
        setProfile(data.profile);
        navigate('/ask');
      } else if (loginMethod === 'otp' && !otpSent) {
        // Request OTP
        await fetchApi('/auth/send-otp', {
          method: 'POST',
          body: JSON.stringify({ identifier })
        });
        setOtpSent(true);
        setSuccessMsg('OTP sent! Please check your messages.');
      } else if (loginMethod === 'otp' && otpSent) {
        // Verify OTP
        const data = await fetchApi('/auth/verify-otp', {
          method: 'POST',
          body: JSON.stringify({ identifier, otp })
        });
        setProfile(data.profile);
        navigate('/ask');
      }
    } catch (err) {
      setErrorMsg(err.message || 'Authentication failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSignupSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg('');
    
    if (password !== confirmPassword) {
      setErrorMsg("Passwords do not match");
      setIsSubmitting(false);
      return;
    }
    
    try {
      if (!signupOtpSent) {
        await fetchApi('/auth/send-otp', {
          method: 'POST',
          body: JSON.stringify({ identifier })
        });
        setSignupOtpSent(true);
        setSuccessMsg('OTP sent! Please check your messages.');
      } else {
        const data = await fetchApi('/auth/signup', {
          method: 'POST',
          body: JSON.stringify({ name, identifier, password, account_type: accountType, otp })
        });
        setProfile(data.profile);
        navigate('/ask');
      }
    } catch (err) {
      setErrorMsg(err.message || 'Signup failed');
    } finally {
      setIsSubmitting(false);
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
        backgroundColor: '#f8faff',
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
            <button 
              onClick={() => setActiveTab('login')}
              style={{ flex: 1, padding: '0.5rem', background: activeTab === 'login' ? '#fff' : 'transparent', border: 'none', borderRadius: '6px', fontWeight: 500, boxShadow: activeTab === 'login' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none', color: activeTab === 'login' ? '#0f1117' : '#64748b', cursor: 'pointer' }}
            >
              Log in
            </button>
            <button 
              onClick={() => setActiveTab('signup')}
              style={{ flex: 1, padding: '0.5rem', background: activeTab === 'signup' ? '#fff' : 'transparent', border: 'none', borderRadius: '6px', fontWeight: 500, boxShadow: activeTab === 'signup' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none', color: activeTab === 'signup' ? '#0f1117' : '#64748b', cursor: 'pointer' }}
            >
              Sign up
            </button>
          </div>

          {errorMsg && (
            <div style={{ padding: '0.75rem', background: 'var(--accent-red-bg)', color: 'var(--accent-red)', borderRadius: '8px', marginBottom: '1.5rem', fontSize: '0.875rem' }}>
              {errorMsg}
            </div>
          )}

          {successMsg && (
            <div style={{ padding: '0.75rem', background: 'var(--accent-green-bg)', color: 'var(--accent-green)', borderRadius: '8px', marginBottom: '1.5rem', fontSize: '0.875rem' }}>
              {successMsg}
            </div>
          )}

          {activeTab === 'login' ? (
            <form onSubmit={handleLoginSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500, color: '#0f1117' }}>Email or Phone</label>
                <input 
                  type="text" 
                  required
                  disabled={otpSent}
                  value={identifier}
                  onChange={e => setIdentifier(e.target.value)}
                  style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid #e2e8f0', outline: 'none', backgroundColor: otpSent ? '#f1f5f9' : '#fff' }}
                />
              </div>
              
              {loginMethod === 'password' && (
                <div>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500, color: '#0f1117' }}>Password</label>
                  <div style={{ position: 'relative' }}>
                    <input 
                      type={showPassword ? "text" : "password"} 
                      required
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      style={{ width: '100%', padding: '0.75rem', paddingRight: '2.5rem', borderRadius: '8px', border: '1px solid #e2e8f0', outline: 'none' }}
                    />
                    <button type="button" onClick={() => setShowPassword(!showPassword)} style={{ position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
              )}

              {loginMethod === 'otp' && otpSent && (
                <div>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500, color: '#0f1117' }}>Enter OTP</label>
                  <input 
                    type="text" 
                    required
                    value={otp}
                    onChange={e => setOtp(e.target.value)}
                    style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid #e2e8f0', outline: 'none' }}
                  />
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '-0.75rem' }}>
                {loginMethod === 'password' ? (
                  <button type="button" onClick={() => setLoginMethod('otp')} style={{ fontSize: '0.875rem', color: 'var(--bg-primary)', background: 'none', border: 'none', cursor: 'pointer' }}>
                    Login with OTP instead
                  </button>
                ) : (
                  <button type="button" onClick={() => { setLoginMethod('password'); setOtpSent(false); }} style={{ fontSize: '0.875rem', color: 'var(--bg-primary)', background: 'none', border: 'none', cursor: 'pointer' }}>
                    Login with Password instead
                  </button>
                )}
              </div>

              <div style={{ background: 'var(--accent-green-bg)', color: 'var(--accent-green)', padding: '0.75rem', borderRadius: '8px', display: 'flex', gap: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
                <ShieldCheck size={18} />
                Zero database write permissions granted by default
              </div>

              <button type="submit" disabled={isSubmitting} className="btn btn-primary" style={{ width: '100%', padding: '0.875rem' }}>
                {isSubmitting ? 'Loading...' : (loginMethod === 'otp' && !otpSent ? 'Send OTP' : 'Continue →')}
              </button>
            </form>
          ) : (
            <form onSubmit={handleSignupSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500, color: '#0f1117' }}>Account Type</label>
                <select 
                  disabled={signupOtpSent}
                  value={accountType}
                  onChange={e => setAccountType(e.target.value)}
                  style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid #e2e8f0', outline: 'none', backgroundColor: '#fff', marginBottom: '0.5rem' }}
                >
                  <option value="personal">Personal</option>
                  <option value="business">Business</option>
                  <option value="institutional">Institutional</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500, color: '#0f1117' }}>Full Name</label>
                <input 
                  type="text" 
                  required
                  disabled={signupOtpSent}
                  value={name}
                  onChange={e => setName(e.target.value)}
                  style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid #e2e8f0', outline: 'none' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500, color: '#0f1117' }}>Email or Phone</label>
                <input 
                  type="text" 
                  required
                  disabled={signupOtpSent}
                  value={identifier}
                  onChange={e => setIdentifier(e.target.value)}
                  style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid #e2e8f0', outline: 'none' }}
                />
              </div>
              
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500, color: '#0f1117' }}>Password</label>
                <div style={{ position: 'relative' }}>
                  <input 
                    type={showPassword ? "text" : "password"} 
                    required
                    disabled={signupOtpSent}
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    style={{ width: '100%', padding: '0.75rem', paddingRight: '2.5rem', borderRadius: '8px', border: '1px solid #e2e8f0', outline: 'none' }}
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} style={{ position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500, color: '#0f1117' }}>Confirm Password</label>
                <div style={{ position: 'relative' }}>
                  <input 
                    type={showPassword ? "text" : "password"} 
                    required
                    disabled={signupOtpSent}
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    style={{ width: '100%', padding: '0.75rem', paddingRight: '2.5rem', borderRadius: '8px', border: '1px solid #e2e8f0', outline: 'none' }}
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} style={{ position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              {signupOtpSent && (
                <div>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500, color: '#0f1117' }}>Enter OTP</label>
                  <input 
                    type="text" 
                    required
                    value={otp}
                    onChange={e => setOtp(e.target.value)}
                    style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid #e2e8f0', outline: 'none' }}
                  />
                </div>
              )}

              <button type="submit" disabled={isSubmitting} className="btn btn-primary" style={{ width: '100%', padding: '0.875rem' }}>
                {isSubmitting ? 'Processing...' : (signupOtpSent ? 'Verify & Create account →' : 'Send OTP')}
              </button>
            </form>
          )}

        </div>
      </div>
    </div>
  );
}
