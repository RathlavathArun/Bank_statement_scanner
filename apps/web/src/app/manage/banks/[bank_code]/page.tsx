/**
 * Edit Bank Template Page
 */
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { getBank, updateBank, BankTemplate } from "@/lib/bank-service";
import { ArrowLeft, AlertCircle, CheckCircle } from "lucide-react";

export default function EditBankPage() {
  const params = useParams();
  const router = useRouter();
  const bankCode = params.bank_code as string;

  const [bank, setBank] = useState<BankTemplate | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [formData, setFormData] = useState({
    bankName: "",
    description: "",
    isActive: true,
  });

  useEffect(() => {
    loadBank();
  }, [bankCode]);

  const loadBank = async () => {
    try {
      setLoading(true);
      const data = await getBank(bankCode);
      setBank(data);
      setFormData({
        bankName: data.name || "",
        description: (data.template?.description as string | undefined) || "",
        isActive: data.is_active,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load bank";
      setError(message);
      console.error("Error loading bank:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    try {
      setSaving(true);
      await updateBank(bankCode, {
        bankName: formData.bankName,
        description: formData.description,
        isActive: formData.isActive,
      });
      setSuccess(true);
      setTimeout(() => {
        router.push("/manage/banks");
      }, 2000);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update bank";
      setError(message);
      console.error("Error updating bank:", err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 bg-gray-200 rounded animate-pulse w-48"></div>
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 bg-gray-100 rounded animate-pulse"></div>
          ))}
        </div>
      </div>
    );
  }

  if (!bank) {
    return (
      <div className="space-y-4">
        <Link href="/manage/banks">
          <Button variant="ghost" size="sm" className="gap-2">
            <ArrowLeft size={18} />
            Back to Banks
          </Button>
        </Link>
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-6">
            <div className="flex gap-3">
              <AlertCircle className="text-red-600 flex-shrink-0" size={24} />
              <div>
                <h3 className="font-medium text-red-900">Bank not found</h3>
                <p className="text-sm text-red-800 mt-1">
                  The bank template could not be loaded.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center gap-2">
        <Link href="/manage/banks">
          <Button variant="ghost" size="sm" className="gap-2">
            <ArrowLeft size={18} />
            Back to Banks
          </Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Edit Bank Template: {bank.name}</CardTitle>
          <p className="text-sm text-gray-600 mt-2">
            Update bank metadata and status. To upload a new template file, delete
            this bank and create a new one.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className="flex gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
                <AlertCircle
                  size={20}
                  className="text-red-500 flex-shrink-0 mt-0.5"
                />
                <div>
                  <p className="font-medium text-red-900">Error</p>
                  <p className="text-sm text-red-800">{error}</p>
                </div>
              </div>
            )}

            {success && (
              <div className="flex gap-3 p-4 bg-green-50 border border-green-200 rounded-lg">
                <CheckCircle
                  size={20}
                  className="text-green-600 flex-shrink-0 mt-0.5"
                />
                <div>
                  <p className="font-medium text-green-900">Success</p>
                  <p className="text-sm text-green-800">
                    Bank updated successfully. Redirecting...
                  </p>
                </div>
              </div>
            )}

            {/* Bank Code (Read-only) */}
            <div className="space-y-2">
              <label className="block text-sm font-medium">Bank Code</label>
              <input
                type="text"
                value={bank.code.toUpperCase()}
                disabled
                className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-600"
              />
              <p className="text-xs text-gray-500">Read-only field</p>
            </div>

            {/* Bank Name */}
            <div className="space-y-2">
              <label className="block text-sm font-medium">Bank Name</label>
              <input
                type="text"
                value={formData.bankName}
                onChange={(e) =>
                  setFormData({ ...formData, bankName: e.target.value })
                }
                placeholder="e.g., HDFC Bank Ltd."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {/* Description */}
            <div className="space-y-2">
              <label className="block text-sm font-medium">Description</label>
              <textarea
                value={formData.description}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.target.value })
                }
                placeholder="Add notes about this template..."
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {/* Active Status */}
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="isActive"
                checked={formData.isActive}
                onChange={(e) =>
                  setFormData({ ...formData, isActive: e.target.checked })
                }
                className="rounded"
              />
              <label htmlFor="isActive" className="text-sm font-medium cursor-pointer">
                Active
              </label>
              <p className="text-xs text-gray-500 ml-auto">
                {formData.isActive
                  ? "Bank template is available for use"
                  : "Bank template is disabled"}
              </p>
            </div>

            {/* Template Info */}
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <h4 className="font-medium text-blue-900 mb-2">Template Details</h4>
              <dl className="space-y-1 text-sm text-blue-800">
                <div className="flex justify-between">
                  <dt>Extraction Type:</dt>
                  <dd className="font-medium">{bank.extraction_type}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>File Path:</dt>
                  <dd className="font-mono text-xs break-all">{bank.template_path}</dd>
                </div>
              </dl>
            </div>

            {/* Submit Button */}
            <div className="flex gap-3 pt-4">
              <Button type="submit" disabled={saving} className="flex-1">
                {saving ? "Saving..." : "Save Changes"}
              </Button>
              <Link href="/manage/banks" className="flex-1">
                <Button type="button" variant="outline" className="w-full">
                  Cancel
                </Button>
              </Link>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
