import type { ActivityEvent, ChatMessage } from "./api";

export type FetchRow = {
  id: string;
  tool: string;
  input: Record<string, unknown>;
  result: Record<string, unknown> | null;
  callTime: string;
  resultTime: string | null;
};

export type ThoughtEntry = {
  id: string;
  content: string;
  time: string;
};

export type StageGroup = {
  stage: string;
  startTime: string;
  status: "done" | "active" | "failed";
  thoughts: ThoughtEntry[];
  fetchRows: FetchRow[];
  chatMessages: ChatMessage[];
  completionEvent: Record<string, unknown> | null;
  errorEvent: Record<string, unknown> | null;
  cacheHitEvent: Record<string, unknown> | null;
};

type MutableGroup = Omit<StageGroup, "status"> & {
  pendingQueues: Map<string, FetchRow[]>;
};

function newGroup(stage: string, startTime: string): MutableGroup {
  return {
    stage,
    startTime,
    thoughts: [],
    fetchRows: [],
    chatMessages: [],
    pendingQueues: new Map(),
    completionEvent: null,
    errorEvent: null,
    cacheHitEvent: null,
  };
}

function flushPending(g: MutableGroup) {
  g.pendingQueues.forEach((queue) => g.fetchRows.push(...queue));
  g.pendingQueues.clear();
}

export function buildGroups(
  activityEvents: ActivityEvent[],
  wsMessages: Record<string, unknown>[],
  conversation: ChatMessage[],
  currentStage: string | null,
  currentStatus: string | null,
): StageGroup[] {
  const ts = (iso: string | undefined) => (iso ? new Date(iso).getTime() || Date.now() : Date.now());

  const merged = [
    ...activityEvents.map((e) => ({ t: ts(e.created_at), ev: e as Record<string, unknown> })),
    ...wsMessages
      .filter((m) => ["thought", "tool_call", "tool_result"].includes(m.type as string))
      .map((m) => ({ t: ts(m.created_at as string | undefined), ev: m })),
    ...conversation.map((m) => ({
      t: ts(m.created_at),
      ev: {
        type: "chat_message",
        role: m.role,
        content: m.content,
        created_at: m.created_at,
      } as Record<string, unknown>,
    })),
  ].sort((a, b) => a.t - b.t);

  let cur = newGroup("configuring", "");
  const completed: MutableGroup[] = [];
  let thoughtIdx = 0;
  let fetchIdx = 0;

  for (const { ev } of merged) {
    const type = ev.type as string;

    if (type === "stage_transition") {
      flushPending(cur);
      completed.push(cur);
      cur = newGroup((ev.to as string) ?? "", (ev.created_at as string) ?? "");
    } else if (type === "cache_hit") {
      cur.cacheHitEvent = ev;
    } else if (type === "artifact_ready") {
      if (!cur.startTime) cur.startTime = (ev.created_at as string) ?? "";
      cur.completionEvent = ev;
    } else if (type === "error") {
      cur.errorEvent = ev;
    } else if (type === "thought") {
      cur.thoughts.push({
        id: `th-${thoughtIdx++}`,
        content: (ev.content as string) ?? "",
        time: (ev.created_at as string) ?? "",
      });
    } else if (type === "tool_call") {
      const tool = ev.tool as string;
      if (tool === "complete") continue;
      const row: FetchRow = {
        id: `fr-${fetchIdx++}`,
        tool,
        input: (ev.input as Record<string, unknown>) ?? {},
        result: null,
        callTime: (ev.created_at as string) ?? "",
        resultTime: null,
      };
      const q = cur.pendingQueues.get(tool) ?? [];
      q.push(row);
      cur.pendingQueues.set(tool, q);
    } else if (type === "tool_result") {
      const tool = ev.tool as string;
      const q = cur.pendingQueues.get(tool);
      if (q?.length) {
        const row = q.shift()!;
        row.result = (ev.output as Record<string, unknown>) ?? {};
        row.resultTime = (ev.created_at as string) ?? "";
        cur.fetchRows.push(row);
        if (q.length === 0) cur.pendingQueues.delete(tool);
      }
    } else if (type === "chat_message") {
      cur.chatMessages.push({
        role: ev.role as "user" | "assistant",
        content: ev.content as string,
        created_at: ev.created_at as string,
      });
    }
  }

  flushPending(cur);
  const all = [...completed, cur];

  return all.map((g, idx): StageGroup => {
    const isLast = idx === all.length - 1;
    let status: "done" | "active" | "failed" = "done";
    if (isLast) {
      if (g.errorEvent || currentStatus === "failed" || currentStatus === "canceled") {
        status = "failed";
      } else if (currentStatus === "running") {
        status = "active";
      } else {
        status = "done";
      }
    }
    const { pendingQueues: _, ...rest } = g;
    return { ...rest, status };
  });
}
