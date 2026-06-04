'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { listResumes, listJDs, healthCheck } from '@/api/client';

export default function DashboardPage() {
  const [resumes, setResumes] = useState([]);
  const [jds, setJds] = useState([]);
  const [apiStatus, setApiStatus] = useState('checking');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      // 1. Health check first
      let apiOk = false;
      try {
        await healthCheck();
        setApiStatus('connected');
        apiOk = true;
      } catch {
        setApiStatus('disconnected');
      }

      // 2. Only fetch data if API is actually up
      if (apiOk) {
        try {
          const [resumeData, jdData] = await Promise.allSettled([
            listResumes(),
            listJDs(),
          ]);
          if (resumeData.status === 'fulfilled') setResumes(resumeData.value);
          if (jdData.status === 'fulfilled') setJds(jdData.value);
        } catch {
          // Silent fail for dashboard stats
        }
      }

      setLoading(false);
    }
    fetchData();
  }, []);

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1>Dashboard</h1>
        <p>AI-powered resume matching at a glance</p>
      </div>

      {/* ── Stats Grid ─────────────────────────────── */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon purple">📄</div>
          <div>
            <div className="stat-value">{resumes.length}</div>
            <div className="stat-label">Resumes Uploaded</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon blue">💼</div>
          <div>
            <div className="stat-value">{jds.length}</div>
            <div className="stat-label">Job Descriptions</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon green">🔗</div>
          <div>
            <div className="stat-value">
              {apiStatus === 'connected' ? '✓' : '✗'}
            </div>
            <div className="stat-label">
              API {apiStatus === 'connected' ? 'Connected' : 'Disconnected'}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon orange">⚡</div>
          <div>
            <div className="stat-value">5</div>
            <div className="stat-label">AI Layers Active</div>
          </div>
        </div>
      </div>

      {/* ── Quick Actions ──────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '32px' }}>
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">📄 Upload Resume</h2>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '16px' }}>
            Upload PDF, DOCX, or TXT resumes for AI-powered analysis and matching.
          </p>
          <Link href="/resumes" className="btn btn-primary">
            Go to Resumes →
          </Link>
        </div>

        <div className="card">
          <div className="card-header">
            <h2 className="card-title">💼 Upload Job Description</h2>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '16px' }}>
            Add job descriptions and match them against your resume pool.
          </p>
          <Link href="/jobs" className="btn btn-primary">
            Go to Jobs →
          </Link>
        </div>
      </div>

      {/* ── Recent Resumes ─────────────────────────── */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <div className="card-header">
          <h2 className="card-title">Recent Resumes</h2>
          <Link href="/resumes" className="btn btn-secondary btn-sm">
            View All
          </Link>
        </div>

        {loading ? (
          <div className="loading">
            <div className="spinner"></div>
            Loading...
          </div>
        ) : resumes.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📄</div>
            <h3>No resumes yet</h3>
            <p>Upload your first resume to get started</p>
          </div>
        ) : (
          <div className="data-list">
            {resumes.slice(0, 5).map((r) => (
              <div key={r.resume_id} className="data-item">
                <div className="data-item-info">
                  <span className="data-item-title">
                    {r.candidate_name || `Resume ${r.resume_id.slice(0, 8)}...`}
                  </span>
                  <span className="data-item-meta">
                    <span>🛠 {r.skills_count} skills</span>
                    <span>📅 {r.total_experience_months} months exp</span>
                  </span>
                </div>
                <div className="tags-container">
                  {(r.domains || []).slice(0, 2).map((d) => (
                    <span key={d} className="tag tag-domain">{d}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Architecture Info ──────────────────────── */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">🏗️ System Architecture</h2>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '8px' }}>
          {[
            { name: 'Extraction', icon: '🔍', desc: 'Gemini LLM' },
            { name: 'Embedding', icon: '🧮', desc: 'BGE-large' },
            { name: 'Storage', icon: '💾', desc: 'Qdrant + PG' },
            { name: 'Scoring', icon: '📊', desc: 'Weighted' },
            { name: 'Explain', icon: '💡', desc: 'AI Reports' },
          ].map((layer, i) => (
            <div key={i} style={{
              textAlign: 'center',
              padding: '16px 8px',
              background: 'var(--bg-glass)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-subtle)',
            }}>
              <div style={{ fontSize: '1.5rem', marginBottom: '8px' }}>{layer.icon}</div>
              <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{layer.name}</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{layer.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
