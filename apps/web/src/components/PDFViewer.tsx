"use client";

import { useState, useEffect } from "react";
import * as pdfjs from "pdfjs-dist";

interface PDFViewerProps {
  fileUrl: string;
}

export function PDFViewer({ fileUrl }: PDFViewerProps) {
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Set up PDF.js worker
  useEffect(() => {
    if (typeof window !== "undefined") {
      pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;
    }
  }, []);

  useEffect(() => {
    const loadPdf = async () => {
      try {
        setLoading(true);
        setError(null);
        const pdf = await pdfjs.getDocument(fileUrl).promise;
        setNumPages(pdf.numPages);
        setCurrentPage(1);
      } catch (err) {
        setError("Failed to load PDF");
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    if (fileUrl) {
      loadPdf();
    }
  }, [fileUrl]);

  const handleNextPage = () => {
    if (currentPage < numPages) {
      setCurrentPage(currentPage + 1);
    }
  };

  const handlePrevPage = () => {
    if (currentPage > 1) {
      setCurrentPage(currentPage - 1);
    }
  };

  const zoomPercentage = Math.round(zoom * 100);

  if (error) {
    return (
      <div
        data-testid="pdf-viewer"
        className="flex flex-col items-center justify-center h-full bg-black/30 backdrop-blur-xl border border-white/10 rounded-lg p-8 text-white"
      >
        <div className="text-center">
          <p className="text-red-400 mb-4">{error}</p>
          <a
            href={fileUrl}
            download
            className="text-blue-400 hover:text-blue-300 underline"
          >
            Download PDF instead
          </a>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div
        data-testid="pdf-viewer"
        className="space-y-2 bg-black/30 backdrop-blur-xl border border-white/10 rounded-lg p-4"
      >
        {[...Array(8)].map((_, i) => (
          <div
            key={i}
            className="h-8 bg-white/5 rounded animate-pulse"
          />
        ))}
      </div>
    );
  }

  return (
    <div
      data-testid="pdf-viewer"
      className="flex flex-col h-full bg-black/30 backdrop-blur-xl border border-white/10 rounded-lg overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-white/10 bg-black/40">
        <div className="flex items-center gap-2">
          <button
            onClick={handlePrevPage}
            disabled={currentPage === 1}
            className="px-3 py-1 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed text-white text-sm transition-all"
          >
            ← Prev
          </button>
          <span className="text-white text-sm px-2">
            {currentPage} / {numPages}
          </span>
          <button
            onClick={handleNextPage}
            disabled={currentPage === numPages}
            className="px-3 py-1 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed text-white text-sm transition-all"
          >
            Next →
          </button>
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-3">
          <input
            type="range"
            min="0.5"
            max="2"
            step="0.1"
            value={zoom}
            onChange={(e) => setZoom(parseFloat(e.target.value))}
            className="w-24"
          />
          <span className="text-white text-sm min-w-[50px] text-right">
            {zoomPercentage}%
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto flex items-center justify-center p-4">
        <div className="text-white text-center">
          <p className="text-gray-400">
            PDF preview - Page {currentPage} of {numPages}
          </p>
          <p className="text-sm text-gray-500 mt-2">
            Full PDF viewer rendering coming soon.
            <br />
            Download to view the complete document.
          </p>
        </div>
      </div>
    </div>
  );
}
