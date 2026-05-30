import { create } from "zustand";
import type { AnalysisResult } from "./api";
import type { StreamMessage } from "./websocket";

type StoreStatus = "idle" | "running" | "completed" | "failed" | "canceled";

type LastRunParams = {
  date_range_start: string;
  date_range_end: string;
  analysis_mode: "quick" | "full";
};

export type ChatMessage = {
  id: string;
  role: "user" | "agent";
  content: string;
  timestamp: number;
  toolPill?: { name: string; status: "running" | "done" | "failed" };
};

type RunStore = {
  runId: string | null;
  status: StoreStatus;
  result: AnalysisResult | null;
  error: string | null;
  messages: StreamMessage[];
  lastRunParams: LastRunParams | null;
  chatOpen: boolean;
  chatMessages: ChatMessage[];
  pendingPreRunMessages: string[];
  setRun: (runId: string, params: LastRunParams) => void;
  setResult: (result: AnalysisResult) => void;
  setStatus: (status: StoreStatus) => void;
  setError: (error: string) => void;
  setMessages: (msgs: StreamMessage[]) => void;
  setCanceled: () => void;
  clearRun: () => void;
  hydrate: () => void;
  setChatOpen: (open: boolean) => void;
  addChatMessage: (msg: ChatMessage) => void;
  queuePreRunMessage: (msg: string) => void;
  clearPreRunMessages: () => void;
};

const RUN_ID_KEY = "activeRunId";
const MESSAGES_KEY = "activeRunMessages";

function readPersistedRunId(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(RUN_ID_KEY);
}

function readPersistedMessages(): StreamMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = sessionStorage.getItem(MESSAGES_KEY);
    return raw ? (JSON.parse(raw) as StreamMessage[]) : [];
  } catch {
    return [];
  }
}

function clearPersisted() {
  sessionStorage.removeItem(RUN_ID_KEY);
  sessionStorage.removeItem(MESSAGES_KEY);
}

export const useRunStore = create<RunStore>((set) => ({
  runId: null,
  status: "idle",
  result: null,
  error: null,
  messages: [],
  lastRunParams: null,
  chatOpen: false,
  chatMessages: [],
  pendingPreRunMessages: [],
  setRun: (runId, params) => {
    sessionStorage.setItem(RUN_ID_KEY, runId);
    sessionStorage.removeItem(MESSAGES_KEY);
    set({
      runId,
      status: "running",
      result: null,
      error: null,
      messages: [],
      lastRunParams: params,
    });
  },
  setResult: (result) => {
    clearPersisted();
    set({ result, status: "completed" });
  },
  setStatus: (status) => set({ status }),
  setError: (error) => {
    set({ error, status: "failed" });
  },
  setMessages: (messages) => {
    try {
      sessionStorage.setItem(MESSAGES_KEY, JSON.stringify(messages));
    } catch {
      // sessionStorage full - continue without persisting
    }
    set({ messages });
  },
  setCanceled: () => set({ status: "canceled" }),
  clearRun: () => {
    clearPersisted();
    // chatOpen is intentionally NOT reset — panel visibility persists across runs
    set({
      runId: null,
      status: "idle",
      result: null,
      error: null,
      messages: [],
      lastRunParams: null,
      chatMessages: [],
      pendingPreRunMessages: [],
    });
  },
  hydrate: () => {
    const runId = readPersistedRunId();
    const messages = readPersistedMessages();
    if (runId) set({ runId, messages });
  },
  setChatOpen: (open) => set({ chatOpen: open }),
  addChatMessage: (msg) =>
    set((state) => ({ chatMessages: [...state.chatMessages, msg] })),
  queuePreRunMessage: (msg) =>
    set((state) => ({ pendingPreRunMessages: [...state.pendingPreRunMessages, msg] })),
  clearPreRunMessages: () => set({ pendingPreRunMessages: [] }),
}));
