import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export async function readApiResponse(res: Response) {
  const text = await res.text();
  if (!text) return { success: false, detail: res.statusText || "Empty response" };

  try {
    return JSON.parse(text);
  } catch {
    return {
      success: false,
      detail: res.ok
        ? "Server returned an invalid JSON response."
        : `API request failed (${res.status}): ${text.slice(0, 160)}`
    };
  }
}
