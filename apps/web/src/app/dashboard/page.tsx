"use client";

import { Dispatch, RefObject, SetStateAction, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API = "/api";

type DashboardUser = {
  full_name?: string | null;
  firm?: {
    name?: string | null;
  } | null;
};

type StatementSummary = {
  id: string;
  filename: string;
  bank: string;
  file_type?: string;
  status: string;
  error?: string | null;
};

type StatementListApiItem = {
  id: string;
  filename?: string;
  file_type?: string;
  bank_code?: string | null;
  bank_id?: string | null;
  status: string;
  error_message?: string | null;
};

type ExtractedTransaction = {
  id?: string;
  date: string;
  description: string;
  debit?: string | null;
  credit?: string | null;
  balance?: string | null;
};

type UploadControlsProps = {
  fileInputRef: RefObject<HTMLInputElement | null>;
  file: File | null;
  bank: string | null;
  status: string;
  progress: number;
  setFile: Dispatch<SetStateAction<File | null>>;
  setBank: Dispatch<SetStateAction<string | null>>;
  setStatus: Dispatch<SetStateAction<string>>;
  setProgress: Dispatch<SetStateAction<number>>;
  handleUpload: () => Promise<void>;
  error: string | null;
  passwordNeeded: boolean;
  password: string;
  setPassword: Dispatch<SetStateAction<string>>;
};

async function readApiResponse(res: Response) {
  const text = await res.text();
  if (!text) return {};

  try {
    return JSON.parse(text);
  } catch {
    throw new Error(
      res.ok
        ? "Server returned an invalid response."
        : `API request failed (${res.status}): ${text.slice(0, 160)}`
    );
  }
}

export default function DashboardPage() {
  const router = useRouter();

  const [user, setUser] = useState<DashboardUser | null>(null);
  const [loading, setLoading] = useState(true);

  const [file, setFile] = useState<File | null>(null);
  const [bank, setBank] = useState<string | null>(null);
  const [status, setStatus] = useState("idle");
  const [progress, setProgress] = useState(0);
  const [uploadedStatementId, setUploadedStatementId] = useState<string | null>(null);
  const [statements, setStatements] = useState<StatementSummary[]>([]);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [transactions, setTransactions] = useState<ExtractedTransaction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [passwordNeeded, setPasswordNeeded] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token") || localStorage.getItem("token");

    if (!token) {
      router.push("/login");
      return;
    }

    const fetchUser = async () => {
      try {
        const res = await fetch(`${API}/v1/auth/me`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        const data = await res.json();

        if (data.success) {
          setUser(data.data.user);
        } else {
          localStorage.removeItem("access_token");
          router.push("/login");
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchUser();
  }, [router]);

  // Load persisted statements from API on page load
  useEffect(() => {
    const token = localStorage.getItem("access_token") || localStorage.getItem("token");
    const fetchStatements = async () => {
      try {
        const res = await fetch(`${API}/v1/statements?page=1&size=20`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const data = await res.json();
          if (data.data && data.data.items) {
            setStatements(
              data.data.items.map((stmt: StatementListApiItem) => ({
                id: stmt.id,
                filename: stmt.filename || "Unknown",
                bank: stmt.bank_code || stmt.bank_id || "Unknown",
                file_type: stmt.file_type,
                status: stmt.status,
                error: stmt.error_message,
              }))
            );
          }
        }
      } catch (err) {
        console.error("Failed to load statements:", err);
      }
    };
    fetchStatements();
  }, []);

  const fetchResult = useCallback(async (statementId: string) => {
    const res = await fetch(`${API}/v1/statements/${statementId}/result`);
    const data = await res.json();

    if (data.success) {
      setTransactions(data.data.transactions);
    }
  }, []);

  const checkStatus = useCallback(async () => {
    if (!uploadedStatementId) return;

    const res = await fetch(
      `${API}/v1/statements/${uploadedStatementId}/status`
    );

    const data = await res.json();

    if (data.success) {
      setStatus(data.data.status);

      setStatements((prev) =>
        prev.map((stmt) =>
          stmt.id === data.data.id
            ? { ...stmt, status: data.data.status }
            : stmt
        )
      );
      if (data.data.status === "READY_FOR_REVIEW") {
        fetchResult(data.data.id);
      }
    }
  }, [fetchResult, uploadedStatementId]);

  useEffect(() => {
    if (!uploadedStatementId) return;
    if (status === "READY_FOR_REVIEW") return;
    if (status === "FAILED") return;

    const interval = setInterval(() => {
      checkStatus();
    }, 3000);

    return () => clearInterval(interval);
  }, [checkStatus, uploadedStatementId, status]);

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/login");
  };

  const handleUpload = async () => {
    setError(null);
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    if (bank) {
      formData.append("bank", bank);
    }

    if (password) {
      formData.append("password", password);
    }

    try {
      setStatus("uploading");
      setProgress(30);

      const token = localStorage.getItem("access_token") || localStorage.getItem("token");
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${API}/v1/statements/upload`, {
        method: "POST",
        headers,
        body: formData,
      });

      const data = await readApiResponse(res);

      if (!res.ok || !data.success) {
        const detail = data.detail;
        if (
          detail &&
          typeof detail === "object" &&
          (detail.error_code === "PASSWORD_REQUIRED" || detail.error_code === "INVALID_PASSWORD")
        ) {
          setPasswordNeeded(true);
          setStatus("password_needed");
          setProgress(0);
          setError(detail.message || "This PDF is password-protected. Please enter the password.");
          return;
        }
        const message =
          typeof detail === "string"
            ? detail
            : detail?.message || data.error || data.message || "Upload failed";
        throw new Error(message);
      }

      setProgress(100);
      setStatus(data.data.status);
      setUploadedStatementId(data.data.id);
      setPasswordNeeded(false);
      setPassword("");

      setStatements((prev) => [
        {
          id: data.data.id,
          filename: data.data.filename,
          bank: data.data.bank || bank || "Unknown",
          file_type: data.data.file_type,
          status: data.data.status,
          error: data.data.error,
        },
        ...prev,
      ]);

      setFile(null);
      if (data.data.error) {
        setError(data.data.error);
      }
      if (data.data.status === "READY_FOR_REVIEW") {
        fetchResult(data.data.id);
      }
    } catch (err) {
      setStatus("failed");
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen relative overflow-hidden bg-slate-50 dark:bg-slate-950">
      <div className="absolute top-0 right-0 w-[800px] h-[800px] bg-blue-400/20 rounded-full mix-blend-multiply filter blur-[120px] opacity-70 animate-blob pointer-events-none"></div>
      <div className="absolute top-1/4 left-0 w-[600px] h-[600px] bg-purple-400/20 rounded-full mix-blend-multiply filter blur-[120px] opacity-70 animate-blob animation-delay-2000 pointer-events-none"></div>

      <header className="sticky top-0 z-50 w-full glass border-b border-white/20 dark:border-slate-800/50">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center text-white font-bold shadow-lg">
              B
            </div>
            <span className="font-semibold text-lg tracking-tight bg-gradient-to-br from-slate-800 to-slate-500 dark:from-white dark:to-slate-400 bg-clip-text text-transparent">
              Bank Extract
            </span>
          </div>

          <div className="flex items-center gap-4">
            <span className="text-sm font-medium text-slate-600 dark:text-slate-300">
              {user?.firm?.name || "My Firm"}
            </span>
            <Button
              variant="outline"
              onClick={handleLogout}
              className="glass-input h-9 text-sm"
            >
              Log out
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8 relative z-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              Welcome back, {user?.full_name?.split(" ")[0] || "User"}
            </h1>
            <p className="text-slate-500 dark:text-slate-400 mt-1">
              Here&apos;s an overview of your firm&apos;s activity
            </p>
          </div>

          <Button
            className="bg-blue-600 hover:bg-blue-700 text-white shadow-md transition-all"
            onClick={() => fileInputRef.current?.click()}
          >
            + Upload Statement
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card className="glass-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">
                Total Clients
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">12</div>
              <p className="text-xs text-emerald-500 font-medium mt-1">
                +2 this month
              </p>
            </CardContent>
          </Card>

          <Card className="glass-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">
                Statements Processed
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">48</div>
              <p className="text-xs text-emerald-500 font-medium mt-1">
                +14 this week
              </p>
            </CardContent>
          </Card>

          <Card className="glass-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">
                Auto-Categorization Rate
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">87%</div>
              <p className="text-xs text-blue-500 font-medium mt-1">
                Learning from your edits
              </p>
            </CardContent>
          </Card>
        </div>

        <h2 className="text-xl font-semibold mb-4 text-slate-800 dark:text-slate-200">
          Recent Statements
        </h2>

        <Card id="upload-section" className="glass-card overflow-hidden">
          <div className="divide-y divide-white/20 dark:divide-slate-800/50">
            {statements.length === 0 ? (
              <div className="p-8 text-center">
                <div className="h-16 w-16 bg-slate-100 dark:bg-slate-800 rounded-full flex items-center justify-center mx-auto mb-4">
                  <svg
                    className="w-8 h-8 text-slate-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                </div>

                <h3 className="text-lg font-medium text-slate-900 dark:text-slate-100 mb-1">
                  No statements yet
                </h3>

                <p className="text-slate-500 dark:text-slate-400 max-w-sm mx-auto mb-4">
                  Upload your first bank statement to get started with
                  auto-extraction.
                </p>

                <UploadControls
                  fileInputRef={fileInputRef}
                  file={file}
                  bank={bank}
                  status={status}
                  progress={progress}
                  setFile={setFile}
                  setBank={setBank}
                  setStatus={setStatus}
                  setProgress={setProgress}
                  handleUpload={handleUpload}
                  error={error}
                  passwordNeeded={passwordNeeded}
                  password={password}
                  setPassword={setPassword}
                />
              </div>
            ) : (
              <div className="p-4">
                <div className="grid grid-cols-4 text-sm font-semibold text-slate-500 border-b pb-2">
                  <span>Filename</span>
                  <span>Bank</span>
                  <span>Status</span>
                  <span>Action</span>
                </div>

                {statements.map((stmt) => (
                  <div
                    key={stmt.id}
                    className="grid grid-cols-4 text-sm py-3 border-b last:border-b-0 text-slate-700 dark:text-slate-300 items-center"
                  >
                    <span className="truncate pr-4">{stmt.filename}</span>
                    <span className="flex items-center gap-2">
                      {stmt.bank}
                      {stmt.file_type && (
                        <span className="rounded-full bg-slate-100 px-2 py-1 text-xs uppercase text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                          {stmt.file_type}
                        </span>
                      )}
                    </span>
                    <span
                      data-testid={`status-chip-${stmt.id}`}
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        stmt.status === "READY_FOR_REVIEW"
                          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300"
                          : stmt.status === "REVIEWED"
                            ? "bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-300"
                            : stmt.status === "OCR"
                              ? "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300"
                              : stmt.status === "PARSING"
                                ? "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300"
                                : stmt.status === "FAILED" || stmt.status === "PARSE_ERROR"
                                  ? "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300"
                                  : "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300"
                      }`}
                    >
                      {(stmt.status === "OCR" || stmt.status === "PARSING") && (
                        <span className="relative flex h-2 w-2">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75" />
                          <span className="relative inline-flex rounded-full h-2 w-2 bg-current" />
                        </span>
                      )}
                      {stmt.status === "OCR" ? "OCR Processing" : stmt.status}
                    </span>
                    {stmt.status === "REVIEWED" ? (
                      <Link
                        href={`/dashboard/review/${stmt.id}`}
                        data-testid={`review-button-${stmt.id}`}
                        className="px-3 py-1 rounded-lg text-xs bg-slate-200 hover:bg-slate-300
                                 text-slate-500 dark:bg-slate-700 dark:text-slate-400 dark:hover:bg-slate-600
                                 font-medium transition-all w-fit flex items-center gap-1"
                        title="This statement is reviewed. You can view it in read-only mode."
                      >
                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                        View
                      </Link>
                    ) : stmt.status === "READY_FOR_REVIEW" || stmt.file_type?.toLowerCase() === "pdf" ? (
                      <Link
                        href={`/dashboard/review/${stmt.id}`}
                        data-testid={`review-button-${stmt.id}`}
                        className="px-3 py-1 rounded-lg text-xs bg-purple-600 hover:bg-purple-500
                                 text-white font-medium transition-all w-fit"
                      >
                        Review →
                      </Link>
                    ) : (
                      <span className="text-xs text-slate-500">—</span>
                    )}
                  </div>
                ))}

                <div className="pt-4">
                  <UploadControls
                    fileInputRef={fileInputRef}
                    file={file}
                    bank={bank}
                    status={status}
                    progress={progress}
                    setFile={setFile}
                    setBank={setBank}
                    setStatus={setStatus}
                    setProgress={setProgress}
                    handleUpload={handleUpload}
                    error={error}
                    passwordNeeded={passwordNeeded}
                    password={password}
                    setPassword={setPassword}
                  />
                </div>
              </div>
            )}
          </div>
        </Card>

        {transactions.length > 0 && (
          <Card className="glass-card mt-6 p-4">
            <h2 className="text-xl font-semibold mb-4 text-slate-800 dark:text-slate-200">
              Extracted Transactions
            </h2>

            <div className="grid grid-cols-5 text-sm font-semibold text-slate-500 border-b pb-2">
              <span>Date</span>
              <span>Description</span>
              <span>Debit</span>
              <span>Credit</span>
              <span>Balance</span>
            </div>

            {transactions.map((txn, index) => (
              <div
                key={txn.id || index}
                className="grid grid-cols-5 text-sm py-3 border-b last:border-b-0 text-slate-700 dark:text-slate-300"
              >
                <span>{txn.date}</span>
                <span>{txn.description}</span>
                <span>{txn.debit || "-"}</span>
                <span>{txn.credit || "-"}</span>
                <span>{txn.balance || "-"}</span>
              </div>
            ))}
          </Card>
        )}
      </main>
    </div>
  );
}

