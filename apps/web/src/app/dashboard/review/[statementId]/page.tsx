"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Moon, Sun } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import ExportModal, { type ExportJob } from "@/components/ExportModal";
import { PDFViewer, type BboxCoords } from "@/components/PDFViewer";
import { TransactionTable } from "@/components/TransactionTable";
import { OcrStatusScreen } from "@/components/OcrStatusScreen";
import { useUndoRedo } from "@/components/useUndoRedo";
import { useReviewStore } from "@/lib/local-store";

const API = "/api";

type StatementMeta = {
  id: string;
  filename: string;
  bank: string;
  file_type?: string;
  error?: string | null;
  status: string;
};

type Transaction = {
  id: string;
  statement_id?: string;
  txn_date?: string;
  narration?: string;
  narration_clean?: string;
  reference_no?: string;
  counterparty?: string;
  debit?: number | string | null;
  credit?: number | string | null;
  balance?: number | string | null;
  payment_mode?: string;
  confirmed_ledger?: string;
  suggested_ledger?: string;
  confidence?: number | string | null;
  ocr_confidence?: number | string | null;
  page_number?: number | null;
  is_ignored?: boolean;
};

type Toast = {
  id: number;
  type: "success" | "error";
  message: string;
};

type StatusPayload = {
  id: string;
  filename?: string;
  bank?: string;
  bank_code?: string;
  bank_id?: string;
  file_type?: string;
  error?: string | null;
  status: string;
};

type TransactionsPayload = {
  items?: Transaction[];
  total?: number;
  pages?: number;
};

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token") || localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function unwrap<T>(payload: T | { data: T }): T {
  return payload && typeof payload === "object" && "data" in payload ? (payload as { data: T }).data : (payload as T);
}

function statusClass(status: string) {
  const classes: Record<string, string> = {
    UPLOADED: "bg-blue-500/20 text-blue-200",
    PARSING: "bg-yellow-500/20 text-yellow-200 animate-pulse",
    OCR: "bg-yellow-500/20 text-yellow-200 animate-pulse",
    READY_FOR_REVIEW: "bg-green-500/20 text-green-200",
    REVIEWED: "bg-purple-500/20 text-purple-200",
    EXPORTED: "bg-cyan-500/20 text-cyan-200",
    FAILED: "bg-red-500/20 text-red-200",
    PARSE_ERROR: "bg-red-500/20 text-red-200",
  };
  return classes[status] ?? "bg-white/10 text-white";
}

