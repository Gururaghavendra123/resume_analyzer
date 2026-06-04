/**
 * API client for the Resume & JD Analyzer backend.
 * 
 * Centralized Axios instance with base URL configuration.
 * All API calls go through this module.
 */

import axios from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,   // 30 seconds — allow for cold starts
  headers: {
    'Accept': 'application/json',
  },
});

// ── Resume APIs ────────────────────────────────────────────────

export async function uploadResume(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await api.post('/api/resume/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function bulkUploadResumes(files) {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  const res = await api.post('/api/resume/bulk-upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function getResume(resumeId) {
  const res = await api.get(`/api/resume/${resumeId}`);
  return res.data;
}

export async function listResumes(retries = 1) {
  try {
    const res = await api.get('/api/resume/');
    return res.data;
  } catch (err) {
    if (retries > 0) {
      await new Promise(r => setTimeout(r, 2000));
      return listResumes(retries - 1);
    }
    throw err;
  }
}

export async function deleteResume(resumeId) {
  const res = await api.delete(`/api/resume/${resumeId}`);
  return res.data;
}

// ── JD APIs ────────────────────────────────────────────────────

export async function uploadJD(fileOrText) {
  if (typeof fileOrText === 'string') {
    const res = await api.post('/api/jd/upload', fileOrText, {
      headers: { 'Content-Type': 'application/json' },
      params: {},
    });
    return res.data;
  }
  const formData = new FormData();
  formData.append('file', fileOrText);
  const res = await api.post('/api/jd/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function getJD(jdId) {
  const res = await api.get(`/api/jd/${jdId}`);
  return res.data;
}

export async function listJDs(retries = 1) {
  try {
    const res = await api.get('/api/jd/');
    return res.data;
  } catch (err) {
    if (retries > 0) {
      await new Promise(r => setTimeout(r, 2000));
      return listJDs(retries - 1);
    }
    throw err;
  }
}

export async function deleteJD(jdId) {
  const res = await api.delete(`/api/jd/${jdId}`);
  return res.data;
}

// ── Match APIs ─────────────────────────────────────────────────

export async function runMatch(jdId, topK = 10, filters = {}) {
  const res = await api.post('/api/match/run', {
    jd_id: jdId,
    top_k: topK,
    filters: Object.keys(filters).length > 0 ? filters : null,
  });
  return res.data;
}

export async function getMatchResults(jobId) {
  const res = await api.get(`/api/match/results/${jobId}`);
  return res.data;
}

export async function getSpecificMatch(resumeId, jdId) {
  const res = await api.get(`/api/match/detail/${resumeId}/${jdId}`);
  return res.data;
}

export async function exportMatchResults(jobId) {
  const res = await api.get(`/api/match/export/${jobId}`);
  return res.data;
}

// ── Health ──────────────────────────────────────────────────────

export async function healthCheck() {
  const res = await api.get('/health');
  return res.data;
}

export default api;
