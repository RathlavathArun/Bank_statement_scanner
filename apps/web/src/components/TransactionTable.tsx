"use client";

import { useState, useMemo } from "react";
import { ChevronUp, ChevronDown } from "lucide-react";

interface Transaction {
  id: string;
  txn_date?: string;
  narration?: string;
  debit?: number | string | null;
  credit?: number | string | null;
  balance?: number | string | null;
  payment_mode?: string;
  suggested_ledger?: string;
  confirmed_ledger?: string;
  confidence?: number;
  is_ignored?: boolean;
}

interface TransactionTableProps {
  statementId: string;
  transactions: Transaction[];
  loading: boolean;
  onUpdate: (txId: string, changes: Partial<Transaction>) => void;
  pagination: { total: number; pages: number } | null;
  page: number;
  pageSize: number;
  onPageChange: (p: number) => void;
  onPageSizeChange: (size: number) => void;
}

type FilterType = "ALL" | "DEBIT" | "CREDIT";

export function TransactionTable({
  statementId,
  transactions,
  loading,
  onUpdate,
  pagination,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: TransactionTableProps) {
  const [editingCell, setEditingCell] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [searchText, setSearchText] = useState("");
  const [filterType, setFilterType] = useState<FilterType>("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortBy, setSortBy] = useState<"date" | "narration">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // Filter transactions
  const filtered = useMemo(() => {
    let result = [...transactions];

    // Text search
    if (searchText) {
      result = result.filter((tx) =>
        tx.narration?.toLowerCase().includes(searchText.toLowerCase())
      );
    }

    // Type filter
    if (filterType === "DEBIT") {
      result = result.filter((tx) => tx.debit);
    } else if (filterType === "CREDIT") {
      result = result.filter((tx) => tx.credit);
    }

    // Date range
    if (dateFrom) {
      result = result.filter((tx) => tx.txn_date! >= dateFrom);
    }
    if (dateTo) {
      result = result.filter((tx) => tx.txn_date! <= dateTo);
    }

    // Sort
    result.sort((a, b) => {
      let aVal: any = sortBy === "date" ? a.txn_date : a.narration;
      let bVal: any = sortBy === "date" ? b.txn_date : b.narration;

      if (aVal === bVal) return 0;
      const cmp = aVal < bVal ? -1 : 1;
      return sortDir === "asc" ? cmp : -cmp;
    });

    return result;
  }, [transactions, searchText, filterType, dateFrom, dateTo, sortBy, sortDir]);

  const startEdit = (txId: string, field: string, value: any) => {
    setEditingCell(`${txId}:${field}`);
    setEditValue(value || "");
  };

  const saveEdit = (txId: string, field: string) => {
    if (editValue.trim() || editValue === "") {
      onUpdate(txId, { [field]: editValue } as Partial<Transaction>);
      setEditingCell(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent, txId: string, field: string) => {
    if (e.key === "Enter") {
      saveEdit(txId, field);
    } else if (e.key === "Escape") {
      setEditingCell(null);
    }
  };

  // Calculate totals
  const totalDebit = filtered.reduce((sum, tx) => {
    const amount = typeof tx.debit === "string" ? parseFloat(tx.debit) : tx.debit;
    return sum + (amount || 0);
  }, 0);

  const totalCredit = filtered.reduce((sum, tx) => {
    const amount = typeof tx.credit === "string" ? parseFloat(tx.credit) : tx.credit;
    return sum + (amount || 0);
  }, 0);

  const unledgered = filtered.filter((tx) => !tx.confirmed_ledger).length;

  if (loading) {
    return (
      <div className="space-y-3">
        {[...Array(8)].map((_, i) => (
          <div
            key={i}
            className="h-10 bg-white/5 rounded animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (filtered.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-gray-400">
        No transactions found.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Filters Bar */}
      <div className="space-y-3 p-4 bg-black/20 rounded-lg border border-white/10">
        {/* Search */}
        <input
          type="text"
          placeholder="Search narration..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
        />

        {/* Type Filters */}
        <div className="flex gap-2">
          {(["ALL", "DEBIT", "CREDIT"] as FilterType[]).map((type) => (
            <button
              key={type}
              onClick={() => setFilterType(type)}
              className={`px-3 py-1 rounded-lg text-sm font-medium transition-all ${
                filterType === type
                  ? "bg-blue-600 text-white"
                  : "bg-white/5 text-gray-300 hover:bg-white/10"
              }`}
            >
              {type}
            </button>
          ))}
        </div>

        {/* Date Range */}
        <div className="flex gap-2">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50"
          />
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50"
          />
        </div>

        {/* Stats */}
        <div className="flex justify-between text-sm text-gray-300">
          <span>Debit: ₹{totalDebit.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
          <span>Credit: ₹{totalCredit.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
          <span className="text-yellow-400">Unledgered: {unledgered}</span>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-black/40 border-b border-white/10">
              <th className="px-4 py-2 text-left text-gray-300 font-medium">
                <button
                  onClick={() => sortBy === "date" && setSortDir(sortDir === "asc" ? "desc" : "asc")}
                  className="flex items-center gap-1 hover:text-white"
                >
                  Date
                  {sortBy === "date" && (
                    sortDir === "asc" ? <ChevronUp size={14} /> : <ChevronDown size={14} />
                  )}
                </button>
              </th>
              <th className="px-4 py-2 text-left text-gray-300 font-medium">Narration</th>
              <th className="px-4 py-2 text-right text-gray-300 font-medium">Amount</th>
              <th className="px-4 py-2 text-right text-gray-300 font-medium">Balance</th>
              <th className="px-4 py-2 text-left text-gray-300 font-medium">Mode</th>
              <th className="px-4 py-2 text-left text-gray-300 font-medium">Ledger</th>
              <th className="px-4 py-2 text-center text-gray-300 font-medium">Conf.</th>
              <th className="px-4 py-2 text-center text-gray-300 font-medium">✓</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((tx) => {
              const amount = tx.debit || tx.credit;
              const isDebit = !!tx.debit;
              const rowClass = !tx.confirmed_ledger
                ? "bg-red-500/5"
                : (tx.confidence || 1) < 0.5
                ? "bg-yellow-500/5"
                : "";

              return (
                <tr
                  key={tx.id}
                  data-testid="transaction-row"
                  className={`border-b border-white/10 hover:bg-white/5 transition-colors ${rowClass}`}
                >
                  <td className="px-4 py-2 text-gray-300">{tx.txn_date}</td>
                  <td
                    className="px-4 py-2 text-gray-300 cursor-pointer hover:text-white"
                    onClick={() => startEdit(tx.id, "narration", tx.narration)}
                  >
                    {editingCell === `${tx.id}:narration` ? (
                      <input
                        autoFocus
                        type="text"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onBlur={() => saveEdit(tx.id, "narration")}
                        onKeyDown={(e) => handleKeyDown(e, tx.id, "narration")}
                        className="w-full px-2 py-1 bg-white/10 border border-white/20 rounded text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                      />
                    ) : (
                      <span title={tx.narration}>{tx.narration?.substring(0, 30)}</span>
                    )}
                  </td>
                  <td
                    className={`px-4 py-2 text-right font-medium ${
                      isDebit ? "text-red-400" : "text-green-400"
                    }`}
                  >
                    {isDebit ? "−" : "+"}{" "}
                    {typeof amount === "string"
                      ? amount
                      : amount?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-300">
                    {typeof tx.balance === "string"
                      ? tx.balance
                      : tx.balance?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-2 text-gray-400 text-xs">{tx.payment_mode || "—"}</td>
                  <td
                    className="px-4 py-2 text-gray-300 cursor-pointer hover:text-white"
                    onClick={() => startEdit(tx.id, "confirmed_ledger", tx.confirmed_ledger)}
                  >
                    {editingCell === `${tx.id}:confirmed_ledger` ? (
                      <input
                        autoFocus
                        type="text"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onBlur={() => saveEdit(tx.id, "confirmed_ledger")}
                        onKeyDown={(e) => handleKeyDown(e, tx.id, "confirmed_ledger")}
                        className="w-full px-2 py-1 bg-white/10 border border-white/20 rounded text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                      />
                    ) : (
                      <span className="text-sm">{tx.confirmed_ledger || "—"}</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-center text-gray-400 text-xs">
                    {tx.confidence ? (tx.confidence * 100).toFixed(0) : "—"}%
                  </td>
                  <td className="px-4 py-2 text-center">
                    <input
                      type="checkbox"
                      checked={tx.is_ignored || false}
                      onChange={(e) => onUpdate(tx.id, { is_ignored: e.target.checked })}
                      className="rounded"
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pagination && (
        <div className="flex items-center justify-between p-4 bg-black/20 rounded-lg border border-white/10">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-400">Rows per page:</span>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(parseInt(e.target.value))}
              className="px-2 py-1 bg-white/10 border border-white/10 rounded text-white text-sm focus:outline-none"
            >
              {[25, 50, 100].map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </div>

          <span className="text-sm text-gray-400">
            Page {page} of {pagination.pages}
          </span>

          <div className="flex gap-2">
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page === 1}
              className="px-3 py-1 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed text-white text-sm transition-all"
            >
              ← Prev
            </button>
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page === pagination.pages}
              className="px-3 py-1 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed text-white text-sm transition-all"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
