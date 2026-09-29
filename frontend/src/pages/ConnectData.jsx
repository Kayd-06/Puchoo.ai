import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, Upload, Server } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { useAuth } from '../context/AuthContext';
import { fetchApi } from '../api/client';

export default function ConnectData() {
  const { workspaces, setWorkspaces, setActiveWorkspaceId } = useAppContext();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('upload');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [workspaceName, setWorkspaceName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [serverForm, setServerForm] = useState({
    name: '', engine: 'postgresql', host: '', port: '5432', database: '', username: '', password: '', ssl_required: true,
  });
  const [connecting, setConnecting] = useState(false);
  const [serverError, setServerError] = useState('');

  if (user?.workspace_role === 'viewer') {
    return <div className="card" style={{ maxWidth: '44rem' }}><h1 style={{ fontSize: '2rem' }}>Viewer access</h1><p className="text-muted" style={{ marginTop: '.75rem', lineHeight: 1.6 }}>Viewers can inspect approved queries and history, but cannot upload files, connect databases, or change workspace data.</p><Link className="btn btn-primary" to="/history" style={{ marginTop: '1.25rem' }}>View query history</Link></div>;
  }

  const uploadFiles = async () => {
    if (!selectedFiles.length) return;
    setUploading(true);
    setUploadError('');
    try {
      const form = new FormData();
      const multiple = selectedFiles.length > 1;
      selectedFiles.forEach((file) => form.append(multiple ? 'files' : 'file', file));
      form.append('name', workspaceName.trim());
      const workspace = await fetchApi(
        multiple ? '/workspaces/upload-multiple' : '/workspaces/upload',
        {
          method: 'POST',
          body: form,
        },
      );
      setWorkspaces([...workspaces, workspace]);
      setActiveWorkspaceId(workspace.id);
      setSelectedFiles([]);
      setWorkspaceName('');
    } catch (error) {
      setUploadError(error.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const updateServerForm = (field, value) => {
    setServerForm((current) => ({ ...current, [field]: value }));
  };

  const connectServer = async (event) => {
    event.preventDefault();
    if (!serverForm.name.trim() || !serverForm.host.trim() || !serverForm.database.trim() || !serverForm.username.trim() || !serverForm.password) {
      setServerError('Enter a workspace name and all connection details.');
      return;
    }
    const port = Number(serverForm.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      setServerError('Enter a valid database port.');
      return;
    }
    setConnecting(true);
    setServerError('');
    try {
      const workspace = await fetchApi('/workspaces/server', {
        method: 'POST',
        body: JSON.stringify({ ...serverForm, name: serverForm.name.trim(), host: serverForm.host.trim(), database: serverForm.database.trim(), username: serverForm.username.trim(), port }),
      });
      setWorkspaces([...workspaces, workspace]);
      setActiveWorkspaceId(workspace.id);
      setServerForm({ name: '', engine: 'postgresql', host: '', port: '5432', database: '', username: '', password: '', ssl_required: true });
    } catch (error) {
      setServerError(error.message || 'Could not connect to that database.');
    } finally {
      setConnecting(false);
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>Connect your data</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '2rem' }}>
        Link your database or upload a local file. Puchoo accesses your schema securely in read-only
        mode with zero mutations guaranteed.
      </p>

      <div
        className="card"
        style={{
          backgroundColor: 'var(--accent-green-bg)',
          borderColor: 'rgba(34, 197, 94, 0.2)',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
          marginBottom: '2rem',
        }}
      >
        <div style={{ color: 'var(--accent-green)' }}>
          <ShieldCheck size={32} />
        </div>
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              marginBottom: '0.25rem',
            }}
          >
            <h3 style={{ margin: 0, color: 'var(--accent-green)' }}>
              100% Read-Only Safety Guarantee
            </h3>
            <span
              className="badge badge-ok"
              style={{ border: '1px solid rgba(34,197,94,0.3)', background: 'transparent' }}
            >
              Strict Read Mode
            </span>
          </div>
          <p style={{ margin: 0, color: 'var(--text-primary)', fontSize: '0.875rem' }}>
            Puchoo connects exclusively in read-only mode. Your source data cannot be changed,
            deleted, or overwritten under any condition. All SQL mutations are blocked at the driver
            layer.
          </p>
        </div>
      </div>

      <div className="connect-layout" style={{ display: 'flex', gap: '2rem' }}>
        <div style={{ flex: 2 }}>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
            <button
              className={`btn ${activeTab === 'upload' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setActiveTab('upload')}
              style={{ flex: 1 }}
            >
              <Upload size={16} style={{ marginRight: '0.5rem' }} /> Upload database file
            </button>
            <button
              className={`btn ${activeTab === 'server' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setActiveTab('server')}
              style={{ flex: 1 }}
            >
              <Server size={16} style={{ marginRight: '0.5rem' }} /> Connect database server
            </button>
          </div>

          <div className="card">
            {activeTab === 'upload' ? (
              <div style={{ textAlign: 'center', padding: '3rem 1rem' }}>
                <Upload size={48} color="var(--bg-primary)" style={{ marginBottom: '1rem' }} />
                <h3>Upload one or more data files</h3>
                <p className="text-muted" style={{ marginBottom: '1.5rem' }}>
                  Select multiple CSV or Excel files to combine them into one queryable workspace.
                  SQLite databases are uploaded individually.
                </p>
                <input
                  type="file"
                  multiple
                  accept=".csv,.xlsx,.xls,.db,.sqlite,.sqlite3"
                  style={{ display: 'none' }}
                  id="fileUpload"
                  onChange={(event) => setSelectedFiles(Array.from(event.target.files || []))}
                />
                <label
                  htmlFor="fileUpload"
                  className="btn btn-secondary"
                  style={{ cursor: 'pointer' }}
                >
                  Browse files
                </label>
                {selectedFiles.length > 0 && (
                  <div style={{ marginTop: '1.5rem', textAlign: 'left' }}>
                    <input
                      className="input"
                      value={workspaceName}
                      onChange={(event) => setWorkspaceName(event.target.value)}
                      placeholder="Workspace name (optional)"
                      style={{ marginBottom: '1rem' }}
                    />
                    <div className="text-muted text-xs" style={{ marginBottom: '1rem' }}>
                      {selectedFiles.map((file) => file.name).join(', ')}
                    </div>
                    {uploadError && (
                      <div style={{ color: 'var(--accent-red)', marginBottom: '1rem' }}>
                        {uploadError}
                      </div>
                    )}
                    <button className="btn btn-primary" onClick={uploadFiles} disabled={uploading}>
                      {uploading
                        ? 'Uploading…'
                        : `Create workspace from ${selectedFiles.length} file${selectedFiles.length === 1 ? '' : 's'}`}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <form onSubmit={connectServer} noValidate>
                <h3 style={{ marginBottom: '1.5rem' }}>Server Connection</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <input type="text" className="input" placeholder="Workspace name" value={serverForm.name} onChange={(event) => updateServerForm('name', event.target.value)} />
                  <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 120px', gap: '.75rem' }}>
                    <select className="input" value={serverForm.engine} onChange={(event) => { const engine = event.target.value; updateServerForm('engine', engine); updateServerForm('port', engine === 'mysql' ? '3306' : '5432'); }} aria-label="Database engine"><option value="postgresql">PostgreSQL</option><option value="mysql">MySQL</option></select>
                    <input type="number" className="input" placeholder="Port" min="1" max="65535" value={serverForm.port} onChange={(event) => updateServerForm('port', event.target.value)} aria-label="Database port" />
                  </div>
                  <input type="text" className="input" placeholder="Host (e.g. db.example.com)" value={serverForm.host} onChange={(event) => updateServerForm('host', event.target.value)} />
                  <input type="text" className="input" placeholder="Database name" value={serverForm.database} onChange={(event) => updateServerForm('database', event.target.value)} />
                  <input type="text" className="input" placeholder="Read-only username" autoComplete="username" value={serverForm.username} onChange={(event) => updateServerForm('username', event.target.value)} />
                  <input type="password" className="input" placeholder="Password" autoComplete="current-password" value={serverForm.password} onChange={(event) => updateServerForm('password', event.target.value)} />
                  <label style={{ display: 'flex', gap: '.5rem', alignItems: 'center', fontSize: '.875rem', color: 'var(--text-muted)' }}><input type="checkbox" checked={serverForm.ssl_required} onChange={(event) => updateServerForm('ssl_required', event.target.checked)} /> Require SSL/TLS</label>
                  {serverError && <p role="alert" style={{ color: 'var(--accent-red)', fontSize: '.875rem' }}>{serverError}</p>}
                  <button type="submit" className="btn btn-primary" style={{ marginTop: '1rem' }} disabled={connecting}>
                    {connecting ? 'Checking connection…' : 'Connect server'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>

        <div style={{ flex: 1 }}>
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <h3
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}
            >
              <ShieldCheck size={20} color="var(--bg-primary)" /> How Puchoo Protects You
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <div>
                <h4 style={{ fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                  Transaction Isolation
                </h4>
                <p className="text-muted text-xs">
                  Every inquiry wraps in an explicit SET TRANSACTION READ ONLY statement before
                  dispatch.
                </p>
              </div>
              <div>
                <h4 style={{ fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                  Zero Data Ingestion
                </h4>
                <p className="text-muted text-xs">
                  Puchoo only reads schema metadata and aggregate summaries. Raw customer PII
                  remains in your enclave.
                </p>
              </div>
              <div>
                <h4 style={{ fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                  Automatic Timeout Caps
                </h4>
                <p className="text-muted text-xs">
                  Queries running beyond 4,000ms are safely aborted to prevent lock contention on
                  your transactional databases.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
