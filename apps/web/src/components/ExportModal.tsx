"use client";

import { useCallback, useEffect, useState } from "react";

const API = "/api";

type ExportFormat = "tally_xml" | "csv" | "json" | "excel";

export interface ExportJob {
  export_id: string;
  statement_id?: string;
  format: ExportFormat;
  status: string;
  download_url: string;
  filename: string;
  created_at: string;
  expires_at?: string;
  idempotent?: boolean;
}

interface Props {
  statementId: string;
  statementFilename: string;
  bankId: string;
  isOpen: boolean;
  onClose: () => void;
  onExportComplete: (job: ExportJob) => void;
}

const FORMAT_INFO: Record<ExportFormat, { label: string; desc: string }> = {
  tally_xml: { label: "Tally XML", desc: "Day Book Voucher import for Tally Prime" },
  csv: { label: "CSV", desc: "Spreadsheet-friendly export with totals" },
  excel: { label: "Excel", desc: "Formatted workbook with summary sheet" },
  json: { label: "JSON", desc: "Structured payload for integrations" },
};

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined"
    ? localStorage.getItem("access_token") || localStorage.getItem("token")
    : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function downloadUrl(path: string): string {
  return path.startsWith("http") ? path : `${API}${path}`;
}

function filenameFromDisposition(value: string | null): string | null {
  if (!value) return null;
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1].replace(/"/g, ""));
  const filenameMatch = value.match(/filename="?([^";]+)"?/i);
  return filenameMatch?.[1] ?? null;
}

