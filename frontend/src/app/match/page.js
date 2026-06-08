'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { listJDs, runMatch, getMatchResults } from '@/api/client';

// ── Radar / Spider Chart (pure SVG, no library needed) ──────────
function RadarChart({ scores, size = 160 }) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.38;
  const labels = ['Skills', 'Exp', 'Edu', 'Projects'];
  const values = [
    scores.skills ?? 0,
    scores.experience ?? 0,
    scores.education ?? 0,
    scores.projects ?? 0,
  ];
  const n = labels.length;
  const angleStep = (2 * Math.PI) / n;
  const startAngle = -Math.PI / 2;

  const toXY = (angle, radius) => ({
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle),
  });

  // Axis endpoints
  const axes = Array.from({ length: n }, (_, i) => toXY(startAngle + i * angleStep, r));

  // Grid rings
  const rings = [0.25, 0.5, 0.75, 1.0];

  // Data polygon
  const dataPoints = values.map((v, i) => toXY(startAngle + i * angleStep, r * v));
  const dataPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + ' Z';

  return (
    <svg width={size} height={size} style={{ overflow: 'visible' }}>
      {/* Grid rings */}
      {rings.map((ring) => {
        const pts = Array.from({ length: n }, (_, i) => toXY(startAngle + i * angleStep, r * ring));
        const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + ' Z';
        return <path key={ring} d={d} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="1" />;
      })}

      {/* Axis lines */}
      {axes.map((end, i) => (
        <line key={i} x1={cx} y1={cy} x2={end.x.toFixed(1)} y2={end.y.toFixed(1)}
          stroke="rgba(255,255,255,0.12)" strokeWidth="1" />
      ))}

      {/* Data area */}
      <path d={dataPath} fill="rgba(99,102,241,0.25)" stroke="#6366f1" strokeWidth="2"
        style={{ filter: 'drop-shadow(0 0 6px rgba(99,102,241,0.5))' }} />

      {/* Data dots */}
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x.toFixed(1)} cy={p.y.toFixed(1)} r="3.5"
          fill="#818cf8" stroke="#1e293b" strokeWidth="1.5" />
      ))}

      {/* Labels */}
      {axes.map((end, i) => {
        const labelPt = toXY(startAngle + i * angleStep, r + 18);
        return (
          <text key={i} x={labelPt.x.toFixed(1)} y={labelPt.y.toFixed(1)}
            textAnchor="middle" dominantBaseline="middle"
            fontSize="9" fill="#94a3b8" fontFamily="Inter,sans-serif" fontWeight="600">
            {labels[i]}
          </text>
        );
      })}

      {/* Value labels at data points */}
      {dataPoints.map((p, i) => (
        <text key={i} x={(p.x + (p.x > cx ? 6 : p.x < cx ? -6 : 0)).toFixed(1)}
          y={(p.y + (p.y > cy ? 8 : -8)).toFixed(1)}
          textAnchor="middle" fontSize="8" fill="#6366f1" fontFamily="Inter,sans-serif" fontWeight="700">
          {Math.round(values[i] * 100)}%
        </text>
      ))}
    </svg>
  );
}

