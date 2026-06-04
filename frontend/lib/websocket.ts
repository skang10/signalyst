"use client";

import { useEffect, useRef } from "react";
import { useSessionStore } from "./store";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

export function useSessionStream(sessionId: string | null) {
  const { appendWsMessage, setSession } = useSessionStore();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);

  useEffect(() => {
    if (!sessionId) return;

    function connect() {
      const socket = new WebSocket(`${WS_URL}/ws/sessions/${sessionId}/stream`);
      wsRef.current = socket;

      socket.onopen = () => {
        attemptRef.current = 0;
      };

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as Record<string, unknown> & {
            type: string;
          };
          if (msg.type === "stage_transition" || msg.type === "artifact_ready") {
            fetch(`${API_URL}/api/sessions/${sessionId}`)
              .then((r) => r.json())
              .then(setSession)
              .catch(() => {});
          }
          appendWsMessage(msg);
        } catch {
          // ignore malformed messages
        }
      };

      socket.onclose = () => {
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** attemptRef.current, RECONNECT_MAX_MS);
        attemptRef.current += 1;
        reconnectRef.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [sessionId, appendWsMessage, setSession]);
}
