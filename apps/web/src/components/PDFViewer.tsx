"use client";

import { ComponentType, ReactNode, useEffect, useState } from "react";
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
    </div>
  );
}