export default function ReviewPage() {
  const params = useParams<{ statementId: string }>();
  const statementId = params.statementId;
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [pagination, setPagination] = useState<{ total: number; pages: number } | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [midnightMode, setMidnightMode] = useState(true);
  
  // Zustand store for UI states
  const {
    selectedPage,
    selectedBbox,
    activeTab,
    setSelectedPage,
    setSelectedBbox,
    setActiveTab,
  } = useReviewStore();

  const {
    state: transactions,
    set: setTransactions,
    reset: resetTransactions,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useUndoRedo<Transaction[]>([]);
  const [enriching, setEnriching] = useState(false);
  const [exportModalOpen, setExportModalOpen] = useState(false);

  const addToast = useCallback((type: Toast["type"], message: string) => {
    const id = Date.now();
    setToasts((items) => [...items, { id, type, message }]);
    window.setTimeout(() => {
      setToasts((items) => items.filter((toast) => toast.id !== id));
    }, 4000);
  }, []);

  const fileUrl = useMemo(
    () => `${API}/v1/statements/${statementId}/file`,
    [statementId]
  );

  // TanStack Query for Statement Meta
  const { data: statement } = useQuery<StatementMeta>({
    queryKey: ["statement", statementId],
    queryFn: async () => {
      const res = await fetch(`${API}/v1/statements/${statementId}/status`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Failed to load statement");
      const json = await res.json();
      const data = unwrap<StatusPayload>(json);
      return {
        id: data.id,
        filename: data.filename ?? "statement",
        bank: data.bank ?? data.bank_code ?? data.bank_id ?? "Unknown",
        file_type: data.file_type,
        error: data.error,
        status: data.status,
      };
    },
  });

  // TanStack Query for Transactions list
  const { data: txsData, isLoading: loading } = useQuery<TransactionsPayload>({
    queryKey: ["transactions", statementId, page, pageSize],
    queryFn: async () => {
      const res = await fetch(
        `${API}/v1/statements/${statementId}/transactions?page=${page}&size=${pageSize}`,
        { headers: authHeaders() }
      );
      if (!res.ok) throw new Error("Failed to load transactions");
      const json = await res.json();
      return unwrap<TransactionsPayload>(json);
    },
  });

  // Sync loaded transactions to useUndoRedo state
  useEffect(() => {
    if (txsData?.items) {
      resetTransactions(txsData.items);
      setPagination({ total: txsData.total ?? 0, pages: txsData.pages ?? 1 });
    }
  }, [txsData, resetTransactions]);

  // WebSocket cache invalidations
  useEffect(() => {
    const wsUrl = `${API.replace(/^http/, "ws")}/v1/ws/statements/${statementId}`;
    const socket = new WebSocket(wsUrl);
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "status") {
        queryClient.setQueryData(["statement", statementId], (old: any) =>
          old ? { ...old, status: data.status } : old
        );
        queryClient.invalidateQueries({ queryKey: ["statement", statementId] });
        queryClient.invalidateQueries({ queryKey: ["transactions", statementId] });
      }
      if (data.type === "ping") {
        socket.send(JSON.stringify({ type: "pong" }));
      }
    };
    return () => socket.close();
  }, [statementId, queryClient]);

  const handleRowClick = useCallback((txId: string, pageNumber: number | null, bbox: BboxCoords | null) => {
    if (pageNumber) {
      setSelectedPage(pageNumber);
      setSelectedBbox(bbox);
      // On mobile, auto-switch to PDF tab
      setActiveTab("pdf");
    }
  }, [setSelectedPage, setSelectedBbox, setActiveTab]);

  const isReadOnly = statement?.status === "REVIEWED" || statement?.status === "EXPORTED";
  const canExport = statement?.status === "READY_FOR_REVIEW" || statement?.status === "REVIEWED" || statement?.status === "EXPORTED";

  // Mutations
  const updateMutation = useMutation({
    mutationFn: async ({ txId, changes }: { txId: string; changes: Partial<Transaction> }) => {
      const res = await fetch(`${API}/v1/statements/${statementId}/transactions/${txId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(changes),
      });
      if (!res.ok) throw new Error("Save failed");
      return res.json();
    },
    onMutate: async ({ txId, changes }) => {
      await queryClient.cancelQueries({ queryKey: ["transactions", statementId] });
      const previous = queryClient.getQueryData(["transactions", statementId, page, pageSize]);
      
      const next = transactions.map((tx) => (tx.id === txId ? { ...tx, ...changes } : tx));
      setTransactions(next);
      
      return { previous };
    },
    onError: (err, variables, context: any) => {
      if (context?.previous) {
        queryClient.setQueryData(["transactions", statementId, page, pageSize], context.previous);
        resetTransactions((context.previous as TransactionsPayload).items ?? []);
      }
      addToast("error", err.message || "Save failed");
    },
    onSuccess: () => {
      addToast("success", "Saved");
      queryClient.invalidateQueries({ queryKey: ["transactions", statementId] });
    },
  });

  const bulkUpdateMutation = useMutation({
    mutationFn: async ({ txIds, changes }: { txIds: string[]; changes: Partial<Transaction> }) => {
      const res = await fetch(`${API}/v1/statements/${statementId}/transactions/bulk-update`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ updates: txIds.map((id) => ({ id, ...changes })) }),
      });
      if (!res.ok) throw new Error("Bulk save failed");
      return res.json();
    },
    onMutate: async ({ txIds, changes }) => {
      await queryClient.cancelQueries({ queryKey: ["transactions", statementId] });
      const previous = queryClient.getQueryData(["transactions", statementId, page, pageSize]);
      
      const next = transactions.map((tx) => (txIds.includes(tx.id) ? { ...tx, ...changes } : tx));
      setTransactions(next);
      
      return { previous };
    },
    onError: (err, variables, context: any) => {
      if (context?.previous) {
        queryClient.setQueryData(["transactions", statementId, page, pageSize], context.previous);
        resetTransactions((context.previous as TransactionsPayload).items ?? []);
      }
      addToast("error", err.message || "Bulk save failed");
    },
    onSuccess: (_, variables) => {
      addToast("success", `Updated ${variables.txIds.length} transactions`);
      queryClient.invalidateQueries({ queryKey: ["transactions", statementId] });
    },
  });

  const updateTransaction = (txId: string, changes: Partial<Transaction>) => {
    if (isReadOnly) { addToast("error", "Statement is reviewed and locked — no edits allowed."); return; }
    updateMutation.mutate({ txId, changes });
  };

  const bulkUpdateTransactions = (txIds: string[], changes: Partial<Transaction>) => {
    if (isReadOnly) { addToast("error", "Statement is reviewed and locked — no edits allowed."); return; }
    bulkUpdateMutation.mutate({ txIds, changes });
  };

  const syncUndoRedoToBackend = async (targetState: Transaction[] | null, beforeState: Transaction[]) => {
    if (!targetState || isReadOnly) return;
    
    const updates: any[] = [];
    const targetById = new Map(targetState.map((tx) => [tx.id, tx]));
    
    for (const beforeTx of beforeState) {
      const targetTx = targetById.get(beforeTx.id);
      if (!targetTx) continue;
      
      const diff: any = {};
      const editableFields = ["narration", "narration_clean", "reference_no", "payment_mode", "counterparty", "suggested_ledger", "confirmed_ledger", "is_ignored"] as const;
      
      let hasChanges = false;
      for (const field of editableFields) {
        if (targetTx[field] !== beforeTx[field]) {
          diff[field] = targetTx[field];
          hasChanges = true;
        }
      }
      
      if (hasChanges) {
        updates.push({ id: targetTx.id, ...diff });
      }
    }
    
    if (updates.length > 0) {
      try {
        const res = await fetch(`${API}/v1/statements/${statementId}/transactions/bulk-update`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ updates }),
        });
        if (!res.ok) throw new Error("Undo/redo sync failed");
        addToast("success", `Restored ${updates.length} edits`);
      } catch (error) {
        addToast("error", error instanceof Error ? error.message : "Sync failed");
      }
    }
  };

  const handleUndo = async () => {
    const before = transactions;
    const target = undo();
    if (target) {
      await syncUndoRedoToBackend(target, before);
    }
  };

  const handleRedo = async () => {
    const before = transactions;
    const target = redo();
    if (target) {
      await syncUndoRedoToBackend(target, before);
    }
  };

  const enrichTransactions = async () => {
    setEnriching(true);
    try {
      const res = await fetch(`${API}/v1/statements/${statementId}/transactions/enrich`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        // force:true clears stale cache so confidence is always recomputed fresh
        body: JSON.stringify({ only_missing: false, force: true, limit: 200 }),
      });
      if (!res.ok) throw new Error("Enrichment failed");
      const data = (await res.json()).data;
      if (data.job_id && data.status === "PENDING") {
        for (let attempt = 0; attempt < 90; attempt += 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 2000));
          const jobRes = await fetch(`${API}/v1/jobs/${data.job_id}`, {
            headers: authHeaders(),
          });
          if (!jobRes.ok) continue;
          const jobPayload = (await jobRes.json()).data || {};
          if (jobPayload.status === "FAILED") {
            throw new Error(jobPayload.detail || "Enrichment failed");
          }
          if (jobPayload.status === "COMPLETED") {
            addToast("success", "Enrichment complete");
            queryClient.invalidateQueries({ queryKey: ["transactions", statementId] });
            return;
          }
        }
        throw new Error("Enrichment is still running. Please refresh shortly.");
      }
      addToast("success", `Enriched ${data.updated} transactions`);
      queryClient.invalidateQueries({ queryKey: ["transactions", statementId] });
    } catch (error) {
      addToast("error", error instanceof Error ? error.message : "Enrichment failed");
    } finally {
      setEnriching(false);
    }
  };

  const markReviewed = async () => {
    try {
      const res = await fetch(`${API}/v1/statements/${statementId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ status: "REVIEWED" }),
      });
      if (!res.ok) throw new Error("Could not mark reviewed");
      queryClient.invalidateQueries({ queryKey: ["statement", statementId] });
      addToast("success", "Marked reviewed");
    } catch (error) {
      addToast("error", error instanceof Error ? error.message : "Could not mark reviewed");
    }
  };

  const handleExportComplete = (job: ExportJob) => {
    queryClient.invalidateQueries({ queryKey: ["statement", statementId] });
    addToast("success", job.idempotent ? "Export is ready" : "Statement exported");
  };

  const isPdf = statement?.file_type?.toLowerCase() === "pdf";
  const filePreview = isPdf ? (
    <PDFViewer
      fileUrl={fileUrl}
      targetPage={selectedPage}
      highlightBbox={selectedBbox}
      darkMode={midnightMode}
    />
  ) : (
    <div
      data-testid="pdf-viewer"
      className={`flex h-full min-h-[420px] flex-col items-center justify-center rounded-lg border p-6 text-center backdrop-blur-xl ${
        midnightMode
          ? "border-white/10 bg-[#06111f] text-white"
          : "border-slate-200 bg-white text-slate-900 shadow-sm"
      }`}
    >
      <p className="text-lg font-semibold">PDF preview is available for PDF files</p>
      <p className={`mt-2 max-w-md text-sm ${midnightMode ? "text-slate-300" : "text-slate-600"}`}>
        This statement is a {statement?.file_type?.toUpperCase() || "non-PDF"} file. Review extracted transactions on the right or download the original file.
      </p>
      <a
        className="mt-5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        href={fileUrl}
        download
      >
        Download original
      </a>
    </div>
  );

  return (
    <div className={`min-h-screen transition-colors duration-300 ${midnightMode ? "bg-[#030b1a] text-white" : "bg-slate-50 text-slate-950"}`}>
      {/* OCR in-progress overlay */}
      {statement?.status === "OCR" && (
        <OcrStatusScreen
          statementId={statementId}
          status={statement.status}
          onComplete={() => {
            queryClient.invalidateQueries({ queryKey: ["statement", statementId] });
            queryClient.invalidateQueries({ queryKey: ["transactions", statementId] });
          }}
        />
      )}

      <div className="fixed right-4 top-20 z-50 space-y-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`rounded-lg px-4 py-2 text-sm shadow-lg ${
              toast.type === "success" ? "bg-emerald-600" : "bg-red-600"
            }`}
          >
            {toast.message}
          </div>
        ))}
      </div>

      <header className={`sticky top-0 z-40 border-b backdrop-blur ${
        midnightMode
          ? "border-white/10 bg-[#030b1a]/95"
          : "border-slate-200 bg-white/90"
      }`}>
        <div className="flex min-h-16 flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <Link href="/dashboard" className={`flex items-center gap-2 text-sm ${
              midnightMode ? "text-slate-300 hover:text-white" : "text-slate-600 hover:text-slate-950"
            }`}>
              <ArrowLeft size={16} /> Dashboard
            </Link>
            <span className="truncate font-semibold">{statement?.filename ?? "Statement"}</span>
            <span className={`rounded-full px-2 py-1 text-xs uppercase ${
              midnightMode ? "bg-white/10 text-slate-200" : "bg-slate-200 text-slate-700"
            }`}>
              {statement?.bank ?? "Unknown"}
            </span>
            <span className={`rounded-full px-2 py-1 text-xs ${statusClass(statement?.status ?? "")}`}>
              {statement?.status ?? "LOADING"}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setMidnightMode((value) => !value)}
              title={midnightMode ? "Switch page to light mode" : "Switch page to midnight black"}
              className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition ${
                midnightMode
                  ? "bg-white/10 text-slate-100 hover:bg-white/15"
                  : "bg-slate-200 text-slate-800 hover:bg-slate-300"
              }`}
            >
              {midnightMode ? <Sun size={16} /> : <Moon size={16} />}
              {midnightMode ? "Light" : "Midnight"}
            </button>
            <button className="rounded-lg bg-white/10 px-3 py-2 text-sm disabled:opacity-40" disabled={!canUndo} onClick={handleUndo}>
              Undo
            </button>
            <button className="rounded-lg bg-white/10 px-3 py-2 text-sm disabled:opacity-40" disabled={!canRedo} onClick={handleRedo}>
              Redo
            </button>
            <button
              className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium disabled:opacity-40"
              disabled={enriching || isReadOnly}
              onClick={enrichTransactions}
              title={isReadOnly ? "Statement is locked" : "Run AI enrichment"}
            >
              {enriching ? "Enriching…" : "✨ Enrich AI"}
            </button>
            <button
              className="rounded-lg bg-purple-600 px-3 py-2 text-sm font-medium disabled:opacity-40"
              disabled={statement?.status === "REVIEWED" || statement?.status === "EXPORTED"}
              onClick={markReviewed}
            >
              Mark Reviewed
            </button>
            <button
              className="rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!canExport}
              onClick={() => setExportModalOpen(true)}
            >
              Export
            </button>
          </div>
        </div>
      </header>

      <main className="h-[calc(100vh-65px)]">
        {isReadOnly && (
          <div className="flex items-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
            <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
            <span><strong>Read-only</strong> — This statement is reviewed and locked. No edits are allowed.</span>
          </div>
        )}
        {statement?.error && (
          <div className="border-b border-yellow-500/20 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-100">
            {statement.error}
          </div>
        )}
        <div className={`grid grid-cols-2 border-b sm:hidden ${midnightMode ? "border-white/10" : "border-slate-200"}`}>
          <button
            className={`py-3 text-sm ${activeTab === "transactions" ? (midnightMode ? "bg-white/10" : "bg-slate-200") : ""}`}
            onClick={() => setActiveTab("transactions")}
          >
            Transactions
          </button>
          <button
            className={`py-3 text-sm ${activeTab === "pdf" ? (midnightMode ? "bg-white/10" : "bg-slate-200") : ""}`}
            onClick={() => setActiveTab("pdf")}
          >
            PDF Preview
          </button>
        </div>

        <div className="hidden h-full grid-cols-[40%_60%] sm:grid">
          <section className={`h-full overflow-hidden border-r p-4 ${midnightMode ? "border-white/10" : "border-slate-200"}`}>
            {filePreview}
          </section>
          <section className="h-full overflow-auto p-4">
            <TransactionTable
              statementId={statementId}
              transactions={transactions}
              loading={loading}
              onUpdate={updateTransaction}
              pagination={pagination}
              page={page}
              pageSize={pageSize}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
              onBulkUpdate={bulkUpdateTransactions}
              onRowClick={handleRowClick}
              darkMode={midnightMode}
            />
          </section>
        </div>

        <div className="h-full p-4 sm:hidden">
          {activeTab === "pdf" ? (
            filePreview
          ) : (
            <TransactionTable
              statementId={statementId}
              transactions={transactions}
              loading={loading}
              onUpdate={updateTransaction}
              pagination={pagination}
              page={page}
              pageSize={pageSize}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
              onBulkUpdate={bulkUpdateTransactions}
              onRowClick={handleRowClick}
              darkMode={midnightMode}
            />
          )}
        </div>
      </main>

      {statement && (
        <ExportModal
          statementId={statementId}
          statementFilename={statement.filename}
          bankId={statement.bank}
          isOpen={exportModalOpen}
          onClose={() => setExportModalOpen(false)}
          onExportComplete={handleExportComplete}
        />
      )}
    </div>
  );
}


