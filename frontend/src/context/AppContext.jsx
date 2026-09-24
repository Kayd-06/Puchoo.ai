import { createContext, useContext, useState, useEffect } from 'react';
import { fetchApi } from '../api/client';

const AppContext = createContext();

export function AppProvider({ children }) {
  const [workspaces, setWorkspaces] = useState([]);
  const [activeWorkspaceId, setActiveWorkspaceIdState] = useState(
    () => window.localStorage.getItem('pucho_active_workspace') || null
  );
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshWorkspaces = async () => {
    const wsData = (await fetchApi('/workspaces/')) || [];
    setWorkspaces(wsData);
    setActiveWorkspaceId(currentId =>
      wsData.some(workspace => workspace.id === currentId)
        ? currentId
        : (wsData[0]?.id || null)
    );
    return wsData;
  };

  const setActiveWorkspaceId = (workspaceIdOrUpdater) => {
    setActiveWorkspaceIdState(currentId => {
      const nextId = typeof workspaceIdOrUpdater === 'function'
        ? workspaceIdOrUpdater(currentId)
        : workspaceIdOrUpdater;
      if (nextId) window.localStorage.setItem('pucho_active_workspace', nextId);
      else window.localStorage.removeItem('pucho_active_workspace');
      return nextId;
    });
  };

  // Load initial data
  useEffect(() => {
    async function loadInitialData() {
      try {
        const [, profileData] = await Promise.all([
          refreshWorkspaces(),
          fetchApi('/settings/profile')
        ]);
        setProfile(profileData);
      } catch (err) {
        console.error("Failed to load initial data", err);
      } finally {
        setLoading(false);
      }
    }
    
    loadInitialData();
  }, []);

  const getActiveWorkspace = () => {
    return workspaces.find(w => w.id === activeWorkspaceId) || null;
  };

  const value = {
    workspaces,
    setWorkspaces,
    activeWorkspaceId,
    setActiveWorkspaceId,
    activeWorkspace: getActiveWorkspace(),
    refreshWorkspaces,
    profile,
    setProfile,
    loading
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
