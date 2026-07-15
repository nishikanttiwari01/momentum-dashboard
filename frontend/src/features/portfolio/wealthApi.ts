import axios from 'axios';
import type {
  GoalConfigurationUpdate,
  FamilyPlanResponse,
  FamilyPlanUpdate,
  ImportCommitResult,
  ImportPreview,
  PrimaryGoalResponse,
  WealthSummary,
} from './wealthTypes';

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

const PRIMARY_GOAL_URL = '/api/v1/wealth-portfolio/goals/primary';

export async function fetchPrimaryGoal(): Promise<PrimaryGoalResponse> {
  return (await axios.get<PrimaryGoalResponse>(PRIMARY_GOAL_URL)).data;
}

export async function updatePrimaryGoal(
  configuration: GoalConfigurationUpdate,
): Promise<PrimaryGoalResponse> {
  return (await axios.put<PrimaryGoalResponse>(PRIMARY_GOAL_URL, configuration)).data;
}

const FAMILY_PLAN_URL = '/api/v1/wealth-portfolio/goals/family-plan';

export async function fetchFamilyPlan(): Promise<FamilyPlanResponse> {
  return (await axios.get<FamilyPlanResponse>(FAMILY_PLAN_URL)).data;
}

export async function updateFamilyPlan(payload: FamilyPlanUpdate): Promise<FamilyPlanResponse> {
  return (await axios.put<FamilyPlanResponse>(FAMILY_PLAN_URL, payload)).data;
}

export async function restoreFamilyPlanDefaults(): Promise<FamilyPlanResponse> {
  return (await axios.post<FamilyPlanResponse>(`${FAMILY_PLAN_URL}/restore-defaults`)).data;
}
