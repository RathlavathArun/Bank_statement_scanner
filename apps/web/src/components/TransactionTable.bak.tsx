"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { type BboxCoords } from "@/components/PDFViewer";

interface Transaction {
  id: string;
  txn_date?: string;
  narration?: string;
  narration_clean?: string;
  debit?: number | string | null;
  credit?: number | string | null;
  balance?: number | string | null;
  payment_mode?: string;
  suggested_ledger?: string;
  confirmed_ledger?: string;
  confidence?: number | string | null;
  ocr_confidence?: number | string | null;
  page_number?: number | null;
  is_ignored?: boolean;
  bbox?: BboxCoords | null;
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
  onBulkUpdate?: (txIds: string[], changes: Partial<Transaction>) => void;
  /** Called when the user clicks a transaction row to jump the PDF to its source page. */
  onRowClick?: (txId: string, pageNumber: number | null, bbox: BboxCoords | null) => void;
}

type FilterType = "ALL" | "DEBIT" | "CREDIT";
type EditableField = "narration" | "confirmed_ledger";

const columnHelper = createColumnHelper<Transaction>();

function amountValue(value: number | string | null | undefined) {
  if (typeof value === "number") return value;
  if (typeof value === "string") return Number(value.replace(/,/g, ""));
  return 0;
}

/** Converts yyyy-mm-dd → dd-mm-yyyy for display */
function formatDate(raw: string | undefined): string {
  if (!raw) return "";
  const parts = raw.split("-");
  if (parts.length === 3) return `${parts[2]}-${parts[1]}-${parts[0]}`;
  return raw;
}

