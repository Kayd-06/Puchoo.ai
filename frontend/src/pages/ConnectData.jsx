import { useState } from 'react';
import { ShieldCheck, Upload, Server } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { fetchApi } from '../api/client';

export default function ConnectData() {
  const { workspaces, setWorkspaces, setActiveWorkspaceId } = useAppContext();
  const [activeTab, setActiveTab] = useState('upload');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [workspaceName, setWorkspaceName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');

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

  return (
    <div>
      <h1 style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>Connect your data</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '2rem' }}>
        Link your database or upload a local file. Pucho accesses your schema securely in read-only
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
            Pucho connects exclusively in read-only mode. Your source data cannot be changed,
            deleted, or overwritten under any condition. All SQL mutations are blocked at the driver
            layer.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '2rem' }}>
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
              <div>
                <h3 style={{ marginBottom: '1.5rem' }}>Server Connection</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <input type="text" className="input" placeholder="Host (e.g. db.example.com)" />
                  <input type="text" className="input" placeholder="Database Name" />
                  <input type="text" className="input" placeholder="Read-only Username" />
                  <input type="password" className="input" placeholder="Password" />
                  <button className="btn btn-primary" style={{ marginTop: '1rem' }}>
                    Connect Server
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div style={{ flex: 1 }}>
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <h3
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}
            >
              <ShieldCheck size={20} color="var(--bg-primary)" /> How Pucho Protects You
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
                  Pucho LLMs only read schema metadata and aggregate summaries. Raw customer PII
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
