import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import WorkspaceInvitePanel from '../WorkspaceInvitePanel';
import { listWorkspaceMembers } from '../../../api/auth';

let user;

vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({ user }),
}));

vi.mock('../../../api/auth', () => ({
  createWorkspaceInvite: vi.fn(),
  listWorkspaceMembers: vi.fn(),
  updateWorkspaceMemberRole: vi.fn(),
  removeWorkspaceMember: vi.fn(),
}));

describe('WorkspaceInvitePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    user = {
      id: 'admin-id', role: 'admin', workspace_role: 'admin',
      workspace_type: 'business', workspace_name: 'Acme',
      capabilities: { administer_workspace: true },
    };
    listWorkspaceMembers.mockResolvedValue([
      { id: 'owner-id', full_name: 'Olivia Owner', email: 'owner@acme.test', role: 'owner' },
      { id: 'editor-id', full_name: 'Eddie Editor', email: 'editor@acme.test', role: 'editor' },
    ]);
  });

  it('lets an admin invite people and manage non-owner members', async () => {
    render(<WorkspaceInvitePanel />);

    expect(screen.getByRole('heading', { name: /invite people to acme/i })).toBeInTheDocument();
    expect(await screen.findByText('Eddie Editor')).toBeInTheDocument();
    expect(screen.getByLabelText(/role for eddie editor/i)).toHaveClass('workspace-member-role');
    expect(screen.getByLabelText(/role for eddie editor/i)).toHaveValue('editor');
    expect(screen.getByRole('button', { name: /remove eddie editor/i })).toHaveClass('workspace-member-remove');
    expect(screen.queryByRole('button', { name: /remove olivia owner/i })).not.toBeInTheDocument();
  });

  it('stays hidden when the capability is absent', async () => {
    user = { ...user, role: 'editor', capabilities: { administer_workspace: false } };
    const { container } = render(<WorkspaceInvitePanel />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(listWorkspaceMembers).not.toHaveBeenCalled();
  });
});
