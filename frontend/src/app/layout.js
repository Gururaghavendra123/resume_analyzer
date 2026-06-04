import './globals.css';
import Link from 'next/link';

export const metadata = {
  title: 'Resume & JD Analyzer — AI-Powered Semantic Matching',
  description:
    'Semantically match resumes to job descriptions with explainable scores. ML-powered matching engine using transformer embeddings and section-weighted scoring.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        {/* ── Navigation ─────────────────────────────── */}
        <nav className="navbar">
          <div className="navbar-inner">
            <Link href="/" className="navbar-brand">
              <span className="logo-icon">⚡</span>
              ResuMatch AI
            </Link>
            <div className="navbar-links">
              <Link href="/">Dashboard</Link>
              <Link href="/resumes">Resumes</Link>
              <Link href="/jobs">Job Descriptions</Link>
              <Link href="/match">Match</Link>
            </div>
          </div>
        </nav>

        {/* ── Main Content ───────────────────────────── */}
        <main className="app-container">
          {children}
        </main>
      </body>
    </html>
  );
}
