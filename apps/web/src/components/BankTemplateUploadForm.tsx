/**
 * BankTemplateUploadForm - Upload new bank template
 */
"use client";

import { FormEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { uploadBank } from "@/lib/bank-service";
import { Upload, AlertCircle, CheckCircle, ArrowLeft } from "lucide-react";

const TEMPLATE_EXAMPLE = `bank_code: "TEST"
bank_name: "Test Bank Ltd."
type: "pdf_text"

fingerprint:
  keywords:
    - "TEST BANK"
    - "Statement of Account"
  regex:
    - "IFSC\\\\s*:\\\\s*TEST000[0-9]{4}"

extraction:
  skip_headers: 1
  headers:
    - "Date"
    - "Narration"
    - "Chq./Ref.No."
    - "Value Dt"
    - "Withdrawal Amt."
    - "Deposit Amt."
    - "Closing Balance"
  
  columns:
    date: 0
    narration: 1
    reference: 2
    value_date: 3
    debit: 4
    credit: 5
    balance: 6

  formats:
    date: "%d/%m/%y"
    number: "indian"
`;

export default function BankTemplateUploadForm() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [bankCode, setBankCode] = useState("");
  const [bankName, setBankName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [preview, setPreview] = useState<string>("");

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    // Validate file type
    if (
      !selectedFile.name.endsWith(".yaml") &&
      !selectedFile.name.endsWith(".yml")
    ) {
      setError("Only YAML files are supported (.yaml or .yml)");
      return;
    }

    // Validate file size (max 1MB)
    if (selectedFile.size > 1024 * 1024) {
      setError("File size must be less than 1MB");
      return;
    }

    setFile(selectedFile);
    setError(null);

    // Try to extract bank code from filename
    const filename = selectedFile.name.split(".")[0].toLowerCase();
    setBankCode(filename);

    // Show file preview
    const text = await selectedFile.text();
    setPreview(text);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!file) {
      setError("Please select a file");
      return;
    }

    if (!bankCode.trim()) {
      setError("Bank code is required");
      return;
    }

    if (!bankName.trim()) {
      setError("Bank name is required");
      return;
    }

    try {
      setLoading(true);
      await uploadBank(file, bankCode, bankName);
      setSuccess(true);
      setFile(null);
      setBankCode("");
      setBankName("");
      setPreview("");

      // Redirect after success
      setTimeout(() => {
        router.push("/admin/banks");
      }, 2000);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setError(message);
      console.error("Upload error:", err);
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="max-w-2xl">
        <Card className="border-green-200 bg-green-50">
          <CardContent className="pt-6">
            <div className="flex gap-4">
              <CheckCircle className="text-green-600 flex-shrink-0" size={24} />
              <div>
                <h2 className="text-lg font-semibold text-green-900">
                  Bank template uploaded successfully!
                </h2>
                <p className="text-sm text-green-800 mt-1">
                  Redirecting to banks list...
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
      <div className="flex items-center gap-2 mb-6">
        <Link href="/admin/banks">
          <Button variant="ghost" size="sm" className="gap-2">
            <ArrowLeft size={18} />
            Back to Banks
          </Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Upload Bank Template</CardTitle>
          <p className="text-sm text-gray-600 mt-2">
            Add a new bank template by uploading a YAML file with extraction rules.
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

            {/* File Upload */}
            <div className="space-y-2">
              <label className="block text-sm font-medium">Template File *</label>
              <div
                className="relative border-2 border-dashed border-gray-300 rounded-lg p-8 cursor-pointer hover:border-blue-400 transition-colors"
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".yaml,.yml"
                  onChange={handleFileChange}
                  className="hidden"
                />
                <div className="text-center">
                  <Upload size={32} className="mx-auto text-gray-400 mb-2" />
                  <p className="text-sm font-medium">
                    {file ? file.name : "Click to upload or drag and drop"}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    YAML files only (.yaml, .yml) • Max 1MB
                  </p>
                </div>
              </div>
            </div>

            {/* Bank Code */}
            <div className="space-y-2">
              <label className="block text-sm font-medium">
                Bank Code *
              </label>
              <input
                type="text"
                value={bankCode}
                onChange={(e) => setBankCode(e.target.value.toUpperCase())}
                placeholder="e.g., HDFC, ICICI, SBI"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <p className="text-xs text-gray-500">
                Unique identifier for the bank
              </p>
            </div>

            {/* Bank Name */}
            <div className="space-y-2">
              <label className="block text-sm font-medium">
                Bank Name *
              </label>
              <input
                type="text"
                value={bankName}
                onChange={(e) => setBankName(e.target.value)}
                placeholder="e.g., HDFC Bank Ltd."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {/* File Preview */}
            {preview && (
              <div className="space-y-2">
                <label className="block text-sm font-medium">Template Preview</label>
                <pre className="bg-gray-50 p-4 rounded-lg overflow-x-auto text-xs border border-gray-200 max-h-64 overflow-y-auto">
                  {preview}
                </pre>
              </div>
            )}

            {/* Template Example */}
            <div className="space-y-2">
              <label className="block text-sm font-medium">Template Example</label>
              <details className="border border-gray-200 rounded-lg">
                <summary className="p-3 cursor-pointer font-medium text-sm bg-gray-50 hover:bg-gray-100">
                  View Example Template
                </summary>
                <pre className="bg-gray-50 p-4 text-xs overflow-x-auto border-t border-gray-200 max-h-48 overflow-y-auto">
                  {TEMPLATE_EXAMPLE}
                </pre>
              </details>
            </div>

            {/* Submit Button */}
            <div className="flex gap-3 pt-4">
              <Button
                type="submit"
                disabled={loading || !file}
                className="flex-1 gap-2"
              >
                {loading ? "Uploading..." : "Upload Template"}
              </Button>
              <Link href="/admin/banks" className="flex-1">
                <Button type="button" variant="outline" className="w-full">
                  Cancel
                </Button>
              </Link>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Instructions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Template Format Guide</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <h4 className="font-medium mb-1">Required Fields:</h4>
            <ul className="list-disc list-inside space-y-1 text-gray-700">
              <li>
                <strong>bank_code</strong>: Unique identifier (e.g., HDFC)
              </li>
              <li>
                <strong>bank_name</strong>: Full name (e.g., HDFC Bank Ltd.)
              </li>
              <li>
                <strong>type</strong>: Extraction type (pdf_text, excel, csv)
              </li>
              <li>
                <strong>fingerprint</strong>: Bank detection patterns
              </li>
              <li>
                <strong>extraction</strong>: Column mapping and format rules
              </li>
            </ul>
          </div>
          <div>
            <h4 className="font-medium mb-1">Tips:</h4>
            <ul className="list-disc list-inside space-y-1 text-gray-700">
              <li>Use keywords and regex to uniquely identify the bank</li>
              <li>Map columns to their positions in the statement</li>
              <li>Specify date and number formats for correct parsing</li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
