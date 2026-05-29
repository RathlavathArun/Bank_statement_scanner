"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { PDFViewer } from "@/components/PDFViewer";
import { TransactionTable } from "@/components/TransactionTable";
import { useUndoRedo } from "@/components/useUndoRedo";

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
  debit?: number | string | null;
  credit?: number | string | null;
  balance?: number | string | null;
  payment_mode?: string;
  confirmed_ledger?: string;
  suggested_ledger?: string;
  confidence?: number | string | null;
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
  const [statement, setStatement] = useState<StatementMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [pagination, setPagination] = useState<{ total: number; pages: number } | null>(null);
  const [activeTab, setActiveTab] = useState<"transactions" | "pdf">("transactions");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const {
    state: transactions,
    set: setTransactions,
    reset: resetTransactions,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useUndoRedo<Transaction[]>([]);

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

  const loadStatement = useCallback(async () => {
    const res = await fetch(`${API}/v1/statements/${statementId}/status`, {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error("Failed to load statement");
    const data = unwrap<StatusPayload>(await res.json());
    setStatement({
      id: data.id,
      filename: data.filename ?? "statement",
      bank: data.bank ?? data.bank_code ?? data.bank_id ?? "Unknown",
      file_type: data.file_type,
      error: data.error,
      status: data.status,
    });
  }, [statementId]);

  const loadTransactions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `${API}/v1/statements/${statementId}/transactions?page=${page}&size=${pageSize}`,
        { headers: authHeaders() }
      );
      if (!res.ok) throw new Error("Failed to load transactions");
      const data = unwrap<TransactionsPayload>(await res.json());
      resetTransactions(data.items ?? []);
      setPagination({ total: data.total ?? 0, pages: data.pages ?? 1 });
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, resetTransactions, statementId]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        await loadStatement();
      } catch {
        if (!cancelled) addToast("error", "Could not load statement");
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [addToast, loadStatement]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        await loadTransactions();
      } catch {
        if (!cancelled) addToast("error", "Could not load transactions");
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [addToast, loadTransactions]);

  useEffect(() => {
    const wsUrl = `${API.replace(/^http/, "ws")}/v1/ws/statements/${statementId}`;
    const socket = new WebSocket(wsUrl);
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "status") {
        setStatement((current) => current ? { ...current, status: data.status } : current);
      }
      if (data.type === "ping") {
        socket.send(JSON.stringify({ type: "pong" }));
      }
    };
    return () => socket.close();
  }, [statementId]);

  const updateTransaction = async (txId: string, changes: Partial<Transaction>) => {
    const before = transactions;
    const next = before.map((tx) => (tx.id === txId ? { ...tx, ...changes } : tx));
    setTransactions(next);

    try {
      const res = await fetch(`${API}/v1/statements/${statementId}/transactions/${txId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(changes),
      });
      if (!res.ok) throw new Error("Save failed");
      addToast("success", "Saved");
    } catch (error) {
      resetTransactions(before);
      addToast("error", error instanceof Error ? error.message : "Save failed");
    }
  };

  const bulkUpdateTransactions = async (txIds: string[], changes: Partial<Transaction>) => {
    const before = transactions;
    const next = before.map((tx) => (txIds.includes(tx.id) ? { ...tx, ...changes } : tx));
    setTransactions(next);

    try {
      const res = await fetch(`${API}/v1/statements/${statementId}/transactions/bulk-update`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ ids: txIds, updates: changes }),
      });
      if (!res.ok) throw new Error("Bulk save failed");
      addToast("success", `Updated ${txIds.length} transactions`);
    } catch (error) {
      resetTransactions(before);
      addToast("error", error instanceof Error ? error.message : "Bulk save failed");
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
      setStatement((current) => current ? { ...current, status: "REVIEWED" } : current);
      addToast("success", "Marked reviewed");
    } catch (error) {
      addToast("error", error instanceof Error ? error.message : "Could not mark reviewed");
    }
  };

  const isPdf = statement?.file_type?.toLowerCase() === "pdf";
  const filePreview = isPdf ? (
    <PDFViewer fileUrl={fileUrl} />
  ) : (
    <div
      data-testid="file-preview-fallback"
      className="flex h-full min-h-[420px] flex-col items-center justify-center rounded-lg border border-white/10 bg-black/30 p-6 text-center text-white backdrop-blur-xl"
    >
      <p className="text-lg font-semibold">PDF preview is available for PDF files</p>
      <p className="mt-2 max-w-md text-sm text-slate-300">
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
    <div className="min-h-screen bg-slate-950 text-white">
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

      <header className="sticky top-0 z-40 border-b border-white/10 bg-slate-950/90 backdrop-blur">
        <div className="flex min-h-16 flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <Link href="/dashboard" className="flex items-center gap-2 text-sm text-slate-300 hover:text-white">
              <ArrowLeft size={16} /> Dashboard
            </Link>
            <span className="truncate font-semibold">{statement?.filename ?? "Statement"}</span>
            <span className="rounded-full bg-white/10 px-2 py-1 text-xs uppercase text-slate-200">
              {statement?.bank ?? "Unknown"}
            </span>
            <span className={`rounded-full px-2 py-1 text-xs ${statusClass(statement?.status ?? "")}`}>
              {statement?.status ?? "LOADING"}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button className="rounded-lg bg-white/10 px-3 py-2 text-sm disabled:opacity-40" disabled={!canUndo} onClick={undo}>
              Undo
            </button>
            <button className="rounded-lg bg-white/10 px-3 py-2 text-sm disabled:opacity-40" disabled={!canRedo} onClick={redo}>
              Redo
            </button>
            <button
              className="rounded-lg bg-purple-600 px-3 py-2 text-sm font-medium disabled:opacity-40"
              disabled={statement?.status === "REVIEWED"}
              onClick={markReviewed}
            >
              Mark Reviewed
            </button>
            <button className="rounded-lg bg-white/10 px-3 py-2 text-sm opacity-40" disabled title="Coming in Phase 5">
              Export
            </button>
          </div>
        </div>
      </header>

      <main className="h-[calc(100vh-65px)]">
        {statement?.error && (
          <div className="border-b border-yellow-500/20 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-100">
            {statement.error}
          </div>
        )}
        <div className="grid grid-cols-2 border-b border-white/10 sm:hidden">
          <button
            className={`py-3 text-sm ${activeTab === "transactions" ? "bg-white/10" : ""}`}
            onClick={() => setActiveTab("transactions")}
          >
            Transactions
          </button>
          <button
            className={`py-3 text-sm ${activeTab === "pdf" ? "bg-white/10" : ""}`}
            onClick={() => setActiveTab("pdf")}
          >
            PDF Preview
          </button>
        </div>

        <div className="hidden h-full grid-cols-[40%_60%] sm:grid">
          <section className="h-full overflow-hidden border-r border-white/10 p-4">
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
            />
          )}
        </div>
      </main>
    </div>
  );
}
