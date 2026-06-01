"use client";

import { useEffect, useState } from "react";

interface OcrStatusScreenProps {
  /** Statement ID to subscribe to OCR progress */
  statementId: string;
  /** Current statement status */
  status: string;
  /** Optional: callback when OCR completes */
  onComplete?: () => void;
}

type OcrProgressEvent = {
  type: "ocr_progress";
  statement_id: string;
  page_current: number;
  page_total: number;
  engine: string;
  confidence_so_far?: number;
};

/**
 * Full-screen OCR progress overlay.
 * Shows animated scanning visual with page-by-page progress.
 * Listens to WebSocket for real-time OCR progress events.
 */
export function OcrStatusScreen({ statementId, status, onComplete }: OcrStatusScreenProps) {
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [engine, setEngine] = useState<string | null>(null);
  const [avgConfidence, setAvgConfidence] = useState<number | null>(null);
  const [phase, setPhase] = useState<"preprocessing" | "scanning" | "parsing" | "done">(
    "preprocessing"
  );

  // Listen for OCR progress events via WebSocket
  useEffect(() => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${window.location.host}/api/v1/ws/statements/${statementId}`;
    const socket = new WebSocket(wsUrl);

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === "ocr_progress") {
          const ocrData = data as OcrProgressEvent;
          setProgress({ current: ocrData.page_current, total: ocrData.page_total });
          setEngine(ocrData.engine);
          if (ocrData.confidence_so_far != null) {
            setAvgConfidence(ocrData.confidence_so_far);
          }
          setPhase("scanning");
        }

        if (data.type === "status") {
          if (data.status === "READY_FOR_REVIEW") {
            setPhase("done");
            onComplete?.();
          }
        }

        if (data.type === "ping") {
          socket.send(JSON.stringify({ type: "pong" }));
        }
      } catch {
        /* ignore parse errors */
      }
    };

    return () => socket.close();
  }, [statementId, onComplete]);

  // Auto-advance through preprocessing phases
  useEffect(() => {
    if (phase === "preprocessing") {
      const timer = setTimeout(() => setPhase("scanning"), 2000);
      return () => clearTimeout(timer);
    }
  }, [phase]);

  // Don't show if status isn't OCR
  if (status !== "OCR" && phase !== "done") return null;

  const percent =
    progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-xl">
      <div className="relative w-full max-w-lg mx-4">
        {/* Animated background effects */}
        <div className="absolute -inset-4 rounded-3xl bg-gradient-to-r from-blue-500/20 via-violet-500/20 to-cyan-500/20 blur-2xl animate-pulse" />

        <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-slate-900/90 p-8 shadow-2xl">
          {/* Scanning animation header */}
          <div className="flex flex-col items-center mb-8">
            {/* Animated scanner icon */}
            <div className="relative mb-6">
              <div className="h-24 w-24 rounded-2xl bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center shadow-lg shadow-blue-500/30">
                <svg
                  className="h-12 w-12 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1.5}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M7.5 3.75H6A2.25 2.25 0 003.75 6v1.5M16.5 3.75H18A2.25 2.25 0 0120.25 6v1.5m0 9V18A2.25 2.25 0 0118 20.25h-1.5m-9 0H6A2.25 2.25 0 013.75 18v-1.5"
                  />
                </svg>

                {/* Scanning line animation */}
                {phase === "scanning" && (
                  <div className="absolute inset-x-0 h-0.5 bg-gradient-to-r from-transparent via-cyan-400 to-transparent animate-scan-line" />
                )}
              </div>

              {/* Pulsing ring */}
              <div className="absolute -inset-2 rounded-2xl border-2 border-blue-400/30 animate-ping" />
            </div>

            {/* Phase text */}
            <h2 className="text-xl font-semibold text-white mb-1">
              {phase === "preprocessing" && "Preparing Document..."}
              {phase === "scanning" && "OCR Scanning in Progress"}
              {phase === "parsing" && "Parsing Results..."}
              {phase === "done" && "OCR Complete!"}
            </h2>

            <p className="text-sm text-slate-400 text-center max-w-sm">
              {phase === "preprocessing" &&
                "Pre-processing images: applying grayscale, denoising, and adaptive thresholding"}
              {phase === "scanning" &&
                "Extracting text from scanned pages using optical character recognition"}
              {phase === "parsing" && "Organizing extracted data into structured transaction rows"}
              {phase === "done" && "All pages have been scanned and transactions extracted"}
            </p>
          </div>

          {/* Progress bar */}
          <div className="mb-6">
            <div className="flex items-center justify-between text-sm mb-2">
              <span className="text-slate-300 font-medium">
                {progress.total > 0
                  ? `Page ${progress.current} of ${progress.total}`
                  : "Initializing..."}
              </span>
              <span className="text-blue-400 font-mono">{percent}%</span>
            </div>

            <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500 transition-all duration-500 ease-out"
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>

          {/* Stats row */}
          <div className="grid grid-cols-3 gap-3">
            {/* Engine */}
            <div className="rounded-xl border border-white/5 bg-white/5 p-3 text-center">
              <p className="text-xs text-slate-500 mb-1">Engine</p>
              <p className="text-sm font-medium text-white">
                {engine
                  ? engine.charAt(0).toUpperCase() + engine.slice(1)
                  : "—"}
              </p>
            </div>

            {/* Pages */}
            <div className="rounded-xl border border-white/5 bg-white/5 p-3 text-center">
              <p className="text-xs text-slate-500 mb-1">Pages</p>
              <p className="text-sm font-medium text-white">
                {progress.total > 0 ? `${progress.current}/${progress.total}` : "—"}
              </p>
            </div>

            {/* Confidence */}
            <div className="rounded-xl border border-white/5 bg-white/5 p-3 text-center">
              <p className="text-xs text-slate-500 mb-1">Avg Confidence</p>
              <p
                className={`text-sm font-medium ${
                  avgConfidence == null
                    ? "text-white"
                    : avgConfidence >= 0.85
                      ? "text-green-400"
                      : avgConfidence >= 0.7
                        ? "text-yellow-400"
                        : "text-red-400"
                }`}
              >
                {avgConfidence != null ? `${Math.round(avgConfidence * 100)}%` : "—"}
              </p>
            </div>
          </div>

          {/* Phase dots indicator */}
          <div className="flex items-center justify-center gap-2 mt-6">
            {(["preprocessing", "scanning", "parsing", "done"] as const).map((p, i) => (
              <div key={p} className="flex items-center gap-2">
                <div
                  className={`h-2 w-2 rounded-full transition-all duration-300 ${
                    phase === p
                      ? "bg-blue-400 scale-125 ring-2 ring-blue-400/30"
                      : (["preprocessing", "scanning", "parsing", "done"] as const).indexOf(phase) > i
                        ? "bg-blue-400/60"
                        : "bg-slate-700"
                  }`}
                />
                {i < 3 && (
                  <div
                    className={`h-0.5 w-6 rounded-full ${
                      (["preprocessing", "scanning", "parsing", "done"] as const).indexOf(phase) > i
                        ? "bg-blue-400/40"
                        : "bg-slate-800"
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CSS for scan line animation */}
      <style jsx>{`
        @keyframes scan-line {
          0% {
            top: 0;
          }
          50% {
            top: calc(100% - 2px);
          }
          100% {
            top: 0;
          }
        }
        .animate-scan-line {
          position: absolute;
          left: 4px;
          right: 4px;
          animation: scan-line 2s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}
