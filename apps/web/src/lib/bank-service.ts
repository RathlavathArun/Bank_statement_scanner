/**
 * Bank management API client
 * Provides TypeScript-safe methods for bank template operations
 */

export interface Bank {
  id: string;
  code: string;
  name: string;
  extraction_type: string;
  template_path: string;
  is_active: boolean;
}

export interface BankTemplate extends Bank {
  template?: Record<string, unknown>;
}

export interface BankUploadResponse {
  id: string;
  bank_code: string;
  bank_name: string;
  created_at: string;
}

const API_BASE = "/api/admin/banks";

async function getAuthHeader(): Promise<Record<string, string>> {
  const token = localStorage.getItem("access_token") || localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleApiError(response: Response) {
  if (response.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("admin_verified");
      window.location.href = "/manage/login";
    }
  }
  const data = await response.json().catch(() => ({}));
  throw new Error(data.detail || data.message || `API Error: ${response.status}`);
}

export async function listBanks(): Promise<Bank[]> {
  const response = await fetch(API_BASE, {
    headers: await getAuthHeader(),
  });

  if (!response.ok) {
    await handleApiError(response);
  }

  const data = await response.json();
  return data.data?.banks || [];
}

export async function getBank(bankCode: string): Promise<BankTemplate> {
  const response = await fetch(`${API_BASE}/${bankCode}`, {
    headers: await getAuthHeader(),
  });

  if (!response.ok) {
    await handleApiError(response);
  }

  const data = await response.json();
  return data.data;
}

export async function uploadBank(
  file: File,
  bankCode?: string,
  bankName?: string
): Promise<BankUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (bankCode) formData.append("bank_code", bankCode);
  if (bankName) formData.append("bank_name", bankName);

  const response = await fetch(API_BASE, {
    method: "POST",
    headers: await getAuthHeader(),
    body: formData,
  });

  if (!response.ok) {
    await handleApiError(response);
  }

  const data = await response.json();
  return data.data;
}

export async function updateBank(
  bankCode: string,
  {
    file,
    bankName,
    description,
    isActive,
  }: {
    file?: File;
    bankName?: string;
    description?: string;
    isActive?: boolean;
  }
): Promise<BankTemplate> {
  const formData = new FormData();
  if (file) formData.append("file", file);
  if (bankName) formData.append("bank_name", bankName);
  if (description !== undefined) formData.append("description", description);
  if (isActive !== undefined) formData.append("is_active", isActive ? "true" : "false");

  const response = await fetch(`${API_BASE}/${bankCode}`, {
    method: "PATCH",
    headers: await getAuthHeader(),
    body: formData,
  });

  if (!response.ok) {
    await handleApiError(response);
  }

  const data = await response.json();
  return data.data;
}

export async function deleteBank(bankCode: string): Promise<void> {
  const response = await fetch(`${API_BASE}/${bankCode}`, {
    method: "DELETE",
    headers: await getAuthHeader(),
  });

  if (!response.ok) {
    await handleApiError(response);
  }
}

export async function downloadTemplate(bankCode: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/${bankCode}/download`, {
    headers: await getAuthHeader(),
  });

  if (!response.ok) {
    await handleApiError(response);
  }

  return response.blob();
}

export function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString("en-IN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
