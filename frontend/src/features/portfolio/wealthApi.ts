import axios from 'axios';
import type { ImportCommitResult, ImportPreview, WealthSummary } from './wealthTypes';

export async function previewWorkbook(file: File): Promise<ImportPreview> {
  const form = new FormData();
  form.append('workbook', file);
  return (await axios.post<ImportPreview>('/api/v1/wealth-portfolio/imports/preview', form)).data;
}

export async function commitWorkbook(token: string): Promise<ImportCommitResult> {
  return (await axios.post<ImportCommitResult>(`/api/v1/wealth-portfolio/imports/${token}/commit`)).data;
}

export async function fetchWealthSummary(): Promise<WealthSummary> {
  return (await axios.get<WealthSummary>('/api/v1/wealth-portfolio/summary')).data;
}
