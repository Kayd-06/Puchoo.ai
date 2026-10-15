import { useRef, useState } from 'react';
import { Camera, Check, History as HistoryIcon, ImageUp, Link2, ShieldCheck, Trash2, User, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import ChangeEmailPanel from '../components/auth/ChangeEmailPanel';
import WorkspaceInvitePanel from '../components/workspace/WorkspaceInvitePanel';
import { can } from '../auth/capabilities';

export default function Settings() {
  const { user, updateProfileImage } = useAuth();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [photoEditorOpen, setPhotoEditorOpen] = useState(false);
  const [photoMode, setPhotoMode] = useState('upload');
  const [photoDraft, setPhotoDraft] = useState(user?.image_url || '');
  const [photoError, setPhotoError] = useState('');
  const [photoSaving, setPhotoSaving] = useState(false);

  function openPhotoEditor(mode = 'upload') {
    setPhotoMode(mode);
    setPhotoDraft(user?.image_url || '');
    setPhotoError('');
    setPhotoEditorOpen(true);
  }

  function closePhotoEditor() {
    setPhotoEditorOpen(false);
    setPhotoDraft(user?.image_url || '');
    setPhotoError('');
  }

  function choosePhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(file.type)) {
      setPhotoError('Choose a PNG, JPEG, WebP, or GIF image.');
      return;
    }
    if (file.size > 1_000_000) {
      setPhotoError('Choose an image smaller than 1 MB.');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setPhotoDraft(String(reader.result || ''));
      setPhotoError('');
    };
    reader.onerror = () => setPhotoError('That image could not be read. Try another file.');
    reader.readAsDataURL(file);
  }

  function updatePhotoLink(value) {
    setPhotoDraft(value);
    setPhotoError(value && !value.startsWith('https://') ? 'Use a secure HTTPS image link.' : '');
  }

  async function savePhoto(imageUrl = photoDraft) {
    if (imageUrl && !imageUrl.startsWith('https://') && !imageUrl.startsWith('data:image/')) {
      setPhotoError('Choose an image or enter a secure HTTPS image link.');
      return;
    }
    setPhotoSaving(true);
    setPhotoError('');
    try {
      await updateProfileImage(imageUrl || null);
      setPhotoEditorOpen(false);
    } catch (error) {
      setPhotoError(error.message || 'The profile image could not be saved.');
    } finally {
      setPhotoSaving(false);
    }
  }

  return (
    <div className="settings-page">
      <header className="settings-hero">
        <div className="settings-eyebrow">
        <ShieldCheck size={20} />
          <span>System preferences</span>
        </div>
        <div className="settings-hero-copy">
          <div>
            <h1>Settings</h1>
            <p>Control your profile, workspace access, and verified account settings.</p>
          </div>
        </div>
      </header>

      <div className="settings-flow">
        {can(user, 'administer_workspace') && <WorkspaceInvitePanel />}
        <section className="settings-section settings-profile" aria-labelledby="profile-title">
          <div className="settings-card-label"><User size={15} /><span>Account profile</span><small>{user?.role || 'member'}</small></div>
          <div className="settings-profile-topline">
            <button type="button" className={`settings-avatar settings-avatar-button${user?.image_url ? ' has-image' : ''}`} onClick={() => openPhotoEditor()} aria-label="Change profile image">
              {user?.image_url
                ? <img src={user.image_url} alt="Your profile" />
                : (user?.full_name ? user.full_name.charAt(0).toUpperCase() : <User />)}
              <span className="settings-avatar-edit" aria-hidden="true"><Camera size={12} /></span>
            </button>
            <div className="settings-profile-identity">
              <div className="settings-profile-titleline">
                <h2 id="profile-title">{user?.full_name || 'User'}</h2>
                <span className="settings-workspace-badge">
                  {user?.workspace_type === 'institution' ? `Institution · ${user?.role || 'member'}` : user?.workspace_type === 'business' ? `Business · ${user?.role || 'member'}` : `Personal · ${user?.role || 'owner'}`}
                </span>
              </div>
              <p>{user?.workspace_name || user?.institute_name || 'Puchoo.si workspace'} <span>•</span> {user?.email || 'email@example.com'}</p>
            </div>
            <span className="settings-verified"><ShieldCheck size={14} /> Email verified</span>
          </div>

          <div className="settings-photo-row">
            <div>
              <strong>Profile image</strong>
              <span>PNG, JPEG, WebP or GIF · maximum 1 MB</span>
            </div>
            <div className="settings-photo-entry-actions">
              <button type="button" className="settings-action" onClick={() => openPhotoEditor('upload')}><ImageUp size={15} /> Upload image</button>
              <button type="button" className="settings-action" onClick={() => openPhotoEditor('link')}><Link2 size={15} /> Use image link</button>
            </div>
          </div>

          {photoEditorOpen && <section className="settings-photo-editor" aria-label="Profile image editor">
            <div className="settings-photo-editor-head">
              <div><span className="settings-section-kicker">Profile image</span><h3>Choose how to add your photo</h3></div>
              <button type="button" className="settings-photo-close" onClick={closePhotoEditor} aria-label="Close profile image editor"><X size={17} /></button>
            </div>
            <div className="settings-photo-tabs" role="tablist" aria-label="Profile image source">
              <button type="button" role="tab" aria-selected={photoMode === 'upload'} className={photoMode === 'upload' ? 'is-active' : ''} onClick={() => { setPhotoMode('upload'); setPhotoError(''); }}><ImageUp size={15} /> Upload</button>
              <button type="button" role="tab" aria-selected={photoMode === 'link'} className={photoMode === 'link' ? 'is-active' : ''} onClick={() => { setPhotoMode('link'); setPhotoDraft(user?.image_url?.startsWith('https://') ? user.image_url : ''); setPhotoError(''); }}><Link2 size={15} /> Image link</button>
            </div>
            <div className="settings-photo-workspace">
              <div className={`settings-photo-preview${photoDraft ? ' has-image' : ''}`}>
                {photoDraft ? <img src={photoDraft} alt="Profile preview" onError={() => setPhotoError('This image cannot be loaded. Check the file or link.')} /> : <User size={26} />}
              </div>
              {photoMode === 'upload' ? <div className="settings-photo-source">
                <strong>Upload from your device</strong>
                <p>Your image is stored securely with your account.</p>
                <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={choosePhoto} hidden />
                <button type="button" className="settings-action" onClick={() => fileInputRef.current?.click()}><ImageUp size={15} /> Choose image</button>
              </div> : <label className="settings-photo-source settings-photo-link">
                <strong>Paste an image link</strong>
                <span>Use a public HTTPS link to an image.</span>
                <div><Link2 size={15} /><input type="url" value={photoDraft} onChange={(event) => updatePhotoLink(event.target.value)} placeholder="https://example.com/photo.jpg" autoFocus /></div>
              </label>}
            </div>
            {photoError && <p className="settings-photo-error" role="alert">{photoError}</p>}
            <footer className="settings-photo-actions">
              {user?.image_url && <button type="button" className="settings-photo-remove" onClick={() => savePhoto(null)} disabled={photoSaving}><Trash2 size={15} /> Remove image</button>}
              <button type="button" className="settings-action" onClick={closePhotoEditor}>Cancel</button>
              <button type="button" className="settings-action settings-action-primary" onClick={() => savePhoto()} disabled={photoSaving || !photoDraft || Boolean(photoError)}><Check size={15} /> {photoSaving ? 'Saving…' : 'Save image'}</button>
            </footer>
          </section>}

          <div className="settings-profile-grid">
            <label>Full name<input type="text" className="input" value={user?.full_name || ''} readOnly /></label>
            <label>Email address<input type="email" className="input" value={user?.email || ''} readOnly /></label>
            <label>Department / workspace<input type="text" className="input" value={user?.workspace_name || user?.institute_name || (user?.workspace_type === 'institution' ? 'Institution' : user?.workspace_type === 'business' ? 'Business' : 'Personal')} readOnly /></label>
            <label>Timezone<input type="text" className="input" value={Intl.DateTimeFormat().resolvedOptions().timeZone} readOnly /></label>
          </div>
          <div className="settings-section-footer">
            <p>Identity information comes from your verified Puchoo.si profile.</p>
            <ChangeEmailPanel />
          </div>
        </section>

        <section className="settings-section settings-history" aria-labelledby="session-history-title">
          <div className="settings-history-icon"><HistoryIcon size={19} /></div>
          <div>
            <span className="settings-section-kicker">Workspace records</span>
            <h2 id="session-history-title">Session &amp; history</h2>
            <p>Review queries, inspect generated SQL, and manage the active workspace record.</p>
          </div>
          <button className="settings-action" onClick={() => navigate('/history')}>Manage history <span aria-hidden="true">↗</span></button>
        </section>
      </div>
    </div>
  );
}
