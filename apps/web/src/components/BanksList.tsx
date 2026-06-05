/**
 * BanksList - Display list of supported banks
 */
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { listBanks, Bank, deleteBank, formatDate } from "@/lib/bank-service";
import { Trash2, Edit2, Plus, Download, AlertCircle, RefreshCw } from "lucide-react";
import TemplateReloadButton from "@/components/TemplateReloadButton";

export default function BanksList() {
  const [banks, setBanks] = useState<Bank[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    loadBanks();
  }, []);

  const loadBanks = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listBanks();
      setBanks(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load banks";
      setError(message);
      console.error("Error loading banks:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (bankCode: string) => {
    if (!confirm(`Delete ${bankCode} template?`)) return;

    try {
      setDeleting(bankCode);
      await deleteBank(bankCode);
      setBanks(banks.filter((b) => b.code !== bankCode));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete bank";
      setError(message);
      console.error("Error deleting bank:", err);
    } finally {
      setDeleting(null);
    }
  };

  const handleDownload = async (bankCode: string) => {
    try {
      const blob = await import("@/lib/bank-service").then((m) =>
        m.downloadTemplate(bankCode)
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${bankCode.toLowerCase()}.yaml`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to download template";
      setError(message);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 bg-gray-200 rounded animate-pulse w-48"></div>
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-gray-100 rounded animate-pulse"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Supported Banks</h1>
        <div className="flex gap-2">
          <Link href="/admin/banks/upload">
            <Button className="gap-2">
              <Plus size={18} />
              Add Bank
            </Button>
          </Link>
          <Link href="/admin/cache">
            <Button variant="outline" className="gap-2">
              <RefreshCw size={18} />
              Cache
            </Button>
          </Link>
        </div>
      </div>

      {error && (
        <div className="flex gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
          <AlertCircle size={20} className="text-red-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium text-red-900">Error</p>
            <p className="text-sm text-red-800">{error}</p>
          </div>
        </div>
      )}

      {/* Quick Reload */}
      <Card className="bg-blue-50 border-blue-200">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Hot Reload Status</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-blue-900 mb-3">
            Templates are automatically monitored for changes. Manually trigger a reload:
          </p>
          <TemplateReloadButton onSuccess={loadBanks} />
        </CardContent>
      </Card>

      {banks.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center text-gray-500">
            <p>No banks configured yet. Add your first bank template.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {banks.map((bank) => (
            <Card
              key={bank.code}
              className={`transition-opacity ${!bank.is_active ? "opacity-60" : ""}`}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-lg">{bank.name}</CardTitle>
                    <p className="text-sm text-gray-500 mt-1">
                      Code: {bank.code.toUpperCase()} • Type: {bank.extraction_type}
                    </p>
                  </div>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-medium ${
                      bank.is_active
                        ? "bg-green-100 text-green-800"
                        : "bg-gray-100 text-gray-800"
                    }`}
                  >
                    {bank.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
              </CardHeader>
              <CardContent className="border-t pt-4">
                <div className="flex gap-2">
                  <Link href={`/admin/banks/${bank.code}`} className="flex-1">
                    <Button variant="outline" className="w-full gap-2">
                      <Edit2 size={16} />
                      Edit
                    </Button>
                  </Link>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDownload(bank.code)}
                    title="Download template"
                  >
                    <Download size={16} />
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => handleDelete(bank.code)}
                    disabled={deleting === bank.code}
                    title="Delete bank"
                  >
                    <Trash2 size={16} />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
