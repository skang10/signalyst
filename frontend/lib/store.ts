import { create } from "zustand";
import type {
  ActivityEvent,
  ChatMessage,
  FeaturizerConfig,
  Session,
  SessionArtifacts,
  SessionStage,
  SessionStatus,
} from "./api";

type WsMessage = Record<string, unknown> & { type: string };

const EMPTY_ARTIFACTS: SessionArtifacts = { data: [], features: [], analysis: [] };
const MAX_WS_MESSAGES = 500;

type SessionStore = {
  sessionId: string | null;
  stage: SessionStage | null;
  status: SessionStatus | null;
  featurizerConfig: FeaturizerConfig | null;
  conversation: ChatMessage[];
  activityEvents: ActivityEvent[];
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
  featurizerConfig: null,
  conversation: [],
  activityEvents: [],
  wsMessages: [],
  artifacts: EMPTY_ARTIFACTS,
  error: null,

  setSession: (session) =>
    set((state) => ({
      sessionId: session.session_id,
      stage: session.stage,
      status: session.status,
      featurizerConfig: session.featurizer_config,
      conversation: session.conversation,
      activityEvents: session.activity_events,
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
      featurizerConfig: null,
      conversation: [],
      activityEvents: [],
      wsMessages: [],
      artifacts: EMPTY_ARTIFACTS,
      error: null,
    }),
}));
