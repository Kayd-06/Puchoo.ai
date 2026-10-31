import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import {
  api,
  login as loginRequest,
  logout as logoutRequest,
  resendLoginCode as resendLoginCodeRequest,
  signup as signupRequest,
  requestEmailChange as requestEmailChangeRequest,
  verifyEmailChange as verifyEmailChangeRequest,
  verifyLogin as verifyRequest,
  updateProfileImage as updateProfileImageRequest,
} from '../api/auth';

import { clearChatSessions } from '../hooks/useChatState';

const AuthContext = createContext(null);

export function AuthProvider({ children, loadSession = true }) {
  const [user, setUser] = useState(null);
  const [sessionChecked, setSessionChecked] = useState(() => !loadSession);

  useEffect(() => {
    if (!loadSession) {
      return undefined;
    }

    let cancelled = false;
    api('/api/v1/auth/me')
      .then((nextUser) => {
        if (!cancelled) setUser(nextUser);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setSessionChecked(true);
      });
    return () => {
      cancelled = true;
    };
  }, [loadSession]);

  useEffect(() => {
    const handleUnauthorized = () => {
      clearChatSessions();
      setUser(null);
    };
    window.addEventListener('puchoo:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('puchoo:unauthorized', handleUnauthorized);
  }, []);

  const value = useMemo(
    () => ({
      user,
      status: loadSession && !sessionChecked ? 'loading' : 'ready',
      async requestLogin(payload) {
        return loginRequest(payload);
      },
      async resendLoginCode() {
        return resendLoginCodeRequest();
      },
      async verifyLogin(payload) {
        const result = await verifyRequest(payload);
        setUser(result.user);
        return result.user;
      },
      async requestSignup(payload) {
        return signupRequest(payload);
      },
      async requestEmailChange(payload) {
        return requestEmailChangeRequest(payload);
      },
      async verifyEmailChange(payload) {
        const result = await verifyEmailChangeRequest(payload);
        setUser(result.user);
        return result.user;
      },
      async updateProfileImage(imageUrl) {
        const nextUser = await updateProfileImageRequest(imageUrl);
        setUser(nextUser);
        return nextUser;
      },
      async logout() {
        await logoutRequest();
        clearChatSessions();
        setUser(null);
      },
    }),
    [user, loadSession, sessionChecked],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
