"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

type ExtractedTransaction = {
  id: string;
  date: string;
  description: string;
  debit: string | null;
  credit: string | null;
  balance: string | null;
  suggested_ledger: string | null;
  confirmed_ledger: string | null;
  confidence: number | null;
  is_ignored: boolean;
  page_number?: number | null;
};

type StatementDetails = {
  id: string;
  filename: string;
  bank: string;
  status: string;
  path: string;
  file_type?: string;
  error: string | null;
};

const DEFAULT_LEDGERS = [
  "Sundry Debtors",
  "Sundry Creditors",
  "Salaries",
  "Rent",
  "Printing & Stationery",
  "Bank Charges",
  "Office Expenses",
  "UPI/Suspense",
  "Interest Earned",
  "Director Remuneration"
];

export default function ReviewStatementPage() {
  const params = useParams();
  const router = useRouter();
  const statementId = params.id as string;

  const [statement, setStatement] = useState<StatementDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Undo/Redo & Transactions State
  const [transactions, setTransactions] = useState<ExtractedTransaction[]>([]);
  const [historyPast, setHistoryPast] = useState<ExtractedTransaction[][]>([]);
  const [historyFuture, setHistoryFuture] = useState<ExtractedTransaction[][]>([]);

  // Selected rows for bulk operations
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Search & Filters
  const [searchTerm, setSearchTerm] = useState("");
  const [ledgerFilter, setLedgerFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [minAmount, setMinAmount] = useState("");
  const [maxAmount, setMaxAmount] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | "debit" | "credit">("all");
  const [confidenceFilter, setConfidenceFilter] = useState(false); // only low confidence (< 0.8)
  const [pdfPage, setPdfPage] = useState<number | null>(null);

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [totalCount, setTotalCount] = useState(0);

  // Bulk ledger mapping popover/input
  const [bulkLedger, setBulkLedger] = useState("");
  const [showBulkPanel, setShowBulkPanel] = useState(false);

  // Fetch statement details
  useEffect(() => {
    const fetchStatement = async () => {
      try {
        const res = await fetch(`http://localhost:8000/v1/statements/${statementId}/status`);
        const data = await res.json();
        if (data.success) {
          setStatement(data.data);
        } else {
          setError(data.message || "Failed to fetch statement info.");
        }
      } catch (err) {
        console.error(err);
        setError("Failed to fetch statement details.");
      }
    };
    fetchStatement();
  }, [statementId]);

  // Fetch transactions with pagination, sorting, filtering
  const fetchTransactions = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.set("page", page.toString());
      params.set("page_size", pageSize.toString());
      if (searchTerm) params.set("search", searchTerm);
      if (ledgerFilter) params.set("ledger", ledgerFilter);
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      if (minAmount) params.set("min_amount", minAmount);
      if (maxAmount) params.set("max_amount", maxAmount);

      const res = await fetch(
        `http://localhost:8000/v1/statements/${statementId}/transactions?${params.toString()}`
      );
      const data = await res.json();
      if (data.success) {
        setTransactions(data.data.transactions);
        setTotalCount(data.data.total);
      }
    } catch (err) {
      console.error(err);
      setError("Failed to fetch transactions.");
    } finally {
      setLoading(false);
    }
  }, [statementId, page, pageSize, searchTerm, ledgerFilter, dateFrom, dateTo, minAmount, maxAmount]);

  const getDownloadFilename = (format: string) => {
    const normalized = format === "excel" ? "xls" : format === "tally_xml" ? "xml" : format;
    return `${statement?.filename || statementId}.${normalized}`;
  };

  const handleExport = async (format: "excel" | "csv" | "tally_xml" | "json") => {
    try {
      const res = await fetch(
        `http://localhost:8000/v1/statements/${statementId}/export?format=${format}`
      );
      if (!res.ok) {
        throw new Error("Export failed");
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const filename = getDownloadFilename(format);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      setError("Export failed. Please try again.");
    }
  };

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  useEffect(() => {
    setPage(1);
  }, [searchTerm, ledgerFilter, dateFrom, dateTo, minAmount, maxAmount]);

  // Undo/Redo Helper functions
  const recordHistory = (currentState: ExtractedTransaction[]) => {
    setHistoryPast((prev) => [...prev, currentState]);
    setHistoryFuture([]); // clear redo stack on new action
  };

  const handleUndo = () => {
    if (historyPast.length === 0) return;
    const previous = historyPast[historyPast.length - 1];
    const newPast = historyPast.slice(0, historyPast.length - 1);
    
    setHistoryFuture((prev) => [transactions, ...prev]);
    setTransactions(previous);
    setHistoryPast(newPast);
  };

  const handleRedo = () => {
    if (historyFuture.length === 0) return;
    const next = historyFuture[0];
    const newFuture = historyFuture.slice(1);

    setHistoryPast((prev) => [...prev, transactions]);
    setTransactions(next);
    setHistoryFuture(newFuture);
  };

  // Edit single transaction cell inline
  const handleCellEdit = async (
    txnId: string,
    field: keyof ExtractedTransaction,
    value: string | number | boolean | null
  ) => {
    // Record current state for undo
    recordHistory([...transactions]);

    // Optimistically update locally
    const updated = transactions.map((t) => {
      if (t.id === txnId) {
        return { ...t, [field]: value };
      }
      return t;
    });
    setTransactions(updated);

    // Save to API
    try {
      const payload: Record<string, string | number | boolean | null> = { [field]: value };
      await fetch(
        `http://localhost:8000/v1/statements/${statementId}/transactions/${txnId}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        }
      );
    } catch (err) {
      console.error("Failed to persist edit:", err);
    }
  };

  // Bulk update confirmed ledger
  const handleBulkUpdateLedger = async (ledgerName: string) => {
    if (selectedIds.size === 0 || !ledgerName) return;

    recordHistory([...transactions]);

    const idsArray = Array.from(selectedIds);
    // Optimistic update locally
    setTransactions((prev) =>
      prev.map((t) => {
        if (selectedIds.has(t.id)) {
          return { ...t, confirmed_ledger: ledgerName };
        }
        return t;
      })
    );

    try {
      await fetch(
        `http://localhost:8000/v1/statements/${statementId}/transactions/bulk-update`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            ids: idsArray,
            updates: { confirmed_ledger: ledgerName },
          }),
        }
      );
      setSelectedIds(new Set());
      setBulkLedger("");
      setShowBulkPanel(false);
    } catch (err) {
      console.error("Bulk update failed:", err);
    }
  };

  // Bulk update ignore status
  const handleBulkIgnore = async (ignore: boolean) => {
    if (selectedIds.size === 0) return;

    recordHistory([...transactions]);

    const idsArray = Array.from(selectedIds);
    setTransactions((prev) =>
      prev.map((t) => {
        if (selectedIds.has(t.id)) {
          return { ...t, is_ignored: ignore };
        }
        return t;
      })
    );

    try {
      await fetch(
        `http://localhost:8000/v1/statements/${statementId}/transactions/bulk-update`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            ids: idsArray,
            updates: { is_ignored: ignore },
          }),
        }
      );
      setSelectedIds(new Set());
    } catch (err) {
      console.error("Bulk ignore failed:", err);
    }
  };

  // Filtered transactions for rendering
  const filteredTransactions = useMemo(() => {
    return transactions.filter((t) => {
      // 1. Debit/Credit Filter
      if (typeFilter === "debit" && !t.debit) return false;
      if (typeFilter === "credit" && !t.credit) return false;

      // 2. Confidence Filter (only low confidence < 0.8)
      if (confidenceFilter) {
        const conf = t.confidence ?? 1.0;
        if (conf >= 0.8) return false;
      }

      return true;
    });
  }, [transactions, typeFilter, confidenceFilter]);

  // Export helper
  const handleExport = async (format: "excel" | "csv" | "tally_xml") => {
    try {
      alert(`Exporting statement transactions as ${format.toUpperCase()}...`);
    } catch (err) {
      console.error(err);
    }
  };

  // Toggle row selection
  const handleToggleSelectRow = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleToggleSelectAll = () => {
    if (selectedIds.size === filteredTransactions.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredTransactions.map((t) => t.id)));
    }
  };

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-4 bg-slate-50 dark:bg-slate-950">
        <h1 className="text-2xl font-bold text-rose-600 mb-2">Error</h1>
        <p className="text-slate-600 dark:text-slate-400 mb-4">{error}</p>
        <Button onClick={() => router.push("/dashboard")}>Back to Dashboard</Button>
      </div>
    );
  }

  const pdfFragment = pdfPage ? `#page=${pdfPage}&toolbar=1` : "#toolbar=1";
  const pdfUrl = `http://localhost:8000/v1/statements/${statementId}/file${pdfFragment}`;

  return (
    <div className="min-h-screen flex flex-col bg-slate-900 text-white">
      {/* Premium Header */}
      <header className="h-16 border-b border-slate-800 bg-slate-950/80 backdrop-blur px-6 flex items-center justify-between z-20">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            onClick={() => router.push("/dashboard")}
            className="text-slate-400 hover:text-white"
          >
            ← Dashboard
          </Button>
          <div className="h-4 w-[1px] bg-slate-800"></div>
          <div>
            <h1 className="font-semibold text-lg flex items-center gap-2">
              Reviewing: <span className="text-blue-400">{statement?.filename}</span>
            </h1>
            <p className="text-xs text-slate-400">
              Bank: {statement?.bank} | Status: {statement?.status}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            onClick={() => handleExport("tally_xml")}
            className="bg-orange-600 hover:bg-orange-700 text-white font-medium text-sm shadow-lg shadow-orange-900/20"
          >
            Tally XML
          </Button>
          <Button
            onClick={() => handleExport("excel")}
            className="bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-sm shadow-lg shadow-emerald-900/20"
          >
            Excel
          </Button>
          <Button
            onClick={() => handleExport("csv")}
            className="bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium text-sm"
          >
            CSV
          </Button>
          <Button
            onClick={() => handleExport("json")}
            className="bg-slate-700 hover:bg-slate-600 text-white font-medium text-sm"
          >
            JSON
          </Button>
        </div>
      </header>

      {/* Main split dashboard panels */}
      <div className="flex-1 flex overflow-hidden">
        {/* PDF PREVIEW PANEL (Left 40% width) */}
        <div className="w-[40%] border-r border-slate-850 bg-slate-950 flex flex-col h-full relative">
          {statement?.file_type === "pdf" ? (
            <iframe
              src={pdfUrl}
              className="w-full h-full border-0"
              title="Statement PDF Preview"
            />
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-400">
              <svg
                className="w-16 h-16 text-slate-600 mb-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
              <h3 className="font-semibold text-lg text-slate-300 mb-1">
                No Preview Available
              </h3>
              <p className="text-sm max-w-xs">
                PDF previews are only supported for PDF statements. This statement was uploaded as a {statement?.file_type?.toUpperCase()} file.
              </p>
            </div>
          )}
        </div>

        {/* TRANSACTIONS GRID PANEL (Right 60% width) */}
        <div className="flex-1 flex flex-col h-full bg-slate-900/60 overflow-hidden relative">
          
          {/* Controls / Filter Bar */}
          <div className="p-4 border-b border-slate-800 bg-slate-950/20 flex flex-wrap items-center justify-between gap-4 z-10">
            <div className="grid gap-2 flex-1 min-w-[300px] sm:grid-cols-[1fr_auto] lg:grid-cols-[1.2fr_auto]">
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                <input
                  type="text"
                  placeholder="Search narration or ledger..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="bg-slate-800/80 border border-slate-700/60 rounded px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-all"
                />
                <input
                  type="text"
                  placeholder="Ledger filter"
                  value={ledgerFilter}
                  onChange={(e) => setLedgerFilter(e.target.value)}
                  className="bg-slate-800/80 border border-slate-700/60 rounded px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-all"
                />
                <div className="flex items-center gap-2">
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    className="bg-slate-800/80 border border-slate-700/60 rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
                  />
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    className="bg-slate-800/80 border border-slate-700/60 rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min="0"
                    placeholder="Min amount"
                    value={minAmount}
                    onChange={(e) => setMinAmount(e.target.value)}
                    className="bg-slate-800/80 border border-slate-700/60 rounded px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
                  />
                  <input
                    type="number"
                    min="0"
                    placeholder="Max amount"
                    value={maxAmount}
                    onChange={(e) => setMaxAmount(e.target.value)}
                    className="bg-slate-800/80 border border-slate-700/60 rounded px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value as "all" | "debit" | "credit")}
                  className="bg-slate-800/80 border border-slate-700/60 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500 transition-all"
                >
                  <option value="all">All Trans.</option>
                  <option value="debit">Debits Only</option>
                  <option value="credit">Credits Only</option>
                </select>

                <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={confidenceFilter}
                    onChange={(e) => setConfidenceFilter(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-0"
                  />
                  Low Confidence
                </label>
              </div>
            </div>

            {/* Undo/Redo & Save Status */}
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleUndo}
                disabled={historyPast.length === 0}
                className="h-8 text-xs border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white"
              >
                ↶ Undo
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleRedo}
                disabled={historyFuture.length === 0}
                className="h-8 text-xs border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white"
              >
                ↷ Redo
              </Button>
            </div>
          </div>

          {/* Bulk Action Banner (Shows when checkboxes are selected) */}
          {selectedIds.size > 0 && (
            <div className="bg-blue-600/90 backdrop-blur px-6 py-3 flex items-center justify-between text-white font-medium text-sm animate-slide-down">
              <span>{selectedIds.size} transaction(s) selected</span>
              <div className="flex items-center gap-3">
                {showBulkPanel ? (
                  <div className="flex items-center gap-2 bg-slate-900/40 p-1 rounded border border-white/20">
                    <input
                      type="text"
                      list="bulk-ledgers-list"
                      placeholder="Enter Ledger name"
                      value={bulkLedger}
                      onChange={(e) => setBulkLedger(e.target.value)}
                      className="bg-slate-950 border border-slate-700 rounded px-2.5 py-1 text-xs text-white placeholder-slate-400 focus:outline-none"
                    />
                    <datalist id="bulk-ledgers-list">
                      {DEFAULT_LEDGERS.map((ledger) => (
                        <option key={ledger} value={ledger} />
                      ))}
                    </datalist>
                    <Button
                      size="sm"
                      onClick={() => handleBulkUpdateLedger(bulkLedger)}
                      className="bg-blue-500 hover:bg-blue-600 text-white text-xs px-3 h-7"
                    >
                      Apply
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowBulkPanel(false)}
                      className="text-white hover:bg-white/10 text-xs px-2 h-7"
                    >
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <Button
                    size="sm"
                    onClick={() => setShowBulkPanel(true)}
                    className="bg-slate-900 hover:bg-slate-950 text-white border border-slate-700"
                  >
                    Assign Ledger
                  </Button>
                )}
                
                <Button
                  size="sm"
                  onClick={() => handleBulkIgnore(true)}
                  className="bg-slate-900 hover:bg-slate-950 text-slate-300"
                >
                  Ignore Selected
                </Button>
                
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelectedIds(new Set())}
                  className="text-white hover:bg-white/10"
                >
                  Clear Selection
                </Button>
              </div>
            </div>
          )}

          {/* Transactions Table Body */}
          <div className="flex-1 overflow-auto">
            {loading ? (
              <div className="h-full flex items-center justify-center">
                <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"></div>
              </div>
            ) : filteredTransactions.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 p-8">
                <p className="text-center font-medium text-slate-400">
                  No transactions found matching your filters.
                </p>
              </div>
            ) : (
              <table className="w-full text-left border-collapse select-none">
                <thead className="sticky top-0 bg-slate-950/90 border-b border-slate-800 text-slate-400 text-xs font-semibold uppercase tracking-wider z-10">
                  <tr>
                    <th className="py-3 px-4 w-12 text-center">
                      <input
                        type="checkbox"
                        checked={selectedIds.size === filteredTransactions.length}
                        onChange={handleToggleSelectAll}
                        className="rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-0"
                      />
                    </th>
                    <th className="py-3 px-4 w-28">Date</th>
                    <th className="py-3 px-4">Narration</th>
                    <th className="py-3 px-4 w-28 text-right">Debit</th>
                    <th className="py-3 px-4 w-28 text-right">Credit</th>
                    <th className="py-3 px-4 w-32 text-center">Confidence</th>
                    <th className="py-3 px-4 w-60">Ledger Mapping</th>
                    <th className="py-3 px-4 w-16 text-center">Ignore</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/40 text-sm">
                  {filteredTransactions.map((txn) => {
                    const isLowConfidence = (txn.confidence ?? 1.0) < 0.8 && !txn.confirmed_ledger;
                    const isSelected = selectedIds.has(txn.id);
                    
                    return (
                      <tr
                        key={txn.id}
                        onClick={() => txn.page_number && setPdfPage(txn.page_number)}
                        className={`transition-colors duration-150 ${
                          isSelected ? "bg-blue-600/10 hover:bg-blue-600/15" :
                          txn.is_ignored ? "bg-slate-800/30 text-slate-500 opacity-60 line-through" :
                          isLowConfidence ? "bg-amber-500/5 border-l-2 border-l-amber-500 hover:bg-slate-800/40 cursor-pointer" :
                          "hover:bg-slate-800/30 cursor-pointer"
                        }`}
                      >
                        {/* Checkbox */}
                        <td className="py-3 px-4 text-center">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => handleToggleSelectRow(txn.id)}
                            className="rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-0"
                          />
                        </td>

                        {/* Date */}
                        <td className="py-3 px-4 font-mono text-slate-300">
                          <input
                            type="date"
                            value={txn.date}
                            onChange={(e) => handleCellEdit(txn.id, "date", e.target.value)}
                            className="bg-transparent border-0 text-slate-300 w-full font-mono text-xs focus:ring-1 focus:ring-blue-500 rounded px-1 py-0.5 focus:bg-slate-850"
                          />
                        </td>

                        {/* Narration */}
                        <td className="py-3 px-4 font-normal text-slate-100 max-w-sm truncate title-wrap">
                          <input
                            type="text"
                            value={txn.description}
                            onChange={(e) => handleCellEdit(txn.id, "description", e.target.value)}
                            className="bg-transparent border-0 text-slate-100 w-full text-xs focus:ring-1 focus:ring-blue-500 rounded px-1 py-0.5 focus:bg-slate-850"
                          />
                        </td>

                        {/* Debit */}
                        <td className="py-3 px-4 text-right font-mono font-medium text-rose-400">
                          {txn.debit ? `₹${parseFloat(txn.debit).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : "-"}
                        </td>

                        {/* Credit */}
                        <td className="py-3 px-4 text-right font-mono font-medium text-emerald-400">
                          {txn.credit ? `₹${parseFloat(txn.credit).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : "-"}
                        </td>

                        {/* Confidence indicator */}
                        <td className="py-3 px-4 text-center">
                          {txn.confirmed_ledger ? (
                            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 bg-slate-800 text-slate-300 rounded-full border border-slate-700">
                              Verified
                            </span>
                          ) : txn.confidence !== null ? (
                            <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full border ${
                              isLowConfidence
                                ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                                : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                            }`}>
                              {(txn.confidence * 100).toFixed(0)}% Match
                            </span>
                          ) : (
                            <span className="text-slate-600">-</span>
                          )}
                        </td>

                        {/* Ledger Selector */}
                        <td className="py-3 px-4">
                          <div className="relative">
                            <input
                              type="text"
                              list={`ledgers-list-${txn.id}`}
                              value={txn.confirmed_ledger || txn.suggested_ledger || ""}
                              placeholder="Select general ledger"
                              onChange={(e) => handleCellEdit(txn.id, "confirmed_ledger", e.target.value)}
                              className={`w-full text-xs border rounded px-2.5 py-1 bg-slate-800/80 focus:outline-none focus:border-blue-500 transition-all ${
                                isLowConfidence
                                  ? "border-amber-500/30 text-amber-300"
                                  : "border-slate-700/60 text-emerald-300"
                              }`}
                            />
                            <datalist id={`ledgers-list-${txn.id}`}>
                              {DEFAULT_LEDGERS.map((ledger) => (
                                <option key={ledger} value={ledger} />
                              ))}
                            </datalist>
                          </div>
                        </td>

                        {/* Ignore toggle */}
                        <td className="py-3 px-4 text-center">
                          <input
                            type="checkbox"
                            checked={txn.is_ignored}
                            onChange={(e) => handleCellEdit(txn.id, "is_ignored", e.target.checked)}
                            className="rounded border-slate-700 bg-slate-800 text-rose-500 focus:ring-0"
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* Pagination Footer */}
          <div className="h-14 border-t border-slate-800 bg-slate-950/80 backdrop-blur px-6 flex items-center justify-between z-10 text-slate-400 text-xs">
            <div>
              Showing {Math.min(totalCount, (page - 1) * pageSize + 1)}-{Math.min(totalCount, page * pageSize)} of {totalCount} records
            </div>
            
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <span>Show</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(parseInt(e.target.value));
                    setPage(1);
                  }}
                  className="bg-slate-800 border border-slate-750 rounded px-2 py-0.5 focus:outline-none"
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
                <span>per page</span>
              </div>

              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="h-8 text-slate-300 disabled:opacity-40 hover:bg-slate-800"
                >
                  ◀ Previous
                </Button>
                <div className="px-3 py-1 bg-slate-800 border border-slate-700 rounded font-semibold text-white">
                  {page}
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setPage((p) => (p * pageSize < totalCount ? p + 1 : p))}
                  disabled={page * pageSize >= totalCount}
                  className="h-8 text-slate-300 disabled:opacity-40 hover:bg-slate-800"
                >
                  Next ▶
                </Button>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
