'use client';

import { useEffect, useState, useCallback } from 'react';
import { listJDs, uploadJD, deleteJD } from '@/api/client';

export default function JobsPage() {
  const [jds, setJds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [showTextInput, setShowTextInput] = useState(false);
  const [jdText, setJdText] = useState('');
  const [dragging, setDragging] = useState(false);
  const [toast, setToast] = useState(null);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  const fetchJDs = useCallback(async () => {
    try {
      const data = await listJDs();
      setJds(data);
    } catch {
      showToast('Failed to load JDs', 'error');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchJDs();
  }, [fetchJDs]);

  const handleFileUpload = async (files) => {
    setUploading(true);
    for (const file of files) {
      try {
        await uploadJD(file);
        showToast('JD uploaded successfully!');
      } catch {
        showToast('Upload failed', 'error');
      }
    }
    setUploading(false);
    let attempts = 0;
    const poll = async () => {
      await fetchJDs();
      attempts++;
      if (attempts < 10) {
        setTimeout(poll, 3000);
      }
    };
    setTimeout(poll, 2000);
  };

  const handleTextSubmit = async () => {
    if (!jdText.trim()) return;
    setUploading(true);
    try {
      // Create a text file from the pasted text
      const blob = new Blob([jdText], { type: 'text/plain' });
      const file = new File([blob], 'job_description.txt', { type: 'text/plain' });
      await uploadJD(file);
      showToast('JD submitted successfully!');
      setJdText('');
      setShowTextInput(false);
    } catch {
      showToast('Submission failed', 'error');
    }
    setUploading(false);
    let attempts = 0;
    const poll = async () => {
      await fetchJDs();
      attempts++;
      if (attempts < 10) {
        setTimeout(poll, 3000);
      }
    };
    setTimeout(poll, 2000);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) handleFileUpload(files);
  };

  const handleDelete = async (jdId) => {
    try {
      await deleteJD(jdId);
      showToast('JD deleted');
      fetchJDs();
    } catch {
      showToast('Delete failed', 'error');
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1>Job Descriptions</h1>
        <p>Upload or paste job descriptions for matching</p>
      </div>

      {/* ── Upload Options ─────────────────────────── */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
        <button
          className={`btn ${!showTextInput ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setShowTextInput(false)}
        >
          📁 Upload File
        </button>
        <button
          className={`btn ${showTextInput ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setShowTextInput(true)}
        >
          ✍️ Paste Text
        </button>
      </div>

      {/* ── File Upload Zone ───────────────────────── */}
      {!showTextInput ? (
        <div
          className={`upload-zone ${dragging ? 'dragging' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => document.getElementById('jd-file-input').click()}
          style={{ marginBottom: '32px' }}
        >
          <input
            id="jd-file-input"
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={(e) => handleFileUpload(Array.from(e.target.files || []))}
            style={{ display: 'none' }}
          />
          <div className="upload-icon">💼</div>
          {uploading ? (
            <>
              <h3>Uploading...</h3>
              <div className="spinner" style={{ margin: '8px auto' }}></div>
            </>
          ) : (
            <>
              <h3>Drop JD file here or click to upload</h3>
              <p>Supports PDF, DOCX, and TXT files</p>
            </>
          )}
        </div>
      ) : (
        /* ── Text Input ──────────────────────────── */
        <div style={{ marginBottom: '32px' }}>
          <textarea
            className="textarea"
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            placeholder="Paste the full job description here..."
            style={{ marginBottom: '12px' }}
          />
          <button
            className="btn btn-primary"
            onClick={handleTextSubmit}
            disabled={uploading || !jdText.trim()}
          >
            {uploading ? 'Submitting...' : '🚀 Submit JD'}
          </button>
        </div>
      )}

      {/* ── JD List ────────────────────────────────── */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">Job Descriptions ({jds.length})</h2>
        </div>

        {loading ? (
          <div className="loading">
            <div className="spinner"></div>
            Loading...
          </div>
        ) : jds.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">💼</div>
            <h3>No job descriptions yet</h3>
            <p>Upload a JD or paste text to get started</p>
          </div>
        ) : (
          <div className="data-list">
            {jds.map((jd) => (
              <div key={jd.jd_id} className="data-item">
                <div className="data-item-info">
                  <span className="data-item-title">{jd.title || `JD ${jd.jd_id.slice(0, 8)}...`}</span>
                  <span className="data-item-meta">
                    <span>📊 {jd.level}</span>
                    <span>📋 {jd.requirements_count} requirements</span>
                    {jd.uploaded_at && (
                      <span>⏰ {new Date(jd.uploaded_at).toLocaleDateString()}</span>
                    )}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  {jd.domain && <span className="tag tag-domain">{jd.domain}</span>}
                  <button
                    className="btn btn-danger btn-sm"
                    onClick={(e) => { e.stopPropagation(); handleDelete(jd.jd_id); }}
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {toast && (
        <div className={`toast ${toast.type}`}>
          {toast.type === 'success' ? '✓' : '✗'} {toast.message}
        </div>
      )}
    </div>
  );
}
