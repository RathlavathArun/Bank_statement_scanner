"use client";

import { useEffect, useRef, useState } from "react";
import Uppy from "@uppy/core";
import Tus from "@uppy/tus";
import { ensureAccessToken, getAccessToken } from "@/lib/auth";

const API = "/api";
const MAX_UPLOAD_FILES = 20;

interface UppyUploaderProps {
  bank: string | null;
  setBank: (bank: string | null) => void;
  onUploadSuccess: (statementId: string, status: string) => void;
  onUploadError: (message: string) => void;
  passwordNeeded: boolean;
  setPasswordNeeded: (v: boolean) => void;
  password: string;
  setPassword: (v: string) => void;
}

function passwordErrorFrom(value: unknown): { code: string; message: string } | null {
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const detail = record.detail ?? value;
    if (detail !== value) return passwordErrorFrom(detail);
    const code = typeof record.error_code === "string" ? record.error_code : "";
    const message = typeof record.message === "string" ? record.message : "";
    if (code === "PASSWORD_REQUIRED" || code === "INVALID_PASSWORD") {
      return { code, message };
    }
  }

  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      const found = passwordErrorFrom(parsed);
      if (found) return found;
    } catch {
      // Uppy may wrap the response JSON inside its own error message.
    }
    if (/password-protected|incorrect password|PASSWORD_REQUIRED|INVALID_PASSWORD/i.test(value)) {
      return {
        code: /incorrect|INVALID_PASSWORD/i.test(value) ? "INVALID_PASSWORD" : "PASSWORD_REQUIRED",
        message: /incorrect|INVALID_PASSWORD/i.test(value)
          ? "Incorrect password. Please provide the correct PDF password."
          : "This PDF is password-protected. Please enter the document password.",
      };
    }
  }

  return null;
}

function authToken(): string | null {
  return getAccessToken();
}

