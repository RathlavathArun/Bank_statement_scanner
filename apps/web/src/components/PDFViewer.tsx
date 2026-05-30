"use client";

import { ComponentType, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

type PDFViewerProps = {
  fileUrl: string;
};

type DocumentProps = {
  file: string;
  loading: ReactNode;
  error: ReactNode;
  onLoadError?: () => void;
  onSourceError?: () => void;
  onLoadSuccess: (meta: { numPages: number }) => void;
  onPassword?: (callback: (password: string) => void, reason: number) => void;
  children: ReactNode;
};

type PageProps = {
  pageNumber: number;
  scale: number;
  renderAnnotationLayer: boolean;
  renderTextLayer: boolean;
};

type ReactPdfModule = {
  Document: ComponentType<DocumentProps>;
  Page: ComponentType<PageProps>;
  pdfjs: {
    version: string;
    GlobalWorkerOptions: {
      workerSrc: string;
    };
  };
};

export function PDFViewer({ fileUrl }: PDFViewerProps) {
  const [reactPdf, setReactPdf] = useState<ReactPdfModule | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [viewerError, setViewerError] = useState(false);

  // Password-prompt state
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [pdfPassword, setPdfPassword] = useState("");
  const [passwordError, setPasswordError] = useState(false);
  const passwordCallbackRef = useRef<((password: string) => void) | null>(null);
  const passwordInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadRenderer = async () => {
      try {
        const mod = await import("react-pdf");
        mod.pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${mod.pdfjs.version}/build/pdf.worker.min.mjs`;
        if (!cancelled) {
          setReactPdf(mod as ReactPdfModule);
        }
      } catch (error) {
        console.error("PDF renderer failed to load", error);
        if (!cancelled) {
          setViewerError(true);
        }
      }
    };

    void loadRenderer();

    return () => {
      cancelled = true;
    };
  }, []);

  // Auto-focus the password input when modal opens
  useEffect(() => {
    if (showPasswordModal) {
      setTimeout(() => passwordInputRef.current?.focus(), 50);
    }
  }, [showPasswordModal]);

  const handlePassword = useCallback(
    (callback: (password: string) => void, reason: number) => {
      // reason 1 = need password, reason 2 = incorrect password
      passwordCallbackRef.current = callback;
      setPasswordError(reason === 2);
      setPdfPassword("");
      setShowPasswordModal(true);
    },
    []
  );

  const submitPassword = () => {
    if (passwordCallbackRef.current && pdfPassword) {
      passwordCallbackRef.current(pdfPassword);
      setShowPasswordModal(false);
    }
  };

  const cancelPassword = () => {
    setShowPasswordModal(false);
    passwordCallbackRef.current = null;
    setViewerError(true);
  };

  const loading = (
    <div className="space-y-2 p-4">
      {Array.from({ length: 8 }).map((_, index) => (
        <div key={index} className="h-8 animate-pulse rounded bg-white/5" />
      ))}
    </div>
  );

  const fallback = (
    <div className="flex min-h-[320px] flex-col items-center justify-center text-center">
      <p className="mb-4 text-red-300">PDF preview not available</p>
      <a className="text-blue-300 underline" href={fileUrl} download>
        Download file
      </a>
    </div>
  );

  const Document = reactPdf?.Document;
  const Page = reactPdf?.Page;

  return (
    <div
      data-testid="pdf-viewer"
      className="flex h-full min-h-[420px] flex-col overflow-hidden rounded-lg border border-white/10 bg-black/30 text-white backdrop-blur-xl"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-black/40 p-4">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
            disabled={currentPage <= 1}
            className="rounded-lg bg-white/10 px-3 py-1 text-sm transition hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-30"
          >
            Prev
          </button>
          <span className="min-w-16 text-center text-sm">
            {currentPage} / {numPages || 1}
          </span>
          <button
            type="button"
            onClick={() => setCurrentPage((page) => Math.min(numPages || 1, page + 1))}
            disabled={currentPage >= numPages}
            className="rounded-lg bg-white/10 px-3 py-1 text-sm transition hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-30"
          >
            Next
          </button>
        </div>

        <label className="flex items-center gap-3 text-sm">
          <input
            type="range"
            min="0.5"
            max="2"
            step="0.1"
            value={zoom}
            onChange={(event) => setZoom(Number(event.target.value))}
            className="w-28"
          />
          <span className="min-w-12 text-right">{Math.round(zoom * 100)}%</span>
        </label>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {viewerError || !Document || !Page ? (
          viewerError ? fallback : loading
        ) : (
          <Document
            file={fileUrl}
            loading={loading}
            error={fallback}
            onLoadError={() => setViewerError(true)}
            onSourceError={() => setViewerError(true)}
            onPassword={handlePassword}
            onLoadSuccess={({ numPages: loadedPages }) => {
              setNumPages(loadedPages);
              setCurrentPage(1);
            }}
          >
            <div className="flex justify-center">
              <Page
                pageNumber={currentPage}
                scale={zoom}
                renderAnnotationLayer
                renderTextLayer
              />
            </div>
          </Document>
        )}
      </div>

      {/* Password modal overlay */}
      {showPasswordModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-xl border border-white/10 bg-slate-900 p-6 shadow-2xl">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-500/20">
                <svg className="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">
                  {passwordError ? "Incorrect password" : "Password required"}
                </h3>
                <p className="text-xs text-slate-400">
                  {passwordError
                    ? "The password you entered is incorrect. Please try again."
                    : "This PDF is password-protected. Enter the password to view it."}
                </p>
              </div>
            </div>

            <input
              ref={passwordInputRef}
              type="password"
              placeholder="Enter PDF password"
              value={pdfPassword}
              onChange={(e) => setPdfPassword(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submitPassword(); }}
              className="mb-4 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white
                         placeholder:text-slate-500 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={cancelPassword}
                className="rounded-lg px-4 py-1.5 text-sm text-slate-400 transition hover:bg-white/5 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={submitPassword}
                disabled={!pdfPassword}
                className="rounded-lg bg-amber-600 px-4 py-1.5 text-sm font-medium text-white transition
                           hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Unlock
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