export default function ExportModal({
  statementId,
  statementFilename,
  bankId,
  isOpen,
  onClose,
  onExportComplete,
}: Props) {
  const [format, setFormat] = useState<ExportFormat>("tally_xml");
  const [companyName, setCompanyName] = useState("");
  const [bankLedgerName, setBankLedgerName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportJob, setExportJob] = useState<ExportJob | null>(null);
  const [pastExports, setPastExports] = useState<ExportJob[]>([]);
  const [showPast, setShowPast] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const defaultCompanyName = bankId ? `${bankId} Company` : "";
  const defaultBankLedgerName = `${bankId || "Bank"} Account`;

  useEffect(() => {
    if (!isOpen) return;

    const loadExports = async () => {
      try {
        const res = await fetch(`${API}/v1/statements/${statementId}/exports`, {
          headers: authHeaders(),
        });
        if (!res.ok) return;
        const data = await res.json();
        setPastExports(Array.isArray(data) ? data : []);
      } catch {
        setPastExports([]);
      }
    };

    void loadExports();
  }, [isOpen, statementId]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  const handleExport = useCallback(async () => {
    const exportCompanyName = companyName || defaultCompanyName;
    const exportBankLedgerName = bankLedgerName || defaultBankLedgerName;

    if (format === "tally_xml" && (!exportCompanyName.trim() || !exportBankLedgerName.trim())) {
      setError("Company name and bank ledger name are required for Tally XML export.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/v1/statements/${statementId}/export`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          format,
          company_name: exportCompanyName || "My Company",
          bank_ledger_name: exportBankLedgerName || "Bank Account",
          strict_reviewed_only: false,
        }),
      });

      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(payload.detail || "Export failed");
      }

      setExportJob(payload);
      setPastExports((current) => [payload, ...current.filter((item) => item.export_id !== payload.export_id)]);
      onExportComplete(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setLoading(false);
    }
  }, [bankLedgerName, companyName, defaultBankLedgerName, defaultCompanyName, format, onExportComplete, statementId]);

  const handleDownload = useCallback(async (job: ExportJob) => {
    setDownloadingId(job.export_id);
    setError(null);
    try {
      const res = await fetch(downloadUrl(job.download_url), {
        headers: authHeaders(),
      });

      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload.detail || "Download failed");
      }

      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filenameFromDisposition(res.headers.get("content-disposition")) || job.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloadingId(null);
    }
  }, []);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-2xl overflow-hidden rounded-3xl border border-white/10 bg-slate-900 shadow-2xl">
        <div className="flex items-start justify-between border-b border-white/10 px-6 py-5">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-cyan-300/70">Export Statement</p>
            <h2 className="mt-1 text-xl font-semibold text-white">{statementFilename}</h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-full border border-white/10 px-3 py-1 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white"
          >
            Close
          </button>
        </div>

        <div className="space-y-6 px-6 py-6">
          <div className="grid gap-3 sm:grid-cols-2">
            {(Object.entries(FORMAT_INFO) as [ExportFormat, { label: string; desc: string }][])
              .map(([key, info]) => (
                <button
                  key={key}
                  onClick={() => setFormat(key)}
                  className={`rounded-2xl border p-4 text-left transition ${
                    format === key
                      ? "border-cyan-400 bg-cyan-400/10"
                      : "border-white/10 bg-white/[0.03] hover:border-white/20 hover:bg-white/[0.05]"
                  }`}
                >
                  <p className="text-sm font-semibold text-white">{info.label}</p>
                  <p className="mt-1 text-sm text-slate-400">{info.desc}</p>
                </button>
              ))}
          </div>

          {format === "tally_xml" && (
            <div className="grid gap-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4">
              <div>
                <label className="mb-1 block text-sm text-slate-300">Company Name</label>
                <input
                  value={companyName || defaultCompanyName}
                  onChange={(event) => setCompanyName(event.target.value)}
                  placeholder="My Company Pvt Ltd"
                  className="w-full rounded-xl border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-400"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm text-slate-300">Bank Ledger Name</label>
                <input
                  value={bankLedgerName || defaultBankLedgerName}
                  onChange={(event) => setBankLedgerName(event.target.value)}
                  placeholder="HDFC Bank A/c"
                  className="w-full rounded-xl border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-400"
                />
              </div>
              <p className="text-xs text-slate-500">
                These names should match the company and ledger names already present in Tally.
              </p>
            </div>
          )}

          {error && (
            <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          )}

          {exportJob ? (
            <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4">
              <p className="text-sm font-semibold text-emerald-200">Export ready</p>
              <p className="mt-1 text-sm text-emerald-100/80">
                {exportJob.idempotent ? "Reused an existing export." : "Created a fresh export file."}
              </p>
              <button
                type="button"
                onClick={() => handleDownload(exportJob)}
                disabled={downloadingId === exportJob.export_id}
                className="mt-4 inline-flex rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-emerald-400"
              >
                {downloadingId === exportJob.export_id ? "Downloading..." : `Download ${FORMAT_INFO[exportJob.format].label}`}
              </button>
            </div>
          ) : (
            <button
              onClick={handleExport}
              disabled={loading}
              className="w-full rounded-2xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Preparing export..." : `Export ${FORMAT_INFO[format].label}`}
            </button>
          )}

          {pastExports.length > 0 && (
            <div className="rounded-2xl border border-white/10 bg-slate-950/50 p-4">
              <button
                onClick={() => setShowPast((current) => !current)}
                className="text-sm font-medium text-slate-300 transition hover:text-white"
              >
                {showPast ? "Hide" : "Show"} previous exports
              </button>
              {showPast && (
                <div className="mt-3 space-y-2">
                  {pastExports.map((job) => (
                    <div
                      key={job.export_id}
                      className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2"
                    >
                      <div>
                        <p className="text-sm text-white">{FORMAT_INFO[job.format]?.label ?? job.format}</p>
                        <p className="text-xs text-slate-500">
                          {job.created_at ? new Date(job.created_at).toLocaleString() : "Unknown time"}
                        </p>
                      </div>
                      {job.download_url ? (
                        <button
                          type="button"
                          onClick={() => handleDownload(job)}
                          disabled={downloadingId === job.export_id}
                          className="text-sm font-medium text-cyan-300 transition hover:text-cyan-200"
                        >
                          {downloadingId === job.export_id ? "Downloading..." : "Download"}
                        </button>
                      ) : (
                        <span className="text-xs text-slate-500">{job.status}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