// ── Animated Counter ─────────────────────────────────────────────
function AnimatedScore({ target, duration = 1000 }) {
  const [current, setCurrent] = useState(0);
  const startRef = useRef(null);
  const rafRef = useRef(null);

  useEffect(() => {
    startRef.current = performance.now();
    const animate = (now) => {
      const elapsed = now - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const ease = 1 - Math.pow(1 - progress, 3);
      setCurrent(Math.round(target * ease));
      if (progress < 1) rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);

  return current;
}

// ── Step Progress Bar (shows current matching stage) ─────────────
function MatchProgressBar({ step }) {
  const steps = [
    { id: 'extracting',  label: 'Extracting JD vectors',  icon: '🔍' },
    { id: 'searching',   label: 'ANN vector search',       icon: '🔎' },
    { id: 'scoring',     label: 'Scoring candidates',      icon: '📊' },
    { id: 'explaining',  label: 'Generating insights',     icon: '💡' },
    { id: 'storing',     label: 'Saving results',          icon: '💾' },
  ];
  const currentIdx = steps.findIndex(s => s.id === step);

  return (
    <div style={{ padding: '24px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
        {steps.map((s, i) => {
          const done = i < currentIdx;
          const active = i === currentIdx;
          return (
            <div key={s.id} style={{ display: 'flex', alignItems: 'center', flex: i < steps.length - 1 ? 1 : 'none' }}>
              <div style={{
                width: 40, height: 40, borderRadius: '50%', flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '1rem',
                background: done ? '#10b981' : active ? 'rgba(99,102,241,0.3)' : 'rgba(255,255,255,0.05)',
                border: active ? '2px solid #6366f1' : done ? '2px solid #10b981' : '2px solid rgba(255,255,255,0.1)',
                boxShadow: active ? '0 0 16px rgba(99,102,241,0.4)' : 'none',
                animation: active ? 'pulse 1.5s ease-in-out infinite' : 'none',
                transition: 'all 0.4s ease',
              }}>
                {done ? '✓' : s.icon}
              </div>
              {i < steps.length - 1 && (
                <div style={{
                  flex: 1, height: 2, margin: '0 4px',
                  background: done ? '#10b981' : 'rgba(255,255,255,0.08)',
                  transition: 'background 0.5s ease',
                }} />
              )}
            </div>
          );
        })}
      </div>
      <div style={{ display: 'flex', marginTop: 8 }}>
        {steps.map((s, i) => {
          const active = i === currentIdx;
          return (
            <div key={s.id} style={{ flex: i < steps.length - 1 ? 1 : 'none', textAlign: 'center' }}>
              <div style={{ fontSize: '0.65rem', color: active ? '#818cf8' : '#475569', fontWeight: active ? 700 : 400, transition: 'all 0.3s' }}>
                {s.label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Skill Pill ───────────────────────────────────────────────────
function SkillPill({ name, type }) {
  const colors = {
    matched: { bg: 'rgba(16,185,129,0.15)', color: '#34d399', border: 'rgba(16,185,129,0.25)' },
    partial:  { bg: 'rgba(245,158,11,0.15)', color: '#fbbf24', border: 'rgba(245,158,11,0.25)' },
    missing:  { bg: 'rgba(239,68,68,0.15)',  color: '#f87171', border: 'rgba(239,68,68,0.25)' },
  }[type];
  const icon = { matched: '✓', partial: '~', missing: '✗' }[type];
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 10px', borderRadius: 100, fontSize: '0.72rem', fontWeight: 600,
      background: colors.bg, color: colors.color, border: `1px solid ${colors.border}`,
      margin: '2px',
    }}>
      {icon} {name}
    </span>
  );
}

// ── Main Page ────────────────────────────────────────────────────
export default function MatchPage() {
  const [jds, setJds] = useState([]);
  const [selectedJd, setSelectedJd] = useState('');
  const [topK, setTopK] = useState(10);
  const [domainFilter, setDomainFilter] = useState('');
  const [running, setRunning] = useState(false);
  const [matchStep, setMatchStep] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [results, setResults] = useState(null);
  const [toast, setToast] = useState(null);
  const [expandedCard, setExpandedCard] = useState(null);
  const pollRef = useRef(null);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 5000);
  }, []);

  useEffect(() => {
    listJDs().then(setJds).catch(() => {});
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, []);

  const STEP_SEQUENCE = ['extracting', 'searching', 'scoring', 'explaining', 'storing'];

  // Simulate step progression during polling (since we don't have true SSE yet)
  const simulateProgress = useCallback(() => {
    let i = 0;
    const advance = () => {
      if (i < STEP_SEQUENCE.length) {
        setMatchStep(STEP_SEQUENCE[i]);
        i++;
        pollRef.current = setTimeout(advance, 4000);
      }
    };
    advance();
  }, []);

  const handleRunMatch = async () => {
    if (!selectedJd) { showToast('Select a Job Description first', 'error'); return; }
    if (pollRef.current) clearTimeout(pollRef.current);
    setRunning(true);
    setResults(null);
    setMatchStep('extracting');

    try {
      const filters = {};
      if (domainFilter) filters.domain = domainFilter;
      const res = await runMatch(selectedJd, topK, filters);
      setJobId(res.job_id);
      showToast('Match job started!');
      simulateProgress();
      pollResults(res.job_id);
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Failed to start match job';
      showToast(`❌ ${msg}`, 'error');
      setRunning(false);
      setMatchStep(null);
    }
  };

  const pollResults = useCallback(async (jid) => {
    const maxAttempts = 80;
    let attempts = 0;

    const poll = async () => {
      try {
        const res = await getMatchResults(jid);
        if (res.status === 'completed') {
          if (pollRef.current) clearTimeout(pollRef.current);
          setMatchStep('storing');
          setTimeout(() => {
            setResults(res);
            setRunning(false);
            setMatchStep(null);
            showToast(`✅ Match complete! ${res.results_count} candidates ranked`);
          }, 800);
          return;
        }
        if (res.status === 'failed') {
          if (pollRef.current) clearTimeout(pollRef.current);
          const errMsg = res.error || 'Unknown error';
          showToast(`❌ Match failed: ${errMsg}`, 'error');
          setRunning(false);
          setMatchStep(null);
          return;
        }
        attempts++;
        if (attempts < maxAttempts) {
          pollRef.current = setTimeout(poll, 3000);
        } else {
          showToast('⏱ Match timed out — try again', 'error');
          setRunning(false);
          setMatchStep(null);
        }
      } catch {
        attempts++;
        if (attempts < maxAttempts) pollRef.current = setTimeout(poll, 3000);
      }
    };
    poll();
  }, [showToast]);

  const handleDownloadPdf = async () => {
    if (!jobId) return;
    try {
      const a = document.createElement('a');
      a.href = `http://127.0.0.1:8000/api/match/export/${jobId}/pdf`;
      a.download = `match_report_${jobId.slice(0, 8)}.pdf`;
      a.click();
      showToast('📄 Downloading PDF report...');
    } catch {
      showToast('Failed to download PDF', 'error');
    }
  };

  const getGradeClass = (grade) => `grade-${grade.toLowerCase()}`;

  const gradeLabel = (grade) => ({
    A: 'Excellent Match', B: 'Strong Match', C: 'Moderate Match',
    D: 'Weak Match', F: 'Poor Match',
  }[grade] || grade);

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1>Match Analysis</h1>
        <p>AI-powered resume ranking with 4-tier skill matching and ontology inference</p>
      </div>

      {/* ── Config Card ──────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <h2 className="card-title">⚡ Run Match</h2>
          {results && (
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={handleDownloadPdf} className="btn btn-secondary btn-sm" id="btn-download-pdf">
                📄 Export PDF
              </button>
              <button onClick={() => { setResults(null); setJobId(null); }}
                className="btn btn-secondary btn-sm" id="btn-clear-results">
                Clear
              </button>
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 110px 200px auto', gap: 12, alignItems: 'end' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 6 }}>
              Job Description
            </label>
            <select id="select-jd" value={selectedJd} onChange={e => setSelectedJd(e.target.value)}
              style={{ width: '100%', padding: '10px 12px', background: 'var(--bg-glass)', border: '1px solid var(--border-medium)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontFamily: 'var(--font-family)', fontSize: '0.875rem' }}>
              <option value="">Select a JD...</option>
              {jds.map(jd => (
                <option key={jd.jd_id} value={jd.jd_id}>
                  {jd.title || jd.jd_id.slice(0, 12)} ({jd.level})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 6 }}>Top K</label>
            <input id="input-topk" type="number" value={topK} onChange={e => setTopK(parseInt(e.target.value) || 10)}
              min={1} max={100}
              style={{ width: '100%', padding: '10px 12px', background: 'var(--bg-glass)', border: '1px solid var(--border-medium)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontFamily: 'var(--font-family)', fontSize: '0.875rem' }} />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 6 }}>Domain Filter</label>
            <input id="input-domain" type="text" value={domainFilter} onChange={e => setDomainFilter(e.target.value)}
              placeholder="e.g. fintech"
              style={{ width: '100%', padding: '10px 12px', background: 'var(--bg-glass)', border: '1px solid var(--border-medium)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontFamily: 'var(--font-family)', fontSize: '0.875rem' }} />
          </div>

          <button id="btn-run-match" className="btn btn-primary" onClick={handleRunMatch}
            disabled={running || !selectedJd} style={{ height: 42 }}>
            {running
              ? <><div className="spinner" style={{ width: 16, height: 16, borderWidth: 2, margin: 0 }} />Matching...</>
              : '🚀 Run Match'}
          </button>
        </div>
      </div>

      {/* ── Progress State ───────────────────────────────────── */}
      {running && matchStep && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-header">
            <h2 className="card-title">🔄 Processing</h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              AI pipeline running...
            </span>
          </div>
          <MatchProgressBar step={matchStep} />
          <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: 4 }}>
            Embedding → ANN search → 4-tier scoring → LLM explanation
          </p>
        </div>
      )}

      {/* ── Results ──────────────────────────────────────────── */}
      {results && results.results && (
        <div className="fade-in">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Match Results</h2>
            <span className="tag tag-matched">{results.results_count} candidates</span>
            {jobId && (
              <button onClick={handleDownloadPdf} className="btn btn-secondary btn-sm" id="btn-pdf-results">
                📄 Download PDF Report
              </button>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {results.results.map((match, i) => {
              const isExpanded = expandedCard === i;
              const radarScores = {
                skills:     match.skills_score?.score ?? 0,
                experience: match.experience_score?.score ?? 0,
                education:  match.education_score?.score ?? 0,
                projects:   match.projects_score?.score ?? 0,
              };
              return (
                <div key={i} className="card" style={{ padding: 20, cursor: 'pointer', transition: 'all 0.3s ease' }}
                  onClick={() => setExpandedCard(isExpanded ? null : i)}>

                  {/* ── Top Row ─────────────────────────── */}
                  <div style={{ display: 'flex', gap: 24, alignItems: 'start' }}>

                    {/* Rank badge */}
                    <div style={{
                      width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
                      background: i === 0 ? 'linear-gradient(135deg,#f59e0b,#fbbf24)' : i === 1 ? 'linear-gradient(135deg,#94a3b8,#cbd5e1)' : i === 2 ? 'linear-gradient(135deg,#b45309,#d97706)' : 'rgba(255,255,255,0.1)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '0.85rem', fontWeight: 800, color: i < 3 ? '#0a0e1a' : 'var(--text-muted)',
                    }}>#{i + 1}</div>

                    {/* Score circle */}
                    <div style={{ textAlign: 'center', flexShrink: 0 }}>
                      <div className="score-circle" style={{ width: 80, height: 80 }}>
                        <span className="score-value" style={{ fontSize: '1.5rem' }}>
                          <AnimatedScore target={Math.round(match.overall_score)} duration={900 + i * 100} />
                        </span>
                        <span className="score-label" style={{ marginTop: 2 }}>/100</span>
                      </div>
                      <div className={`grade-badge ${getGradeClass(match.grade)}`} style={{ margin: '8px auto 0' }}>
                        {match.grade}
                      </div>
                    </div>

                    {/* Info */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 8 }}>
                        <div>
                          <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>Candidate #{i + 1}</h3>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
                            {gradeLabel(match.grade)} · ID: {match.resume_id?.slice(0, 12)}...
                          </div>
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
                          {isExpanded ? '▲ collapse' : '▼ expand'}
                        </span>
                      </div>

                      {/* Score bars */}
                      <div className="section-scores">
                        {[
                          { name: 'Skills',     score: match.skills_score },
                          { name: 'Experience', score: match.experience_score },
                          { name: 'Education',  score: match.education_score },
                          { name: 'Projects',   score: match.projects_score },
                        ].map(section => {
                          const pct = section.score?.score * 100 || 0;
                          const colorClass = pct >= 70 ? 'high' : pct >= 40 ? 'medium' : 'low';
                          return (
                            <div key={section.name} className="section-score-item">
                              <div className="section-score-header">
                                <span className="section-score-name">{section.name}</span>
                                <span className="section-score-value">{Math.round(pct)}%</span>
                              </div>
                              <div className="score-bar">
                                <div className={`score-bar-fill ${colorClass}`} style={{ width: `${pct}%` }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Radar chart */}
                    <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <RadarChart scores={radarScores} size={150} />
                    </div>
                  </div>

                  {/* ── Expanded Detail ──────────────────── */}
                  {isExpanded && (
                    <div className="fade-in" style={{ marginTop: 20, borderTop: '1px solid var(--border-subtle)', paddingTop: 16 }}>

                      {/* Skill pills */}
                      <div style={{ marginBottom: 14 }}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 8 }}>
                          Skill Breakdown
                        </div>
                        <div className="tags-container" style={{ gap: 4 }}>
                          {(match.skills_score?.matched || []).map(s => <SkillPill key={s} name={s} type="matched" />)}
                          {(match.skills_score?.partial  || []).map(s => <SkillPill key={s} name={s.split(' (')[0]} type="partial" />)}
                          {(match.skills_score?.missing  || []).map(s => <SkillPill key={s} name={s} type="missing" />)}
                        </div>
                      </div>

                      {/* Red flags */}
                      {match.red_flags?.length > 0 && (
                        <div style={{ marginBottom: 14, padding: 12, background: 'rgba(239,68,68,0.05)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(239,68,68,0.15)' }}>
                          <span style={{ fontSize: '0.8rem', color: '#f87171', fontWeight: 700 }}>⚠ Red Flags</span>
                          <ul style={{ marginTop: 6, paddingLeft: 16 }}>
                            {match.red_flags.map((f, j) => (
                              <li key={j} style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 3 }}>{f}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Recommendation */}
                      {match.recommendation && (
                        <div style={{ padding: '12px 16px', background: 'rgba(99,102,241,0.06)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(99,102,241,0.15)', borderLeft: '3px solid #6366f1' }}>
                          <div style={{ fontSize: '0.8rem', color: '#818cf8', fontWeight: 700, marginBottom: 6 }}>💡 AI Recommendation</div>
                          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                            {match.recommendation}
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Toast ─────────────────────────────────────────── */}
      {toast && (
        <div className={`toast ${toast.type}`}>
          {toast.type === 'success' ? '✓' : '✗'} {toast.message}
        </div>
      )}
    </div>
  );
}
