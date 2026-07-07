import { create } from "zustand";

export type BboxCoords = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

interface ReviewUIState {
  selectedPage: number | null;
  selectedBbox: BboxCoords | null;
  activeRowId: string | null;
  activeTab: "transactions" | "pdf";
  setSelectedPage: (page: number | null) => void;
  setSelectedBbox: (bbox: BboxCoords | null) => void;
  setActiveRowId: (rowId: string | null) => void;
  setActiveTab: (tab: "transactions" | "pdf") => void;
  resetUI: () => void;
}

export const useReviewStore = create<ReviewUIState>((set) => ({
  selectedPage: null,
  selectedBbox: null,
  activeRowId: null,
  activeTab: "transactions",
  setSelectedPage: (page) => set({ selectedPage: page }),
  setSelectedBbox: (bbox) => set({ selectedBbox: bbox }),
  setActiveRowId: (rowId) => set({ activeRowId: rowId }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  resetUI: () => set({ selectedPage: null, selectedBbox: null, activeRowId: null, activeTab: "transactions" }),
}));