export default function UppyUploader({
  bank,
  setBank,
  onUploadSuccess,
  onUploadError,
  passwordNeeded,
  setPasswordNeeded,
  password,
  setPassword,
}: UppyUploaderProps) {
  const uppyRef = useRef<Uppy | null>(null);
  const [uploadState, setUploadState] = useState<"idle" | "uploading" | "done" | "error">("idle");
  const [progress, setProgress] = useState(0);
  const [selectedFileNames, setSelectedFileNames] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const syncSelectedFiles = (uppy: Uppy) => {
    setSelectedFileNames(
      uppy.getFiles().map((file) => file.name ?? "Unnamed file")
    );
  };

  // Lazy-init Uppy once and keep it stable
  useEffect(() => {
    const uppy = new Uppy({
      autoProceed: false,
      restrictions: {
        maxNumberOfFiles: MAX_UPLOAD_FILES,
        allowedFileTypes: [".pdf", ".csv", ".xlsx", ".xls", "image/*"],
      },
    });

    uppy.use(Tus, {
      endpoint: `${API}/v1/statements/upload/tus`,
      removeFingerprintOnSuccess: true,
      // Set Authorization in exactly one place. Supplying it here as well as
      // in onBeforeRequest makes tus-js-client append the two values, which
      // produces a malformed JWT (roughly twice the expected token length).
      onBeforeRequest: (req) => {
        const token = authToken();
        if (token) req.setHeader("Authorization", `Bearer ${token}`);
      },
    });

    uppy.on("file-added", () => {
      syncSelectedFiles(uppy);
      setUploadState("idle");
      setProgress(0);
    });

    uppy.on("file-removed", () => {
      syncSelectedFiles(uppy);
      setUploadState("idle");
      setProgress(0);
    });

    uppy.on("upload", () => {
      setUploadState("uploading");
      setProgress(0);
    });

    uppy.on("progress", (pct) => {
      setProgress(pct);
    });

    uppy.on("upload-success", (_file, response) => {
      const statementId = response.uploadURL
        ? response.uploadURL.split("/").pop()
        : null;
        
      // Try to get statementId from the custom header we added in backend
      let realStatementId = statementId;
      const xhr = (response.body as { xhr?: XMLHttpRequest } | undefined)?.xhr;
      const headerId = xhr?.getResponseHeader("X-Statement-Id");
      if (headerId) realStatementId = headerId;
      
      if (realStatementId) {
        onUploadSuccess(realStatementId, "PARSING");
      } else {
        onUploadError("Upload succeeded but couldn't parse the statement ID.");
      }
    });

    uppy.on("complete", (result) => {
      const failedUploads = result.failed ?? [];
      setUploadState(failedUploads.length > 0 ? "error" : "done");
      if (failedUploads.length === 0) {
        setProgress(100);
      }
      syncSelectedFiles(uppy);
    });

    uppy.on("upload-error", (_file, error, response) => {
      setUploadState("error");
      // Fallback detail object from JSON if backend sent a 422
      let detail: any = null;
      const respAny = response as any;
      if (respAny && respAny.getBody) {
        try {
          const body = respAny.getBody();
          if (body && body.detail) {
            detail = body.detail;
          } else if (typeof body === "string") {
            const parsed = JSON.parse(body);
            detail = parsed.detail || parsed;
          }
        } catch (e) {}
      } else if (respAny && respAny.body) {
        detail = respAny.body.detail || respAny.body;
      }

      const passwordError =
        passwordErrorFrom(detail) ||
        passwordErrorFrom((response as { body?: unknown } | undefined)?.body) ||
        passwordErrorFrom(error.message);

      if (passwordError) {
        setPasswordNeeded(true);
        onUploadError(passwordError.message);
        return;
      }

      const message =
        typeof detail === "string"
          ? detail
          : detail?.message || detail?.error || error.message || "Upload failed";
      onUploadError(message);
    });

    uppyRef.current = uppy;
    return () => {
      uppy.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Inject additional form fields (bank, password) before upload
  const startUpload = async () => {
    const uppy = uppyRef.current;
    if (!uppy) return;

    const files = uppy.getFiles();
    if (files.length === 0) return;

    try {
      const token = await ensureAccessToken();
      if (!token) {
        setUploadState("error");
        onUploadError("Your session has expired. Please sign in again.");
        return;
      }
    } catch {
      setUploadState("error");
      onUploadError("Could not renew your session. Please try again.");
      return;
    }

    // Uppy XHR plugin reads `meta` fields and sends them as form-data fields
      files.forEach((f) => {
      const meta = f.meta || {};
      if (bank) meta.bank = bank;
      if (password) meta.password = password;
      uppy.setFileMeta(f.id, meta);
    });

    void uppy.upload();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const uppy = uppyRef.current;
    if (!uppy || !e.target.files?.length) return;

    Array.from(e.target.files).forEach((file) => {
      try {
        uppy.addFile({
          name: file.name,
          type: file.type,
          data: file,
          source: "Local",
        });
      } catch (err: any) {
        if (err?.isRestriction || err?.message) {
          onUploadError(err.message);
        }
      }
    });
    // Reset file input so same file can be re-selected after error
    e.target.value = "";
  };

  const clearSelectedFiles = () => {
    const uppy = uppyRef.current;
    if (!uppy || isUploading) return;
    uppy.getFiles().forEach((file) => uppy.removeFile(file.id));
    setSelectedFileNames([]);
    setUploadState("idle");
    setProgress(0);
  };

  const hasFile = selectedFileNames.length > 0;
  const isUploading = uploadState === "uploading";
  const selectedSummary =
    selectedFileNames.length === 1
      ? selectedFileNames[0]
      : `${selectedFileNames.length} files selected`;

  return (
    <div className="space-y-4">
      {/* File picker */}
      <div
        className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed transition-colors cursor-pointer
          ${hasFile
            ? "border-blue-500/60 bg-blue-500/5"
            : "border-white/20 bg-white/5 hover:border-white/40 hover:bg-white/10"
          } px-6 py-8 text-center`}
        onClick={() => !isUploading && fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.csv,.xlsx,.xls,image/*"
          className="sr-only"
          onChange={handleFileChange}
          disabled={isUploading}
        />
        {hasFile ? (
          <>
            <svg className="w-8 h-8 text-blue-400 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="text-sm font-medium text-blue-300">{selectedSummary}</p>
            {selectedFileNames.length > 1 && (
              <ul className="mt-2 max-h-24 w-full max-w-xl overflow-y-auto text-left text-xs text-slate-500 dark:text-slate-400">
                {selectedFileNames.map((name, index) => (
                  <li key={`${name}-${index}`} className="truncate">• {name}</li>
                ))}
              </ul>
            )}
            {!isUploading && (
              <p className="text-xs text-slate-500 mt-1">Click to add more files</p>
            )}
          </>
        ) : (
          <>
            <svg className="w-10 h-10 text-slate-500 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="text-sm font-semibold text-slate-300">
              Click to select bank statements
            </p>
            <p className="text-xs text-slate-500 mt-1">Select up to {MAX_UPLOAD_FILES} files: PDF, CSV, XLSX, XLS, or image</p>
          </>
        )}
      </div>

      {hasFile && !isUploading && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={clearSelectedFiles}
            className="text-xs font-medium text-slate-500 hover:text-red-500 transition-colors"
          >
            Clear selected files
          </button>
        </div>
      )}

      {/* Bank selector pills */}
      <div className="flex flex-wrap justify-center gap-2">
        {["HDFC", "ICICI", "SBI", "AXIS", "KOTAK"].map((b) => (
          <button
            key={b}
            type="button"
            disabled={isUploading}
            onClick={() => setBank(bank === b ? null : b)}
            className={`rounded-full px-3 py-1 border text-sm transition-all ${
              bank === b
                ? "bg-blue-600 text-white border-blue-600"
                : "border-slate-300 text-slate-600 dark:text-slate-300 hover:border-blue-400 hover:text-blue-400 dark:border-slate-600"
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {b}
          </button>
        ))}
      </div>

      {/* Password prompt (for password-protected PDFs) */}
      {passwordNeeded && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-950/30 dark:border-amber-800">
          <svg className="w-5 h-5 text-amber-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <input
            type="password"
            placeholder="Enter PDF password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && hasFile) void startUpload(); }}
            className="flex-1 px-3 py-1.5 rounded-md border border-amber-300 bg-white text-sm
                       text-slate-800 placeholder:text-slate-400
                       focus:outline-none focus:ring-2 focus:ring-amber-400
                       dark:bg-slate-900 dark:border-amber-700 dark:text-slate-200"
          />
        </div>
      )}

      {/* Progress bar */}
      {isUploading && (
        <div className="space-y-2">
          <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-400 font-medium">
              Uploading… {progress}%
            </p>
            <div className="flex gap-1.5">
              <button
                type="button"
                onClick={() => uppyRef.current?.pauseAll()}
                className="rounded bg-amber-500/20 border border-amber-500/30 px-2.5 py-1 text-xs text-amber-300 hover:bg-amber-500/35 transition-colors"
              >
                Pause
              </button>
              <button
                type="button"
                onClick={() => uppyRef.current?.resumeAll()}
                className="rounded bg-emerald-500/20 border border-emerald-500/30 px-2.5 py-1 text-xs text-emerald-300 hover:bg-emerald-500/35 transition-colors"
              >
                Resume
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Retry button on error */}
      {uploadState === "error" && (
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-red-500/10 border border-red-500/20">
          <span className="text-xs text-red-400 font-medium">Upload failed or interrupted.</span>
          <button
            type="button"
            onClick={() => {
              setUploadState("uploading");
              uppyRef.current?.retryAll();
            }}
            className="rounded bg-red-600 px-3 py-1 text-xs font-semibold text-white hover:bg-red-700 transition-colors"
          >
            Retry Upload
          </button>
        </div>
      )}

      {/* Upload button */}
      <button
        type="button"
        disabled={!hasFile || isUploading || (passwordNeeded && !password)}
        onClick={startUpload}
        className={`w-full sm:w-auto px-6 py-2.5 rounded-lg text-sm font-semibold transition-all
          ${hasFile && !isUploading
            ? "bg-purple-600 hover:bg-purple-700 text-white shadow-md"
            : "bg-white/10 text-slate-400 cursor-not-allowed"
          } disabled:opacity-50`}
      >
        {isUploading
          ? "Uploading…"
          : passwordNeeded
            ? "Unlock & Upload"
            : selectedFileNames.length > 1
              ? `Upload ${selectedFileNames.length} Statements`
              : "Upload Statement"}
      </button>
    </div>
  );
}
