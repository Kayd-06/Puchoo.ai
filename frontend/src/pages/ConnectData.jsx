import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Check, FileSpreadsheet, Server, ShieldCheck, Upload, X } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { useAuth } from '../context/AuthContext';
import { fetchApi } from '../api/client';

const ACCEPTED_FILES = '.csv,.xlsx,.xls,.db,.sqlite,.sqlite3';

function fileLabel(file) {
  const size = file.size < 1024 * 1024 ? `${Math.max(1, Math.round(file.size / 1024))} KB` : `${(file.size / (1024 * 1024)).toFixed(1)} MB`;
  return `${file.name} · ${size}`;
}

export default function ConnectData() {
  const { workspaces, setWorkspaces, setActiveWorkspaceId } = useAppContext();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('upload');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [workspaceName, setWorkspaceName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [createdWorkspace, setCreatedWorkspace] = useState(null);
  const [hoveredLetter, setHoveredLetter] = useState(null);
  const wordRef = useRef(null);
  const [serverForm, setServerForm] = useState({
    name: '', engine: 'postgresql', host: '', port: '5432', database: '', username: '', password: '', ssl_required: true,
  });
  const [connecting, setConnecting] = useState(false);
  const [serverError, setServerError] = useState('');

  if (user?.workspace_role === 'viewer') {
    return <section className="connect-viewer-state"><ShieldCheck size={24} /><span>Viewer access</span><h1>Data sources are protected.</h1><p>Only workspace editors and admins can add or connect data sources. You can still inspect approved query history.</p><Link to="/history">View query history <ArrowUpRight size={16} /></Link></section>;
  }

  const selectFiles = (files) => {
    const incoming = Array.from(files || []);
    if (!incoming.length) return;
    setSelectedFiles(incoming);
    setUploadError('');
    setCreatedWorkspace(null);
  };

  const uploadFiles = async () => {
    if (!selectedFiles.length) return;
    setUploading(true);
    setUploadError('');
    try {
      const form = new FormData();
      const multiple = selectedFiles.length > 1;
      selectedFiles.forEach((file) => form.append(multiple ? 'files' : 'file', file));
      form.append('name', workspaceName.trim());
      const workspace = await fetchApi(multiple ? '/workspaces/upload-multiple' : '/workspaces/upload', { method: 'POST', body: form });
      setWorkspaces([...workspaces, workspace]);
      setActiveWorkspaceId(workspace.id);
      setCreatedWorkspace(workspace);
      setSelectedFiles([]);
      setWorkspaceName('');
    } catch (error) {
      setUploadError(error.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const updateServerForm = (field, value) => setServerForm((current) => ({ ...current, [field]: value }));

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
      setCreatedWorkspace(workspace);
      setServerForm({ name: '', engine: 'postgresql', host: '', port: '5432', database: '', username: '', password: '', ssl_required: true });
    } catch (error) {
      setServerError(error.message || 'Could not connect to that database.');
    } finally {
      setConnecting(false);
    }
  };

  const handleStagePointerMove = (event) => {
    const word = wordRef.current;
    if (!word) return;
    const bounds = word.getBoundingClientRect();
    const closeToWord = event.clientY >= bounds.top - 34 && event.clientY <= bounds.bottom + 34;
    let nextLetter = null;
    if (closeToWord) {
      Array.from(word.children).some((letter, index) => {
        const letterBounds = letter.getBoundingClientRect();
        const horizontalPadding = Math.min(38, letterBounds.width * .16);
        const insideLetter = event.clientX >= letterBounds.left - horizontalPadding
          && event.clientX <= letterBounds.right + horizontalPadding;
        if (insideLetter) {
          nextLetter = index;
          return true;
        }
        return false;
      });
    }
    setHoveredLetter((current) => current === nextLetter ? current : nextLetter);
  };

  const displayWord = uploading ? 'SYNC' : selectedFiles.length ? 'READY' : activeTab === 'server' ? 'LINK' : 'DATA';

  return (
    <div className="connect-page">
      <section className="connect-stage" onPointerMove={handleStagePointerMove} onPointerLeave={() => setHoveredLetter(null)}>
        <div ref={wordRef} className="connect-word" aria-hidden="true">{displayWord.split('').map((letter, index) => <span key={`${displayWord}-${index}`} className={hoveredLetter === index ? 'is-illuminated' : ''}>{letter}</span>)}</div>
        <header className="connect-stage-header"><span>Secure ingestion</span><span><i /> Read-only by design</span></header>
        <div className="connect-stage-content">
          <div className="connect-tablist" role="tablist" aria-label="Data source type">
            <button type="button" role="tab" aria-selected={activeTab === 'upload'} className={activeTab === 'upload' ? 'is-active' : ''} onClick={() => setActiveTab('upload')}><Upload size={15} /> Upload files</button>
            <button type="button" role="tab" aria-selected={activeTab === 'server'} className={activeTab === 'server' ? 'is-active' : ''} onClick={() => setActiveTab('server')}><Server size={15} /> Connect server</button>
          </div>

          {createdWorkspace ? (
            <div className="connect-complete" role="status"><div><Check size={22} /></div><span>Workspace ready</span><h1>{createdWorkspace.name}</h1><p>Your source is now isolated and available for verified, read-only analysis.</p><Link to="/ask">Ask your data <ArrowUpRight size={17} /></Link><button type="button" onClick={() => setCreatedWorkspace(null)}>Add another source</button></div>
          ) : activeTab === 'upload' ? (
            <div className="connect-upload-flow">
              <h1>Bring your data<br />into focus.</h1>
              <p>Upload CSV, Excel, or SQLite files. Puchoo builds one private, queryable workspace without mutating the source.</p>
              <input id="fileUpload" type="file" multiple accept={ACCEPTED_FILES} onChange={(event) => selectFiles(event.target.files)} hidden />
              <label htmlFor="fileUpload" className={`connect-dropzone${isDragging ? ' is-dragging' : ''}${uploading ? ' is-uploading' : ''}`} onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }} onDragLeave={() => setIsDragging(false)} onDrop={(event) => { event.preventDefault(); setIsDragging(false); selectFiles(event.dataTransfer.files); }}>
                <div className="connect-dropzone-mark"><Upload size={23} /></div>
                <strong>{uploading ? 'Creating isolated workspace…' : selectedFiles.length ? `${selectedFiles.length} file${selectedFiles.length > 1 ? 's' : ''} selected` : 'Drop files here'}</strong>
                <span>{uploading ? 'Validating structure and access boundaries' : 'or browse from your device'}</span>
              </label>

              {selectedFiles.length > 0 && !uploading && <div className="connect-selected-files"><div>{selectedFiles.map((file) => <span key={`${file.name}-${file.size}`}><FileSpreadsheet size={14} />{fileLabel(file)}<button type="button" onClick={() => setSelectedFiles((current) => current.filter((item) => item !== file))} aria-label={`Remove ${file.name}`}><X size={14} /></button></span>)}</div><input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} placeholder="Name this workspace (optional)" aria-label="Workspace name" /><button type="button" className="connect-submit" onClick={uploadFiles}>Create workspace <ArrowUpRight size={17} /></button></div>}
              {uploadError && <p className="connect-error" role="alert">{uploadError}</p>}
            </div>
          ) : (
            <form className="connect-server-form" onSubmit={connectServer} noValidate>
              <h1>Connect a<br />trusted source.</h1><p>Use a restricted database user. Puchoo validates every connection in read-only mode.</p>
              <div className="connect-server-grid">
                <input type="text" placeholder="Workspace name" value={serverForm.name} onChange={(event) => updateServerForm('name', event.target.value)} />
                <select value={serverForm.engine} onChange={(event) => { const engine = event.target.value; updateServerForm('engine', engine); updateServerForm('port', engine === 'mysql' ? '3306' : '5432'); }} aria-label="Database engine"><option value="postgresql">PostgreSQL</option><option value="mysql">MySQL</option></select>
                <input type="text" placeholder="Host (db.example.com)" value={serverForm.host} onChange={(event) => updateServerForm('host', event.target.value)} />
                <input type="number" placeholder="Port" min="1" max="65535" value={serverForm.port} onChange={(event) => updateServerForm('port', event.target.value)} aria-label="Database port" />
                <input type="text" placeholder="Database name" value={serverForm.database} onChange={(event) => updateServerForm('database', event.target.value)} />
                <input type="text" placeholder="Read-only username" autoComplete="username" value={serverForm.username} onChange={(event) => updateServerForm('username', event.target.value)} />
                <input type="password" placeholder="Password" autoComplete="current-password" value={serverForm.password} onChange={(event) => updateServerForm('password', event.target.value)} />
              </div>
              <label className="connect-ssl"><input type="checkbox" checked readOnly disabled /> TLS is required by the server</label>
              {serverError && <p className="connect-error" role="alert">{serverError}</p>}
              <button type="submit" className="connect-submit" disabled={connecting}>{connecting ? 'Checking connection…' : 'Connect source'} <ArrowUpRight size={17} /></button>
            </form>
          )}
        </div>
        <footer className="connect-stage-footer"><span>CSV · XLSX · SQLITE</span><span>Source data is never altered</span><span>Encrypted in transit</span></footer>
      </section>
    </div>
  );
}
