import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { can } from '../../auth/capabilities';
import Sidebar from '../../components/layout/Sidebar';
import TopBar from '../../components/layout/TopBar';
import ConnectData from '../ConnectData';
import Settings from '../Settings';

let user;

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ user, updateProfileImage: vi.fn() }),
}));
vi.mock('../../context/AppContext', () => ({
  useAppContext: () => ({
    workspaces: [], activeWorkspace: null, activeWorkspaceId: null,
    setActiveWorkspaceId: vi.fn(), setWorkspaces: vi.fn(),
  }),
}));
vi.mock('../../components/workspace/WorkspaceInvitePanel', () => ({
  default: () => <div>Invite management</div>,
}));
vi.mock('../../components/auth/ChangeEmailPanel', () => ({
  default: () => <div>Change email</div>,
}));
vi.mock('../../api/client', () => ({
  fetchApi: vi.fn().mockResolvedValue({ items: [], unread_count: 0 }),
}));

const capabilityMap = {
  owner: { view_workspaces: true, view_history: true, query_workspace: true, manage_data_sources: true, administer_workspace: true, manage_account: true },
  admin: { view_workspaces: true, view_history: true, query_workspace: true, manage_data_sources: true, administer_workspace: true, manage_account: true },
  editor: { view_workspaces: true, view_history: true, query_workspace: true, manage_data_sources: false, administer_workspace: false, manage_account: true },
  viewer: { view_workspaces: true, view_history: true, query_workspace: false, manage_data_sources: false, administer_workspace: false, manage_account: true },
};

function setRole(role) {
  user = {
    id: `${role}-id`, full_name: 'Ada Lovelace', email: 'ada@example.com',
    role, workspace_role: role, workspace_type: 'business', workspace_name: 'Acme',
    capabilities: capabilityMap[role],
  };
}

function renderRoute(component) {
  return render(<MemoryRouter>{component}</MemoryRouter>);
}

describe('role-aware product surfaces', () => {
  beforeEach(() => setRole('owner'));

  it.each(['owner', 'admin'])('%s sees data-source and admin surfaces', (role) => {
    setRole(role);
    renderRoute(<Sidebar />);
    expect(screen.getByText('Data sources')).toBeInTheDocument();
    renderRoute(<Settings />);
    expect(screen.getByText('Invite management')).toBeInTheDocument();
    expect(screen.getByText(new RegExp(role, 'i'))).toBeInTheDocument();
  });

  it('editor can ask and review but cannot see or open uploads', () => {
    setRole('editor');
    renderRoute(<Sidebar />);
    expect(screen.getByText('Ask data')).toBeInTheDocument();
    expect(screen.getByText('History')).toBeInTheDocument();
    expect(screen.queryByText('Data sources')).not.toBeInTheDocument();
    renderRoute(<ConnectData />);
    expect(screen.queryByLabelText(/upload/i)).not.toBeInTheDocument();
    expect(screen.getByText(/does not allow data source changes/i)).toBeInTheDocument();
  });

  it('viewer sees history and account settings only', () => {
    setRole('viewer');
    renderRoute(<Sidebar />);
    expect(screen.getByText('History')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.queryByText('Ask data')).not.toBeInTheDocument();
    expect(screen.queryByText('Data sources')).not.toBeInTheDocument();
    renderRoute(<Settings />);
    expect(screen.getByText('Upload image')).toBeInTheDocument();
    expect(screen.getByText('Use image link')).toBeInTheDocument();
    expect(screen.queryByText('Invite management')).not.toBeInTheDocument();
    expect(screen.getByText(/viewer/i)).toBeInTheDocument();
  });

  it('capabilities deny missing and unknown permissions', () => {
    expect(can(null, 'view_history')).toBe(false);
    expect(can({ capabilities: {} }, 'view_history')).toBe(false);
    expect(can(user, 'does_not_exist')).toBe(false);
  });

  it.each(['owner', 'admin', 'editor', 'viewer'])('%s can manage a profile image', (role) => {
    setRole(role);
    renderRoute(<Settings />);
    expect(screen.getByText('Upload image')).toBeInTheDocument();
    expect(screen.getByText('Use image link')).toBeInTheDocument();
  });

  it('uses the account image in the top bar', () => {
    setRole('editor');
    user.image_url = 'https://images.example.com/ada.png';
    const { container } = renderRoute(<TopBar />);
    expect(container.querySelector('.topbar-avatar img')).toHaveAttribute('src', user.image_url);
  });
});
