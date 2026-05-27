"use client";

import { useEffect, useRef, useState } from "react";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
const MAX_MESSAGES = 200;

type StreamUsage = {
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
};

export type StreamMessage =
  | { type: "thought"; content: string }
  | { type: "phase"; phase: string; tool?: string | null }
  | { type: "tabpfn_estimate"; known_calls: number; unknown_backtest: boolean; note: string }
  | {
      type: "tabpfn_progress";
      completed_calls: number;
      estimated_calls: number;
      unknown_backtest: boolean;
      tool?: string | null;
    }
  | { type: "tool_call"; tool: string; input: unknown }
  | { type: "tool_result"; tool: string; output: unknown }
  | { type: "prediction"; regime: string; confidence: number }
  | {
      type: "done";
      summary: string;
      usage?: StreamUsage;
    }
  | { type: "unknown"; originalType: string; payload: Record<string, unknown> };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOptionalTool(payload: Record<string, unknown>) {
  return (
    payload.tool === undefined ||
    typeof payload.tool === "string" ||
    payload.tool === null
  );
}

function hasValidUsage(payload: Record<string, unknown>) {
  if (payload.usage === undefined) return true;
  if (!isRecord(payload.usage)) return false;

  return (
    typeof payload.usage.input_tokens === "number" &&
    typeof payload.usage.output_tokens === "number" &&
    typeof payload.usage.estimated_cost_usd === "number"
  );
}

function parseUsage(usage: Record<string, unknown>): StreamUsage {
  return {
    input_tokens: usage.input_tokens as number,
    output_tokens: usage.output_tokens as number,
    estimated_cost_usd: usage.estimated_cost_usd as number,
  };
}

function parseKnownStreamMessage(
  payload: Record<string, unknown>
): StreamMessage | null {
  switch (payload.type) {
    case "thought":
      return typeof payload.content === "string"
        ? { type: "thought", content: payload.content }
        : null;
    case "phase":
      if (typeof payload.phase !== "string" || !hasOptionalTool(payload)) {
        return null;
      }
      return payload.tool === undefined
        ? { type: "phase", phase: payload.phase }
        : {
            type: "phase",
            phase: payload.phase,
            tool: payload.tool as string | null,
          };
    case "tabpfn_estimate":
      return typeof payload.known_calls === "number" &&
        typeof payload.unknown_backtest === "boolean" &&
        typeof payload.note === "string"
        ? {
            type: "tabpfn_estimate",
            known_calls: payload.known_calls,
            unknown_backtest: payload.unknown_backtest,
            note: payload.note,
          }
        : null;
    case "tabpfn_progress":
      if (
        typeof payload.completed_calls !== "number" ||
        typeof payload.estimated_calls !== "number" ||
        typeof payload.unknown_backtest !== "boolean" ||
        !hasOptionalTool(payload)
      ) {
        return null;
      }
      return payload.tool === undefined
        ? {
            type: "tabpfn_progress",
            completed_calls: payload.completed_calls,
            estimated_calls: payload.estimated_calls,
            unknown_backtest: payload.unknown_backtest,
          }
        : {
            type: "tabpfn_progress",
            completed_calls: payload.completed_calls,
            estimated_calls: payload.estimated_calls,
            unknown_backtest: payload.unknown_backtest,
            tool: payload.tool as string | null,
          };
    case "tool_call":
      return typeof payload.tool === "string"
        ? { type: "tool_call", tool: payload.tool, input: payload.input }
        : null;
    case "tool_result":
      return typeof payload.tool === "string"
        ? { type: "tool_result", tool: payload.tool, output: payload.output }
        : null;
    case "prediction":
      return typeof payload.regime === "string" &&
        typeof payload.confidence === "number"
        ? {
            type: "prediction",
            regime: payload.regime,
            confidence: payload.confidence,
          }
        : null;
    case "done":
      if (typeof payload.summary !== "string" || !hasValidUsage(payload)) {
        return null;
      }
      return payload.usage === undefined
        ? { type: "done", summary: payload.summary }
        : {
            type: "done",
            summary: payload.summary,
            usage: parseUsage(payload.usage as Record<string, unknown>),
          };
    default:
      return null;
  }
}

function normalizeStreamMessage(payload: unknown): StreamMessage {
  if (!isRecord(payload)) {
    return {
      type: "unknown",
      originalType: "unknown",
      payload: { value: payload },
    };
  }

  const originalType =
    typeof payload.type === "string" ? payload.type : "unknown";

  const knownMessage = parseKnownStreamMessage(payload);
  if (knownMessage) {
    return knownMessage;
  }

  return {
    type: "unknown",
    originalType,
    payload,
  };
}

export function useRunStream(runId: string | null) {
  const [messages, setMessages] = useState<StreamMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;

    const socket = new WebSocket(`${WS_URL}/ws/runs/${runId}/stream`);
    ws.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = (event) => {
      let msg: StreamMessage;
      try {
        msg = normalizeStreamMessage(JSON.parse(event.data as string));
      } catch {
        msg = {
          type: "unknown",
          originalType: "invalid_json",
          payload: { value: String(event.data) },
        };
      }

      setMessages((prev) =>
        prev.length >= MAX_MESSAGES
          ? [...prev.slice(1), msg]
          : [...prev, msg]
      );
    };

    return () => {
      socket.close();
      setMessages([]);
    };
  }, [runId]);

  return { messages, connected };
}
