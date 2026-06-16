import { create } from "zustand";
import type {
  ActivityEvent,
  ChatMessage,
  FeaturizerConfig,
  PendingSource,
  Session,
  SessionArtifacts,
  SessionStage,
  SessionStatus,
  StageHistoryEntry,
} from "./api";

type WsMessage = Record<string, unknown> & { type: string };

const EMPTY_ARTIFACTS: SessionArtifacts = { data: [], features: [], analysis: [] };
const MAX_WS_MESSAGES = 500;

type SessionStore = {
  sessionId: string | null;
  stage: SessionStage | null;
  status: SessionStatus | null;
  marketProfile: string | null;
  timeframeStart: string | null;
  timeframeEnd: string | null;
  pendingSources: PendingSource[];
  featurizerConfig: FeaturizerConfig | null;
  conversation: ChatMessage[];
  activityEvents: ActivityEvent[];
  stageHistory: StageHistoryEntry[];
  wsMessages: WsMessage[];
  artifacts: SessionArtifacts;
  error: string | null;

  setSession: (session: Session) => void;
  appendWsMessage: (msg: WsMessage) => void;
  clearSession: () => void;
};

export const useSessionStore = create<SessionStore>((set) => ({
  sessionId: null,
  stage: null,
  status: null,
  marketProfile: null,
  timeframeStart: null,
  timeframeEnd: null,
  pendingSources: [],
  featurizerConfig: null,
  conversation: [],
  activityEvents: [],
  stageHistory: [],
  wsMessages: [],
  artifacts: EMPTY_ARTIFACTS,
  error: null,

  setSession: (session) =>
    set((state) => ({
      sessionId: session.session_id,
      stage: session.stage,
      status: session.status,
      marketProfile: session.market_profile,
      timeframeStart: session.timeframe_start,
      timeframeEnd: session.timeframe_end,
      pendingSources: session.pending_sources ?? [],
      featurizerConfig: session.featurizer_config,
      conversation: session.conversation,
      activityEvents: session.activity_events,
      stageHistory: session.stage_history,
      artifacts: session.artifacts,
      error: session.error,
      wsMessages: state.sessionId !== session.session_id ? [] : state.wsMessages,
    })),

  appendWsMessage: (msg) =>
    set((state) => ({
      wsMessages:
        state.wsMessages.length >= MAX_WS_MESSAGES
          ? [...state.wsMessages.slice(1), msg]
          : [...state.wsMessages, msg],
    })),

  clearSession: () =>
    set({
      sessionId: null,
      stage: null,
      status: null,
      marketProfile: null,
      timeframeStart: null,
      timeframeEnd: null,
      pendingSources: [],
      featurizerConfig: null,
      conversation: [],
      activityEvents: [],
      stageHistory: [],
      wsMessages: [],
      artifacts: EMPTY_ARTIFACTS,
      error: null,
    }),
}));
