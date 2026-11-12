import { useCallback, useEffect, useRef, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { X } from 'lucide-react';
import Sidebar from './Sidebar';
import TopBar from './TopBar';

export default function AppShell() {
  const [compact, setCompact] = useState(() =>
    window.matchMedia ? window.matchMedia('(max-width: 1023px)').matches : false,
  );
  const drawerRef = useRef(null);
  const openerRef = useRef(null);
  const previousOverflow = useRef(null);
  const { pathname } = useLocation();

  const restoreScroll = useCallback(() => {
    if (previousOverflow.current !== null) {
      document.body.style.overflow = previousOverflow.current;
      previousOverflow.current = null;
    }
  }, []);
  const closeDrawer = useCallback(() => {
    if (drawerRef.current?.open) drawerRef.current.close();
    restoreScroll();
  }, [restoreScroll]);

  useEffect(() => {
    const query = window.matchMedia?.('(max-width: 1023px)');
    const update = (event) => setCompact(event.matches);
    query?.addEventListener('change', update);
    return () => query?.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    const drawer = drawerRef.current;
    function onClose() {
      restoreScroll();
      if (openerRef.current?.isConnected) openerRef.current.focus();
    }
    drawer?.addEventListener('close', onClose);
    return () => {
      drawer?.removeEventListener('close', onClose);
      restoreScroll();
    };
  }, [compact, restoreScroll]);

  useEffect(() => closeDrawer(), [pathname, closeDrawer]);

  function openDrawer() {
    const drawer = drawerRef.current;
    if (!drawer || drawer.open) return;
    openerRef.current = document.activeElement;
    previousOverflow.current = document.body.style.overflow;
    drawer.showModal();
    document.body.style.overflow = 'hidden';
  }

  return (
    <div className="app-container">
      {compact ? (
        <dialog
          ref={drawerRef}
          id="workspace-navigation"
          className="workspace-navigation-drawer"
          aria-label="Workspace menu"
          onClick={(event) => {
            if (event.target === event.currentTarget) closeDrawer();
          }}
        >
          <div className="workspace-drawer-content">
            <button
              type="button"
              className="workspace-drawer-close"
              aria-label="Close workspace menu"
              onClick={closeDrawer}
            >
              <X size={20} />
            </button>
            <Sidebar onNavigate={closeDrawer} />
          </div>
        </dialog>
      ) : (
        <Sidebar />
      )}
      <main id="main-content" className="main-content">
        <TopBar onOpenNavigation={compact ? openDrawer : undefined} />
        <div className="page-container animate-fade-slide">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
