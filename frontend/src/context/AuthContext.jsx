import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import {
  api,
  login as loginRequest,
  logout as logoutRequest,
  signup as signupRequest,
  verifyLogin as verifyRequest,
} from '../api/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    let cancelled = false;
    api('/api/v1/auth/me')
      .then((nextUser) => {
        if (!cancelled) setUser(nextUser);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setStatus('ready');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(
    () => ({
      user,
      status,
      async requestLogin(payload) {
        return loginRequest(payload);
      },
      async verifyLogin(payload) {
        const result = await verifyRequest(payload);
        setUser(result.user);
        return result.user;
      },
      async signup(payload) {
        const result = await signupRequest(payload);
        setUser(result.user);
        return result.user;
      },
      async logout() {
        await logoutRequest();
        setUser(null);
      },
    }),
    [user, status],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