const API = "/api";

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
  onBulkUpdate,
  onRowClick,
}: TransactionTableProps) {
  const [editingCell, setEditingCell] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [searchText, setSearchText] = useState("");
  const [filterType, setFilterType] = useState<FilterType>("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortBy, setSortBy] = useState<"date" | "narration">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [rowSelection, setRowSelection] = useState({});
  const [bulkLedger, setBulkLedger] = useState("");
  const [ledgerSuggestions, setLedgerSuggestions] = useState<{ ledger_name: string; score: number }[]>([]);
  const [activeRowId, setActiveRowId] = useState<string | null>(null);

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
    if (field === "confirmed_ledger") {
      // Fetch ledger suggestions when user begins editing ledger cell
      setLedgerSuggestions([]);
      fetch(`${API}/v1/statements/${statementId}/transactions/${txId}/ledger-suggestions`)
        .then((res) => res.ok ? res.json() : null)
        .then((data) => {
          if (data?.data?.suggestions) {
            setLedgerSuggestions(data.data.suggestions);
          }
        })
        .catch(() => {/* no-op */});
    }
  };

  const saveEdit = (txId: string, field: EditableField) => {
    onUpdate(txId, { [field]: editValue } as Partial<Transaction>);
    setEditingCell(null);
    setLedgerSuggestions([]);
  };

  const handleKeyDown = (event: React.KeyboardEvent, txId: string, field: EditableField) => {
    if (event.key === "Enter") {
      saveEdit(txId, field);
    } else if (event.key === "Escape") {
      setEditingCell(null);
      setLedgerSuggestions([]);
    }
  };

  const totalDebit = filtered.reduce((sum, tx) => sum + amountValue(tx.debit), 0);
  const totalCredit = filtered.reduce((sum, tx) => sum + amountValue(tx.credit), 0);
  const unledgered = filtered.filter((tx) => !tx.confirmed_ledger).length;

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: "select",
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllPageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            className="rounded"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            className="rounded"
          />
        ),
      }),
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
        cell: (info) => <span className="text-gray-300">{formatDate(info.getValue())}</span>,
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
                <div>
                  <span title={getValue()}>{getValue()?.substring(0, 30)}</span>
                  {tx.narration_clean && tx.narration_clean !== getValue() && (
                    <p className="text-xs text-indigo-400 truncate" title={tx.narration_clean}>
                      {tx.narration_clean.substring(0, 28)}
                    </p>
                  )}
                </div>
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
          const isEditing = editingCell === `${tx.id}:confirmed_ledger`;
          return (
            <div className="relative cursor-pointer text-gray-300 hover:text-white">
              {isEditing ? (
                <div>
                  <input
                    autoFocus
                    type="text"
                    value={editValue}
                    onChange={(event) => setEditValue(event.target.value)}
                    onBlur={() => saveEdit(tx.id, "confirmed_ledger")}
                    onKeyDown={(event) => handleKeyDown(event, tx.id, "confirmed_ledger")}
                    className="w-full rounded border border-white/20 bg-white/10 px-2 py-1 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                  />
                  {ledgerSuggestions.length > 0 && (
                    <ul className="absolute z-50 mt-1 w-56 rounded-lg border border-white/10 bg-slate-900 shadow-xl text-xs">
                      {ledgerSuggestions.slice(0, 5).map((s) => (
                        <li
                          key={s.ledger_name}
                          className="flex items-center justify-between px-3 py-1.5 hover:bg-white/10 cursor-pointer"
                          onMouseDown={(e) => {
                            e.preventDefault();
                            setEditValue(s.ledger_name);
                            onUpdate(tx.id, { confirmed_ledger: s.ledger_name });
                            setEditingCell(null);
                            setLedgerSuggestions([]);
                          }}
                        >
                          <span className="text-white">{s.ledger_name}</span>
                          <span className="text-gray-500">{Math.round(s.score * 100)}%</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {tx.suggested_ledger && !getValue() && (
                    <p className="mt-1 text-xs text-indigo-400">
                      AI: <button
                        className="hover:text-indigo-300 underline"
                        onMouseDown={(e) => {
                          e.preventDefault();
                          setEditValue(tx.suggested_ledger!);
                          onUpdate(tx.id, { confirmed_ledger: tx.suggested_ledger });
                          setEditingCell(null);
                        }}
                      >{tx.suggested_ledger}</button>
                    </p>
                  )}
                </div>
              ) : (
                <div onClick={() => startEdit(tx.id, "confirmed_ledger", getValue())}>
                  <span>{getValue() || <span className="text-gray-500 italic text-xs">click to assign</span>}</span>
                  {!getValue() && tx.suggested_ledger && (
                    <p className="text-xs text-indigo-400 truncate">{tx.suggested_ledger}</p>
                  )}
                </div>
              )}
            </div>
          );
        },
      }),
      columnHelper.accessor("confidence", {
        header: () => <span className="block text-center">Conf.</span>,
        cell: (info) => {
          const val = Number(info.getValue() || 0);
          if (!val) return <span className="block text-center text-xs text-gray-400">-</span>;
          
          let badgeClass = "bg-red-500/20 text-red-400 border-red-500/30";
          if (val >= 0.8) badgeClass = "bg-green-500/20 text-green-400 border-green-500/30";
          else if (val >= 0.5) badgeClass = "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
          
          return (
            <span className={`inline-block text-center text-xs px-2 py-0.5 rounded border ${badgeClass}`}>
              {Math.round(val * 100)}%
            </span>
          );
        },
      }),
      columnHelper.accessor("ocr_confidence", {
        header: () => <span className="block text-center">OCR</span>,
        cell: (info) => {
          const val = Number(info.getValue() || 0);
          if (!val) return <span className="block text-center text-xs text-gray-500">—</span>;

          let badgeClass = "bg-red-500/20 text-red-300 border-red-500/30";
          let icon = "⚠️";
          let label = "Low";
          if (val >= 0.85) {
            badgeClass = "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
            icon = "✓";
            label = "High";
          } else if (val >= 0.7) {
            badgeClass = "bg-amber-500/20 text-amber-300 border-amber-500/30";
            icon = "~";
            label = "Med";
          }

          const tx = info.row.original;

          return (
            <span
              className={`inline-flex items-center gap-1 text-center text-xs px-2 py-0.5 rounded border cursor-help ${badgeClass}`}
              title={`OCR confidence: ${Math.round(val * 100)}%${tx.page_number ? ` (page ${tx.page_number})` : ""}\n${val < 0.7 ? "⚠ Red-flagged: manual review recommended" : val < 0.85 ? "⚡ Medium confidence: verify key fields" : "✓ High confidence"}`}
            >
              <span>{icon}</span>
              <span>{Math.round(val * 100)}%</span>
            </span>
          );
        },
      }),
      columnHelper.accessor("is_ignored", {
        header: () => <span className="block text-center text-xs text-gray-400" title="Ignore this transaction (e.g. bank charges, internal transfers)">Ignore</span>,
        cell: ({ row, getValue }) => (
          <span className="block text-center">
            <input
              type="checkbox"
              title={getValue() ? "Unignore transaction" : "Mark transaction as ignored"}
              checked={getValue() || false}
              onChange={(event) => onUpdate(row.original.id, { is_ignored: event.target.checked })}
              className="rounded cursor-pointer accent-gray-500"
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
    state: { rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    getRowId: (row) => row.id,
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

      {Object.keys(rowSelection).length > 0 && onBulkUpdate && (
        <div className="flex items-center gap-3 rounded-lg border border-blue-500/30 bg-blue-500/10 p-3">
          <span className="text-sm font-medium text-blue-200">
            {Object.keys(rowSelection).length} selected
          </span>
          <input
            type="text"
            placeholder="New Ledger Name"
            value={bulkLedger}
            onChange={(e) => setBulkLedger(e.target.value)}
            className="rounded border border-white/20 bg-white/10 px-2 py-1 text-sm text-white focus:outline-none"
          />
          <button
            onClick={() => {
              const selectedIds = Object.keys(rowSelection);
              onBulkUpdate(selectedIds, { confirmed_ledger: bulkLedger });
              setRowSelection({});
              setBulkLedger("");
            }}
            disabled={!bulkLedger}
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            Apply to All
          </button>
        </div>
      )}

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
                const conf = Number(tx.confidence || 1);
                const ocrConf = Number(tx.ocr_confidence || 0);

                // Determine row class based on confidence and OCR confidence
                let rowClass = "";
                let borderLeft = "";

                // OCR confidence takes priority for flagging
                if (tx.is_ignored) {
                  rowClass = "opacity-40 grayscale bg-transparent";
                  borderLeft = "border-l-4 border-l-gray-600/50";
                } else if (ocrConf > 0 && ocrConf < 0.7) {
                  rowClass = "bg-red-500/10";
                  borderLeft = "border-l-4 border-l-red-500";
                } else if (ocrConf > 0 && ocrConf < 0.85) {
                  rowClass = "bg-amber-500/5";
                  borderLeft = "border-l-4 border-l-amber-500";
                } else if (!tx.confirmed_ledger) {
                  rowClass = "bg-red-500/5";
                } else if (conf < 0.5) {
                  rowClass = "bg-red-500/10";
                } else if (conf < 0.8) {
                  rowClass = "bg-yellow-500/10";
                }

                return (
                  <tr
                    key={row.id}
                    data-testid="transaction-row"
                    onClick={(e) => {
                      // Don't fire if user clicked on an input/button/select (editing)
                      const target = e.target as HTMLElement;
                      if (target.closest("input, button, select, a")) return;
                      if (onRowClick) {
                        setActiveRowId(tx.id);
                        onRowClick(tx.id, tx.page_number ?? null, tx.bbox ?? null);
                      }
                    }}
                    className={`border-b border-white/10 transition-colors hover:bg-white/5 ${rowClass} ${borderLeft} ${
                      activeRowId === tx.id ? "ring-1 ring-inset ring-amber-400/60 bg-amber-500/10" : ""
                    } ${onRowClick && tx.page_number ? "cursor-pointer" : ""}`}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className={`px-4 py-2 ${tx.is_ignored && cell.column.id !== "is_ignored" ? "line-through text-gray-500" : ""}`}>
                        {cell.column.id === "txn_date" && tx.page_number ? (
                          <div className="flex flex-col gap-0.5">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            <span
                              className="inline-flex w-fit items-center gap-0.5 rounded bg-indigo-500/20 px-1.5 py-0.5 text-[10px] text-indigo-300"
                              title={`Source: PDF page ${tx.page_number}`}
                            >
                              p.{tx.page_number}
                            </span>
                          </div>
                        ) : (
                          flexRender(cell.column.columnDef.cell, cell.getContext())
                        )}
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
