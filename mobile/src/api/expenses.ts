
import { apiClient } from "./client";

export interface JobExpense {
  id: string | number;
  job_id: string | number;
  amount: number;
  currency?: string;
  category: string;
  description?: string;
  receipt_url?: string;
  status?: string;
  created_at?: string;
}

export interface CreateJobExpenseRequest {
  amount: number;
  currency?: string;
  category: string;
  description?: string;
  receipt_url?: string;
  occurred_at?: string;
}

export async function submitJobExpense(
  jobId: string | number,
  expense: CreateJobExpenseRequest
): Promise<JobExpense> {
  const safeJobId = encodeURIComponent(String(jobId));

  if (!Number.isFinite(expense.amount) || expense.amount <= 0) {
    throw new Error("Expense amount must be greater than zero.");
  }

  if (!expense.category.trim()) {
    throw new Error("Expense category is required.");
  }

  const response = await apiClient.post<JobExpense>(
    `/api/technician/jobs/${safeJobId}/expenses`,
    expense
  );

  return response.data;
}

export async function getJobExpenses(
  jobId: string | number
): Promise<JobExpense[]> {
  const safeJobId = encodeURIComponent(String(jobId));

  const response = await apiClient.get<JobExpense[]>(
    `/api/technician/jobs/${safeJobId}/expenses`
  );

  return response.data;
}
