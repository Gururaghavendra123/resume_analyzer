'use client';

import { useEffect, useState, useCallback } from 'react';
import { listJDs, runMatch, getMatchResults } from '@/api/client';

export default function MatchPage() {
  const [jds, setJds] = useState([]);
  const [selectedJd, setSelectedJd] = useState('');
  const [topK, setTopK] = useState(10);
  const [domainFilter, setDomainFilter] = useState('');
  const [running, setRunning] = useState(false);
  const [polling, setPolling] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [results, setResults] = useState(null);
  const [toast, setToast] = useState(null);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  useEffect(() => {
    listJDs().then(setJds).catch(() => {});
  }, []);

  const handleRunMatch = async () => {
    if (!selectedJd) {
      showToast('Select a Job Description first', 'error');
      return;
    }

    setRunning(true);
    setResults(null);

    try {
      const filters = {};
      if (domainFilter) filters.domain = domainFilter;

      const res = await runMatch(selectedJd, topK, filters);
      setJobId(res.job_id);
      showToast('Match job started! Polling for results...');
      pollResults(res.job_id);
    } catch {
      showToast('Failed to start match', 'error');
      setRunning(false);
    }
  };

  const pollResults = useCallback(async (jid) => {
    setPolling(true);
    const maxAttempts = 60;
    let attempts = 0;

    const poll = async () => {
      try {
        const res = await getMatchResults(jid);

        if (res.status === 'completed') {
          setResults(res);
          setRunning(false);
          setPolling(false);
          showToast(`Match complete! ${res.results_count} results found`);
          return;
        }

        if (res.status === 'failed') {
          showToast('Match failed: ' + (res.error || 'Unknown error'), 'error');
          setRunning(false);
          setPolling(false);
          return;
        }

        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 3000);
        } else {
          showToast('Match timed out', 'error');
          setRunning(false);
          setPolling(false);
        }
      } catch {
        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 3000);
        }
      }
    };

    poll();
  }, []);

  const getScoreColor = (score) => {
    if (score >= 70) return 'high';
    if (score >= 40) return 'medium';
    return 'low';
  };

  const getGradeClass = (grade) => {
    return `grade-${grade.toLowerCase()}`;
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1>Match Analysis</h1>
        <p>Match a job description against all uploaded resumes</p>
      </div>

      {/* ── Match Configuration ────────────────────── */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <div className="card-header">
          <h2 className="card-title">⚡ Run Match</h2>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px 200px auto', gap: '12px', alignItems: 'end' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
              Job Description
            </label>
            <select
              value={selectedJd}
              onChange={(e) => setSelectedJd(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                background: 'var(--bg-glass)',
                border: '1px solid var(--border-medium)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-family)',
                fontSize: '0.875rem',
              }}
            >
              <option value="">Select a JD...</option>
              {jds.map((jd) => (
                <option key={jd.jd_id} value={jd.jd_id}>
                  {jd.title || jd.jd_id.slice(0, 12)} ({jd.level})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
              Top K
            </label>
            <input
              type="number"
              value={topK}
              onChange={(e) => setTopK(parseInt(e.target.value) || 10)}
              min={1}
              max={100}
              style={{
                width: '100%',
                padding: '10px 12px',
                background: 'var(--bg-glass)',
                border: '1px solid var(--border-medium)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-family)',
                fontSize: '0.875rem',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
              Domain Filter (optional)
            </label>
            <input
              type="text"
              value={domainFilter}
              onChange={(e) => setDomainFilter(e.target.value)}
              placeholder="e.g. fintech"
              style={{
                width: '100%',
                padding: '10px 12px',
                background: 'var(--bg-glass)',
                border: '1px solid var(--border-medium)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-family)',
                fontSize: '0.875rem',
              }}
            />
          </div>

          <button
            className="btn btn-primary"
            onClick={handleRunMatch}
            disabled={running || !selectedJd}
            style={{ height: '42px' }}
          >
            {running ? (
              <><div className="spinner" style={{ width: '16px', height: '16px', borderWidth: '2px', margin: 0 }}></div> Matching...</>
            ) : (
              '🚀 Run Match'
            )}
          </button>
        </div>
      </div>

      {/* ── Polling State ──────────────────────────── */}
      {polling && (
        <div className="card" style={{ marginBottom: '24px', textAlign: 'center', padding: '32px' }}>
          <div className="spinner" style={{ margin: '0 auto 16px' }}></div>
          <p style={{ color: 'var(--text-secondary)' }}>
            Analyzing resumes... This may take a moment.
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
            Running: ANN search → Re-ranking → Scoring → Explanation
          </p>
        </div>
      )}

      {/* ── Results ────────────────────────────────── */}
      {results && results.results && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>
              Match Results
            </h2>
            <span className="tag tag-matched">
              {results.results_count} candidates
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {results.results.map((match, i) => (
              <div key={i} className="card" style={{ padding: '20px' }}>
                <div style={{ display: 'flex', gap: '24px', alignItems: 'start' }}>
                  {/* Score + Grade */}
                  <div style={{ textAlign: 'center', flexShrink: 0 }}>
                    <div className="score-circle" style={{ width: '80px', height: '80px' }}>
                      <span className="score-value" style={{ fontSize: '1.5rem' }}>
                        {Math.round(match.overall_score)}
                      </span>
                    </div>
                    <div className={`grade-badge ${getGradeClass(match.grade)}`} style={{ margin: '8px auto 0' }}>
                      {match.grade}
                    </div>
                  </div>

                  {/* Details */}
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                      <div>
                        <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>
                          Candidate #{i + 1}
                        </h3>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                          ID: {match.resume_id.slice(0, 12)}...
                        </span>
                      </div>
                    </div>

                    {/* Section Score Bars */}
                    <div className="section-scores">
                      {[
                        { name: 'Skills', score: match.skills_score },
                        { name: 'Experience', score: match.experience_score },
                        { name: 'Education', score: match.education_score },
                        { name: 'Projects', score: match.projects_score },
                      ].map((section) => (
                        <div key={section.name} className="section-score-item">
                          <div className="section-score-header">
                            <span className="section-score-name">{section.name}</span>
                            <span className="section-score-value">
                              {Math.round(section.score.score * 100)}%
                            </span>
                          </div>
                          <div className="score-bar">
                            <div
                              className={`score-bar-fill ${getScoreColor(section.score.score * 100)}`}
                              style={{ width: `${section.score.score * 100}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Tags */}
                    <div style={{ marginTop: '12px' }}>
                      <div className="tags-container">
                        {(match.skills_score.matched || []).slice(0, 5).map((s) => (
                          <span key={s} className="tag tag-matched">{s}</span>
                        ))}
                        {(match.skills_score.partial || []).slice(0, 3).map((s) => (
                          <span key={s} className="tag tag-partial">{s}</span>
                        ))}
                        {(match.skills_score.missing || []).slice(0, 3).map((s) => (
                          <span key={s} className="tag tag-missing">{s}</span>
                        ))}
                      </div>
                    </div>

                    {/* Red Flags */}
                    {match.red_flags && match.red_flags.length > 0 && (
                      <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(239,68,68,0.05)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(239,68,68,0.15)' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--danger-light)', fontWeight: 600 }}>⚠ Red Flags:</span>
                        <ul style={{ marginTop: '4px', paddingLeft: '16px' }}>
                          {match.red_flags.map((flag, j) => (
                            <li key={j} style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{flag}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Recommendation */}
                    {match.recommendation && (
                      <div style={{ marginTop: '12px', padding: '12px', background: 'var(--bg-glass)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--accent-primary-light)', fontWeight: 600 }}>💡 Recommendation:</span>
                        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '4px', lineHeight: '1.5' }}>
                          {match.recommendation}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {toast && (
        <div className={`toast ${toast.type}`}>
          {toast.type === 'success' ? '✓' : '✗'} {toast.message}
        </div>
      )}
    </div>
  );
}
