'use client';

import { useEffect, useState, useCallback } from 'react';
import { listResumes, uploadResume, deleteResume } from '@/api/client';

export default function ResumesPage() {
  const [resumes, setResumes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [toast, setToast] = useState(null);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  const fetchResumes = useCallback(async () => {
    try {
      const data = await listResumes();
      setResumes(data);
    } catch {
      showToast('Failed to load resumes', 'error');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchResumes();
  }, [fetchResumes]);

  const handleUpload = async (files) => {
    setUploading(true);
    let successCount = 0;
    let failCount = 0;

    for (const file of files) {
      try {
        await uploadResume(file);
        successCount++;
      } catch {
        failCount++;
      }
    }

    if (successCount > 0) {
      showToast(`${successCount} resume(s) uploaded successfully!`);
    }
    if (failCount > 0) {
      showToast(`${failCount} upload(s) failed`, 'error');
    }

    setUploading(false);
    // Poll for results (up to 30s) since backend processes async
    let attempts = 0;
    const poll = async () => {
      await fetchResumes();
      attempts++;
      if (attempts < 10) {
        setTimeout(poll, 3000);
      }
    };
    setTimeout(poll, 2000);
  };

  const handleFileInput = (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) handleUpload(files);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) handleUpload(files);
  };

  const handleDelete = async (resumeId) => {
    try {
      await deleteResume(resumeId);
      showToast('Resume deleted');
      fetchResumes();
    } catch {
      showToast('Delete failed', 'error');
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1>Resumes</h1>
        <p>Upload and manage candidate resumes</p>
      </div>

      {/* ── Upload Zone ────────────────────────────── */}
      <div
        className={`upload-zone ${dragging ? 'dragging' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => document.getElementById('file-input').click()}
        style={{ marginBottom: '32px' }}
      >
        <input
          id="file-input"
          type="file"
          accept=".pdf,.docx,.txt"
          multiple
          onChange={handleFileInput}
          style={{ display: 'none' }}
        />
        <div className="upload-icon">📄</div>
        {uploading ? (
          <>
            <h3>Uploading...</h3>
            <div className="spinner" style={{ margin: '8px auto' }}></div>
          </>
        ) : (
          <>
            <h3>Drop resumes here or click to upload</h3>
            <p>Supports PDF, DOCX, and TXT files • Multiple files allowed</p>
          </>
        )}
      </div>

      {/* ── Resume List ────────────────────────────── */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">Uploaded Resumes ({resumes.length})</h2>
        </div>

        {loading ? (
          <div className="loading">
            <div className="spinner"></div>
            Loading resumes...
          </div>
        ) : resumes.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📄</div>
            <h3>No resumes uploaded yet</h3>
            <p>Drag and drop files above to get started</p>
          </div>
        ) : (
          <div className="data-list">
            {resumes.map((r) => (
              <div key={r.resume_id} className="data-item">
                <div className="data-item-info">
                  <span className="data-item-title">
                    {r.candidate_name || `Resume ${r.resume_id.slice(0, 8)}...`}
                  </span>
                  <span className="data-item-meta">
                    <span>🛠 {r.skills_count} skills</span>
                    <span>📅 {r.total_experience_months} months</span>
                    {r.uploaded_at && (
                      <span>⏰ {new Date(r.uploaded_at).toLocaleDateString()}</span>
                    )}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div className="tags-container">
                    {(r.domains || []).slice(0, 2).map((d) => (
                      <span key={d} className="tag tag-domain">{d}</span>
                    ))}
                  </div>
                  <button
                    className="btn btn-danger btn-sm"
                    onClick={(e) => { e.stopPropagation(); handleDelete(r.resume_id); }}
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Toast ──────────────────────────────────── */}
      {toast && (
        <div className={`toast ${toast.type}`}>
          {toast.type === 'success' ? '✓' : '✗'} {toast.message}
        </div>
      )}
    </div>
  );
}