function UploadControls({
  fileInputRef,
  file,
  bank,
  status,
  progress,
  setFile,
  setBank,
  setStatus,
  setProgress,
  handleUpload,
  error,
  passwordNeeded,
  password,
  setPassword,
}: UploadControlsProps) {
  return (
    <div className="space-y-4">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.csv,.xlsx,.xls,image/*"
        onChange={(e) => {
          const selected = e.target.files?.[0] || null;
          setFile(selected);
          setStatus(selected ? "selected" : "idle");
          setProgress(0);
        }}
        className="block w-full text-sm text-slate-500"
      />

      {file && (
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Selected: {file.name}
        </p>
      )}

      <div className="flex justify-center gap-2">
        {["HDFC", "ICICI", "SBI", "AXIS", "KOTAK"].map((b) => (
          <button
            key={b}
            onClick={() => setBank(b)}
            className={`rounded-full px-3 py-1 border text-sm ${
              bank === b
                ? "bg-blue-600 text-white border-blue-600"
                : "border-slate-300 text-slate-600 dark:text-slate-300"
            }`}
          >
            {b}
          </button>
        ))}
      </div>

      {passwordNeeded && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-950/30 dark:border-amber-800">
          <svg className="w-5 h-5 text-amber-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <input
            type="password"
            placeholder="Enter PDF password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && file) handleUpload(); }}
            className="flex-1 px-3 py-1.5 rounded-md border border-amber-300 bg-white text-sm
                       text-slate-800 placeholder:text-slate-400
                       focus:outline-none focus:ring-2 focus:ring-amber-400
                       dark:bg-slate-900 dark:border-amber-700 dark:text-slate-200"
          />
        </div>
      )}

      {status !== "idle" && (
        <p className="text-sm text-slate-500">
          Status: {status} {progress > 0 && `(${progress}%)`}
        </p>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <Button
        variant="outline"
        className="glass-input"
        disabled={!file || (passwordNeeded && !password)}
        onClick={handleUpload}
      >
        {passwordNeeded ? "Unlock & Upload" : "Upload Statement"}
      </Button>
    </div>
  );
}
