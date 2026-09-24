import { createContext, useContext, useState, useEffect } from 'react';
import { fetchApi } from '../api/client';

const AppContext = createContext();

export function AppProvider({ children }) {
  const [workspaces, setWorkspaces] = useState([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);


  // Load initial data
  useEffect(() => {
    async function loadInitialData() {
      try {
        // First check if user is authenticated
        const profileData = await fetchApi('/auth/me');
        setProfile(profileData);
        
        // If authenticated, load workspaces
        const wsData = await fetchApi('/workspaces/');
        setWorkspaces(wsData || []);
        if (wsData && wsData.length > 0) {
          setActiveWorkspaceId(wsData[0].id);
        }
      } catch (err) {
        console.error("Failed to load initial data (user might not be logged in)", err);
        setProfile(null);
      } finally {
        setLoading(false);
      }
    }
    
    loadInitialData();
  }, []);

  const logout = async () => {
    try {
      await fetchApi('/auth/logout', { method: 'POST' });
    } catch (err) {
      console.error("Logout error", err);
    } finally {
      setProfile(null);
      setWorkspaces([]);
      setActiveWorkspaceId(null);
    }
  };

  const getActiveWorkspace = () => {
    return workspaces.find(w => w.id === activeWorkspaceId) || null;
  };

  const value = {
    workspaces,
    setWorkspaces,
    activeWorkspaceId,
    setActiveWorkspaceId,
    activeWorkspace: getActiveWorkspace(),
    profile,
    setProfile,
    loading,
    logout
  };

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useAppContext must be used within an AppProvider');
  }
  return context;
}
