"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";

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
  confidence?: number | string | null;
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
type EditableField = "narration" | "confirmed_ledger";

const columnHelper = createColumnHelper<Transaction>();

function amountValue(value: number | string | null | undefined) {
  if (typeof value === "number") return value;
  if (typeof value === "string") return Number(value.replace(/,/g, ""));
  return 0;
}

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
  void statementId;
  const [editingCell, setEditingCell] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [searchText, setSearchText] = useState("");
  const [filterType, setFilterType] = useState<FilterType>("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortBy, setSortBy] = useState<"date" | "narration">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const filtered = useMemo(() => {
    let result = [...transactions];

    if (searchText) {
      result = result.filter((tx) =>
        tx.narration?.toLowerCase().includes(searchText.toLowerCase())
      );
    }

    if (filterType === "DEBIT") {
      result = result.filter((tx) => tx.debit);
    } else if (filterType === "CREDIT") {
      result = result.filter((tx) => tx.credit);
    }

    if (dateFrom) {
      result = result.filter((tx) => (tx.txn_date ?? "") >= dateFrom);
    }
    if (dateTo) {
      result = result.filter((tx) => (tx.txn_date ?? "") <= dateTo);
    }

    result.sort((a, b) => {
      const aVal = sortBy === "date" ? a.txn_date ?? "" : a.narration ?? "";
      const bVal = sortBy === "date" ? b.txn_date ?? "" : b.narration ?? "";
      if (aVal === bVal) return 0;
      const cmp = aVal < bVal ? -1 : 1;
      return sortDir === "asc" ? cmp : -cmp;
    });

    return result;
  }, [dateFrom, dateTo, filterType, searchText, sortBy, sortDir, transactions]);

  const startEdit = (txId: string, field: EditableField, value: string | undefined) => {
    setEditingCell(`${txId}:${field}`);
    setEditValue(value || "");
  };

  const saveEdit = (txId: string, field: EditableField) => {
    onUpdate(txId, { [field]: editValue } as Partial<Transaction>);
    setEditingCell(null);
  };

  const handleKeyDown = (event: React.KeyboardEvent, txId: string, field: EditableField) => {
    if (event.key === "Enter") {
      saveEdit(txId, field);
    } else if (event.key === "Escape") {
      setEditingCell(null);
    }
  };

  const totalDebit = filtered.reduce((sum, tx) => sum + amountValue(tx.debit), 0);
  const totalCredit = filtered.reduce((sum, tx) => sum + amountValue(tx.credit), 0);
  const unledgered = filtered.filter((tx) => !tx.confirmed_ledger).length;

  const columns = useMemo(
    () => [
      columnHelper.accessor("txn_date", {
        header: () => (
          <button
            onClick={() => {
              setSortBy("date");
              setSortDir(sortDir === "asc" ? "desc" : "asc");
            }}
            className="flex items-center gap-1 hover:text-white"
          >
            Date
            {sortBy === "date" && (
              sortDir === "asc" ? <ChevronUp size={14} /> : <ChevronDown size={14} />
            )}
          </button>
        ),
        cell: (info) => <span className="text-gray-300">{info.getValue()}</span>,
      }),
      columnHelper.accessor("narration", {
        header: "Narration",
        cell: ({ row, getValue }) => {
          const tx = row.original;
          return (
            <div
              className="cursor-pointer text-gray-300 hover:text-white"
              onClick={() => startEdit(tx.id, "narration", getValue())}
            >
              {editingCell === `${tx.id}:narration` ? (
                <input
                  autoFocus
                  type="text"
                  value={editValue}
                  onChange={(event) => setEditValue(event.target.value)}
                  onBlur={() => saveEdit(tx.id, "narration")}
                  onKeyDown={(event) => handleKeyDown(event, tx.id, "narration")}
                  className="w-full rounded border border-white/20 bg-white/10 px-2 py-1 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                />
              ) : (
                <span title={getValue()}>{getValue()?.substring(0, 30)}</span>
              )}
            </div>
          );
        },
      }),
      columnHelper.display({
        id: "amount",
        header: () => <span className="block text-right">Amount</span>,
        cell: ({ row }) => {
          const tx = row.original;
          const amount = tx.debit || tx.credit;
          const isDebit = !!tx.debit;
          return (
            <span className={`block text-right font-medium ${isDebit ? "text-red-400" : "text-green-400"}`}>
              {isDebit ? "-" : "+"}₹
              {amountValue(amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </span>
          );
        },
      }),
      columnHelper.accessor("balance", {
        header: () => <span className="block text-right">Balance</span>,
        cell: (info) => (
          <span className="block text-right text-gray-300">
            ₹{amountValue(info.getValue()).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
          </span>
        ),
      }),
      columnHelper.accessor("payment_mode", {
        header: "Mode",
        cell: (info) => <span className="text-xs text-gray-400">{info.getValue() || "-"}</span>,
      }),
      columnHelper.accessor("confirmed_ledger", {
        header: "Ledger",
        cell: ({ row, getValue }) => {
          const tx = row.original;
          return (
            <div
              className="cursor-pointer text-gray-300 hover:text-white"
              onClick={() => startEdit(tx.id, "confirmed_ledger", getValue())}
            >
              {editingCell === `${tx.id}:confirmed_ledger` ? (
                <input
                  autoFocus
                  type="text"
                  value={editValue}
                  onChange={(event) => setEditValue(event.target.value)}
                  onBlur={() => saveEdit(tx.id, "confirmed_ledger")}
                  onKeyDown={(event) => handleKeyDown(event, tx.id, "confirmed_ledger")}
                  className="w-full rounded border border-white/20 bg-white/10 px-2 py-1 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                />
              ) : (
                <span>{getValue() || "-"}</span>
              )}
            </div>
          );
        },
      }),
      columnHelper.accessor("confidence", {
        header: () => <span className="block text-center">Conf.</span>,
        cell: (info) => (
          <span className="block text-center text-xs text-gray-400">
            {info.getValue() ? `${Math.round(Number(info.getValue()) * 100)}%` : "-"}
          </span>
        ),
      }),
      columnHelper.accessor("is_ignored", {
        header: () => <span className="block text-center">✓</span>,
        cell: ({ row, getValue }) => (
          <span className="block text-center">
            <input
              type="checkbox"
              checked={getValue() || false}
              onChange={(event) => onUpdate(row.original.id, { is_ignored: event.target.checked })}
              className="rounded"
            />
          </span>
        ),
      }),
    ],
    [editValue, editingCell, onUpdate, sortBy, sortDir]
  );

  const table = useReactTable({
    data: filtered,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="h-10 animate-pulse rounded bg-white/5" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-lg border border-white/10 bg-black/20 p-4">
        <input
          type="text"
          placeholder="Search narration..."
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-white placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
        />

        <div className="flex gap-2">
          {(["ALL", "DEBIT", "CREDIT"] as FilterType[]).map((type) => (
            <button
              key={type}
              onClick={() => setFilterType(type)}
              className={`rounded-lg px-3 py-1 text-sm font-medium transition-all ${
                filterType === type
                  ? "bg-blue-600 text-white"
                  : "bg-white/5 text-gray-300 hover:bg-white/10"
              }`}
            >
              {type}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <input
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
            className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
          />
          <input
            type="date"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
            className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
          />
        </div>

        <div className="flex justify-between text-sm text-gray-300">
          <span>Debit: ₹{totalDebit.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
          <span>Credit: ₹{totalCredit.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
          <span className="text-yellow-400">Unledgered: {unledgered}</span>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-white/10 bg-black/40">
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="px-4 py-2 text-left font-medium text-gray-300">
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="h-32 text-center text-gray-400">
                  No transactions found.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => {
                const tx = row.original;
                const rowClass = !tx.confirmed_ledger
                  ? "bg-red-500/5"
                  : Number(tx.confidence || 1) < 0.5
                    ? "bg-yellow-500/5"
                    : "";

                return (
                  <tr
                    key={row.id}
                    data-testid="transaction-row"
                    className={`border-b border-white/10 transition-colors hover:bg-white/5 ${rowClass}`}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-4 py-2">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {pagination && (
        <div className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 p-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-400">Rows per page:</span>
            <select
              value={pageSize}
              onChange={(event) => onPageSizeChange(parseInt(event.target.value))}
              className="rounded border border-white/10 bg-white/10 px-2 py-1 text-sm text-white focus:outline-none"
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
              className="rounded-lg bg-white/10 px-3 py-1 text-sm text-white transition-all hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-30"
            >
              Prev
            </button>
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page === pagination.pages}
              className="rounded-lg bg-white/10 px-3 py-1 text-sm text-white transition-all hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-30"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
