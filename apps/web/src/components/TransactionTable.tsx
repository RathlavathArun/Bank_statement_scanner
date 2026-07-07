"use client";

import { useMemo, useState, useCallback, useRef } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { AgGridReact } from "ag-grid-react";
import { ColDef, RowClassParams, RowClickedEvent, SelectionChangedEvent } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
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
  onRowClick?: (txId: string, pageNumber: number | null, bbox: BboxCoords | null) => void;
}

type FilterType = "ALL" | "DEBIT" | "CREDIT";
type EditableField = "narration" | "confirmed_ledger";

function amountValue(value: number | string | null | undefined) {
  if (typeof value === "number") return value;
  if (typeof value === "string") return Number(value.replace(/,/g, ""));
  return 0;
}

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
  const [rowSelection, setRowSelection] = useState<string[]>([]);
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

  const totalDebit = filtered.filter((tx) => !tx.is_ignored).reduce((sum, tx) => sum + amountValue(tx.debit), 0);
  const totalCredit = filtered.filter((tx) => !tx.is_ignored).reduce((sum, tx) => sum + amountValue(tx.credit), 0);
  const unledgered = filtered.filter((tx) => !tx.confirmed_ledger).length;

  const columns: ColDef<Transaction>[] = useMemo(
    () => [
      {
        headerCheckboxSelection: true,
        checkboxSelection: true,
        width: 50,
        sortable: false,
        suppressHeaderMenuButton: true,
        pinned: 'left'
      },
      {
        field: "txn_date",
        headerName: "Date",
        width: 120,
        sortable: false,
        cellRenderer: (params: any) => {
          const tx = params.data;
          if (!tx) return null;
          return (
            <div className={`flex flex-col justify-center h-full gap-0.5 ${tx.is_ignored ? "line-through text-gray-500" : "text-gray-300"}`}>
              {formatDate(tx.txn_date)}
              {tx.page_number && (
                <span
                  className="inline-flex w-fit items-center gap-0.5 rounded bg-indigo-500/20 px-1.5 py-0.5 text-[10px] text-indigo-300 no-underline"
                  title={`Source: PDF page ${tx.page_number}`}
                >
                  p.{tx.page_number}
                </span>
              )}
            </div>
          );
        },
        headerComponent: () => (
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
        )
      },
      {
        field: "narration",
        headerName: "Narration",
        flex: 1,
        minWidth: 200,
        cellRenderer: (params: any) => {
          const tx = params.data;
          if (!tx) return null;
          const isIgnoredClass = tx.is_ignored ? "line-through text-gray-500" : "text-gray-300 hover:text-white";
          return (
            <div
              className={`flex flex-col justify-center h-full cursor-pointer ${isIgnoredClass}`}
              onClick={(e) => {
                e.stopPropagation();
                startEdit(tx.id, "narration", tx.narration);
              }}
            >
              {editingCell === `${tx.id}:narration` ? (
                <input
                  autoFocus
                  type="text"
                  value={editValue}
                  onChange={(event) => setEditValue(event.target.value)}
                  onBlur={() => saveEdit(tx.id, "narration")}
                  onKeyDown={(event) => handleKeyDown(event, tx.id, "narration")}
                  onClick={(e) => e.stopPropagation()}
                  className="w-full rounded border border-white/20 bg-black/50 px-2 py-1 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                />
              ) : (
                <div className="flex flex-col justify-center leading-tight">
                  <span title={tx.narration}>{tx.narration?.substring(0, 30)}</span>
                  {tx.narration_clean && tx.narration_clean !== tx.narration && (
                    <p className={`text-[10px] truncate ${tx.is_ignored ? "text-gray-500" : "text-indigo-400"}`} title={tx.narration_clean}>
                      {tx.narration_clean.substring(0, 28)}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        },
      },
      {
        headerName: "Amount",
        width: 120,
        type: "rightAligned",
        cellRenderer: (params: any) => {
          const tx = params.data;
          if (!tx) return null;
          const amount = tx.debit || tx.credit;
          const isDebit = !!tx.debit;
          const colorClass = isDebit ? "text-red-400" : "text-green-400";
          return (
            <span className={`block font-medium w-full text-right ${tx.is_ignored ? "line-through text-gray-500" : colorClass}`}>
              {isDebit ? "-" : "+"}₹
              {amountValue(amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </span>
          );
        },
      },
      {
        field: "balance",
        headerName: "Balance",
        width: 120,
        type: "rightAligned",
        cellRenderer: (params: any) => {
          const tx = params.data;
          if (!tx) return null;
          return (
            <span className={`block w-full text-right ${tx.is_ignored ? "line-through text-gray-500" : "text-gray-300"}`}>
              ₹{amountValue(tx.balance).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </span>
          );
        },
      },
      {
        field: "payment_mode",
        headerName: "Mode",
        width: 100,
        cellRenderer: (params: any) => {
          const tx = params.data;
          if (!tx) return null;
          return <span className={`text-xs ${tx.is_ignored ? "line-through text-gray-600" : "text-gray-400"}`}>{tx.payment_mode || "-"}</span>;
        },
      },
      {
        field: "confirmed_ledger",
        headerName: "Ledger",
        width: 180,
        cellRenderer: (params: any) => {
          const tx = params.data;
          if (!tx) return null;
          const isEditing = editingCell === `${tx.id}:confirmed_ledger`;
          return (
            <div className={`relative flex flex-col justify-center h-full cursor-pointer ${tx.is_ignored ? "line-through text-gray-500" : "text-gray-300 hover:text-white"}`}>
              {isEditing ? (
                <div onClick={(e) => e.stopPropagation()}>
                  <input
                    autoFocus
                    type="text"
                    value={editValue}
                    onChange={(event) => setEditValue(event.target.value)}
                    onBlur={(e) => {
                       if (e.relatedTarget && (e.relatedTarget as HTMLElement).closest('.ledger-suggestion-dropdown')) return;
                       saveEdit(tx.id, "confirmed_ledger");
                    }}
                    onKeyDown={(event) => handleKeyDown(event, tx.id, "confirmed_ledger")}
                    className="w-full rounded border border-white/20 bg-black/50 px-2 py-1 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                  />
                  {ledgerSuggestions.length > 0 && (
                    <ul className="ledger-suggestion-dropdown absolute z-50 mt-1 w-56 rounded-lg border border-white/10 bg-slate-900 shadow-xl text-xs">
                      {ledgerSuggestions.slice(0, 5).map((s) => (
                        <li
                          key={s.ledger_name}
                          tabIndex={0}
                          className="flex items-center justify-between px-3 py-1.5 hover:bg-white/10 cursor-pointer"
                          onMouseDown={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
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
                  {tx.suggested_ledger && !tx.confirmed_ledger && (
                    <p className="mt-1 text-[10px] text-indigo-400 leading-none">
                      AI: <button
                        className="hover:text-indigo-300 underline"
                        onMouseDown={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setEditValue(tx.suggested_ledger!);
                          onUpdate(tx.id, { confirmed_ledger: tx.suggested_ledger });
                          setEditingCell(null);
                        }}
                      >{tx.suggested_ledger}</button>
                    </p>
                  )}
                </div>
              ) : (
                <div onClick={(e) => { e.stopPropagation(); startEdit(tx.id, "confirmed_ledger", tx.confirmed_ledger); }}>
                  <span className="leading-tight block">{tx.confirmed_ledger || <span className="text-gray-500 italic text-xs">click to assign</span>}</span>
                  {!tx.confirmed_ledger && tx.suggested_ledger && (
                    <p className={`text-[10px] truncate leading-none mt-0.5 ${tx.is_ignored ? "text-gray-500" : "text-indigo-400"}`}>{tx.suggested_ledger}</p>
                  )}
                </div>
              )}
            </div>
          );
        },
      },
      {
        field: "confidence",
        headerName: "Conf.",
        width: 80,
        cellRenderer: (params: any) => {
          const tx = params.data;
          if (!tx) return null;
          const val = Number(tx.confidence || 0);
          if (!val) return <span className="block text-center text-xs text-gray-400">-</span>;
          
          let badgeClass = "bg-red-500/20 text-red-400 border-red-500/30";
          if (val >= 0.8) badgeClass = "bg-green-500/20 text-green-400 border-green-500/30";
          else if (val >= 0.5) badgeClass = "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
          
          if (tx.is_ignored) badgeClass += " opacity-50 grayscale";
          
          return (
            <div className="flex items-center justify-center h-full">
              <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded border leading-none ${badgeClass}`}>
                {Math.round(val * 100)}%
              </span>
            </div>
          );
        },
      },
      {
        field: "ocr_confidence",
        headerName: "OCR",
        width: 80,
        cellRenderer: (params: any) => {
          const tx = params.data;
          if (!tx) return null;
          const val = Number(tx.ocr_confidence || 0);
          if (!val) return <span className="block text-center text-xs text-gray-500">—</span>;

          let badgeClass = "bg-red-500/20 text-red-300 border-red-500/30";
          let icon = "⚠️";
          if (val >= 0.85) {
            badgeClass = "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
            icon = "✓";
          } else if (val >= 0.7) {
            badgeClass = "bg-amber-500/20 text-amber-300 border-amber-500/30";
            icon = "~";
          }
          
          if (tx.is_ignored) badgeClass += " opacity-50 grayscale";

          return (
            <div className="flex items-center justify-center h-full">
              <span
                className={`inline-flex items-center justify-center gap-1 text-[10px] px-1.5 py-0.5 rounded border cursor-help leading-none ${badgeClass}`}
                title={`OCR confidence: ${Math.round(val * 100)}%${tx.page_number ? ` (page ${tx.page_number})` : ""}\n${val < 0.7 ? "⚠ Red-flagged: manual review recommended" : val < 0.85 ? "⚡ Medium confidence: verify key fields" : "✓ High confidence"}`}
              >
                <span>{icon}</span>
                <span>{Math.round(val * 100)}%</span>
              </span>
            </div>
          );
        },
      },
      {
        field: "is_ignored",
        headerName: "Ignore",
        width: 80,
        headerComponent: () => (
          <span className="block text-center text-xs text-gray-400 w-full" title="Ignore this transaction (e.g. bank charges, internal transfers)">Ignore</span>
        ),
        cellRenderer: (params: any) => {
          const tx = params.data;
          if (!tx) return null;
          return (
            <div className="flex items-center justify-center h-full">
              <input
                type="checkbox"
                title={tx.is_ignored ? "Unignore transaction" : "Mark transaction as ignored"}
                checked={tx.is_ignored || false}
                onChange={(event) => {
                  onUpdate(tx.id, { is_ignored: event.target.checked });
                }}
                onClick={(e) => e.stopPropagation()}
                className="rounded cursor-pointer accent-gray-500"
              />
            </div>
          );
        },
      },
    ],
    [editValue, editingCell, onUpdate, sortBy, sortDir, ledgerSuggestions]
  );

  const getRowClass = useCallback((params: RowClassParams<Transaction>) => {
    const tx = params.data;
    if (!tx) return "";
    const conf = Number(tx.confidence || 1);
    const ocrConf = Number(tx.ocr_confidence || 0);
    
    let classes = ["!border-b", "!border-white/10", "transition-colors"];
    
    if (tx.is_ignored) {
      classes.push("!opacity-40", "!grayscale", "!bg-transparent", "!border-l-4", "!border-l-gray-600/50");
    } else if (ocrConf > 0 && ocrConf < 0.7) {
      classes.push("!bg-red-500/10", "!border-l-4", "!border-l-red-500");
    } else if (ocrConf > 0 && ocrConf < 0.85) {
      classes.push("!bg-amber-500/5", "!border-l-4", "!border-l-amber-500");
    } else if (!tx.confirmed_ledger) {
      classes.push("!bg-red-500/5");
    } else if (conf < 0.5) {
      classes.push("!bg-red-500/10");
    } else if (conf < 0.8) {
      classes.push("!bg-yellow-500/10");
    }

    if (activeRowId === tx.id) {
      classes.push("!ring-1", "!ring-inset", "!ring-amber-400/60", "!bg-amber-500/20");
    }
    if (onRowClick && tx.page_number) {
      classes.push("cursor-pointer");
    }
    
    return classes.join(" ");
  }, [activeRowId, onRowClick]);

  const handleRowClick = useCallback((e: RowClickedEvent<Transaction>) => {
    const tx = e.data;
    if (!tx) return;
    
    // Ignore clicks on inputs or buttons
    const target = e.event?.target as HTMLElement;
    if (target?.closest("input, button, select, a, .ag-selection-checkbox")) return;

    if (onRowClick) {
      setActiveRowId(tx.id);
      onRowClick(tx.id, tx.page_number ?? null, tx.bbox ?? null);
    }
  }, [onRowClick]);

  const handleSelectionChanged = useCallback((e: SelectionChangedEvent<Transaction>) => {
    const selectedNodes = e.api.getSelectedNodes();
    const selectedIds = selectedNodes.map(node => node.data?.id).filter(Boolean) as string[];
    setRowSelection(selectedIds);
  }, []);

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

      {rowSelection.length > 0 && onBulkUpdate && (
        <div className="flex items-center gap-3 rounded-lg border border-blue-500/30 bg-blue-500/10 p-3">
          <span className="text-sm font-medium text-blue-200">
            {rowSelection.length} selected
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
              onBulkUpdate(rowSelection, { confirmed_ledger: bulkLedger });
              setBulkLedger("");
            }}
            disabled={!bulkLedger}
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            Apply to All
          </button>
        </div>
      )}

      {/* AG Grid container */}
      <div className="ag-theme-quartz-dark rounded-lg border border-white/10 overflow-hidden" style={{ height: "65vh", minHeight: "400px" }}>
        <AgGridReact
          rowData={filtered}
          columnDefs={columns}
          rowSelection="multiple"
          onSelectionChanged={handleSelectionChanged}
          getRowId={(params) => params.data.id}
          getRowClass={getRowClass}
          onRowClicked={handleRowClick}
          rowHeight={48}
          suppressRowClickSelection={true}
          suppressCellFocus={true}
          enableCellTextSelection={true}
        />
      </div>

      {/* Keep pagination controls if they still want them for server-side fetches, though AG Grid handles all filtered data */}
      {pagination && (
        <div className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 p-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-400">Rows per page:</span>
            <select
              value={pageSize}
              onChange={(event) => onPageSizeChange(parseInt(event.target.value))}
              className="rounded border border-white/10 bg-white/10 px-2 py-1 text-sm text-white focus:outline-none"
            >
              {[25, 50, 100, 250, 500, 1000].map((size) => (
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
