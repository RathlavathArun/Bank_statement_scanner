/**
 * TemplateReloadButton - Trigger template reload
 */
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { RefreshCw, AlertCircle, CheckCircle } from "lucide-react";

interface TemplateReloadButtonProps {
  onSuccess?: () => void;
  bankCode?: string;
}

export default function TemplateReloadButton({
  onSuccess,
  bankCode,
}: TemplateReloadButtonProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleReload = async () => {
    try {
      setLoading(true);
      setError(null);
      setSuccess(false);

      const token =
        localStorage.getItem("access_token") ||
        localStorage.getItem("token");
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};

      const endpoint = bankCode
        ? `/api/admin/banks/${bankCode}/reload`
        : `/api/admin/banks/reload/all`;

      const response = await fetch(endpoint, {
        method: "POST",
        headers,
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(
          data.detail || data.message || "Failed to reload templates"
        );
      }

      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);

      if (onSuccess) {
        onSuccess();
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Reload failed";
      setError(message);
      setTimeout(() => setError(null), 5000);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button
        onClick={handleReload}
        disabled={loading}
        variant="outline"
        size="sm"
        className="gap-2"
      >
        <RefreshCw
          size={16}
          className={loading ? "animate-spin" : ""}
        />
        {loading
          ? "Reloading..."
          : bankCode
            ? `Reload ${bankCode}`
            : "Reload All"}
      </Button>

      {error && (
        <div className="flex gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
          <AlertCircle size={16} className="text-red-600 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {success && (
        <div className="flex gap-2 p-3 bg-green-50 border border-green-200 rounded-lg">
          <CheckCircle size={16} className="text-green-600 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-green-700">Templates reloaded successfully</p>
        </div>
      )}
    </div>
  );
}
