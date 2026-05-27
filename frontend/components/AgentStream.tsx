"use client";

import { useEffect, useRef } from "react";
import { useRunStore } from "@/lib/store";
import { useRunStream } from "@/lib/websocket";
import { api } from "@/lib/api";
import type { AnalysisResult } from "@/lib/api";

export function AgentStream() {
  const { runId, status, setResult, setStatus, setError, setMessages, clearRun } = useRunStore();
  const { messages: wsMessages } = useRunStream(runId);

  // Capture values at mount to detect sessionStorage-restored runId/messages.
  const mountRunId = useRef(runId);
  const mountStatus = useRef(status);
  // History messages present at mount (restored from sessionStorage).
  const baselineMessages = useRef(useRunStore.getState().messages);

  // Recovery: if runId was restored from sessionStorage (status still "idle" on mount),
  // check the backend to restore the correct state before the WS catches up.
  useEffect(() => {
    const restoredRunId = mountRunId.current;
    const restoredStatus = mountStatus.current;
    if (!restoredRunId || restoredStatus !== "idle") return;

    setStatus("running");
    api
      .getRun(restoredRunId)
      .then((run) => {
        if (run.status === "completed") {
          if (run.result) setResult(run.result as AnalysisResult);
          else setError("Run completed but no result was returned.");
        } else if (run.status === "failed") {
          setError("Run failed.");
        } else if (run.status === "canceled") {
          clearRun();
        }
        // pending / running: stay "running" — WS will stream events and complete normally
      })
      .catch(() => clearRun());
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync WS messages to store, prepending any history from before the refresh.
  useEffect(() => {
    const baseline = baselineMessages.current;
    setMessages(baseline.length > 0 ? [...baseline, ...wsMessages] : wsMessages);
  }, [wsMessages, setMessages]);

  useEffect(() => {
    const last = wsMessages[wsMessages.length - 1];
    if (last?.type !== "done" || !runId || status === "completed") return;

    api
      .getRun(runId)
      .then((runResult) => {
        if (runResult.result) {
          setResult(runResult.result as AnalysisResult);
        } else {
          setStatus("failed");
        }
      })
      .catch(() => setStatus("failed"));
  }, [wsMessages, runId, status, setResult, setStatus]);

  return null;
}
