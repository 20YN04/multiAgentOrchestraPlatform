"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";

import type {
  AgentStreamEvent,
  AgentTurn,
  AgentTurnEvent,
  StartStreamInput,
  StreamStatus,
} from "../lib/agent-stream-types";

interface StreamState {
  status: StreamStatus;
  turns: AgentTurn[];
  events: AgentTurnEvent[];
  errorMessage: string | null;
}

type StreamAction =
  | { type: "RESET" }
  | { type: "CONNECTING" }
  | { type: "STREAMING" }
  | { type: "APPEND_EVENT"; event: AgentStreamEvent }
  | { type: "COMPLETE" }
  | { type: "ERROR"; message: string };

const INITIAL_STATE: StreamState = {
  status: "idle",
  turns: [],
  events: [],
  errorMessage: null,
};

const EVENT_TYPES: ReadonlySet<string> = new Set([
  "thought",
  "tool_execution",
  "final_answer",
  "error",
]);

function createEventId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function normalizeIncomingEvent(value: unknown): AgentStreamEvent | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }

  const candidate = value as Partial<AgentStreamEvent>;
  if (
    typeof candidate.agent_name !== "string" ||
    typeof candidate.content !== "string" ||
    typeof candidate.event_type !== "string"
  ) {
    return null;
  }

  if (!EVENT_TYPES.has(candidate.event_type)) {
    return null;
  }

  return {
    agent_name: candidate.agent_name,
    event_type: candidate.event_type,
    content: candidate.content,
  };
}

function appendByAgentTurn(turns: AgentTurn[], incoming: AgentTurnEvent): AgentTurn[] {
  const lastTurn = turns.at(-1);
  if (!lastTurn || lastTurn.agentName !== incoming.agent_name) {
    return [
      ...turns,
      {
        id: `turn-${incoming.id}`,
        agentName: incoming.agent_name,
        startedAt: incoming.receivedAt,
        events: [incoming],
      },
    ];
  }

  const updatedLast: AgentTurn = {
    ...lastTurn,
    events: [...lastTurn.events, incoming],
  };

  return [...turns.slice(0, -1), updatedLast];
}

function reducer(state: StreamState, action: StreamAction): StreamState {
  switch (action.type) {
    case "RESET": {
      return INITIAL_STATE;
    }
    case "CONNECTING": {
      return {
        ...INITIAL_STATE,
        status: "connecting",
      };
    }
    case "STREAMING": {
      if (state.status === "streaming") {
        return state;
      }
      return {
        ...state,
        status: "streaming",
      };
    }
    case "APPEND_EVENT": {
      const eventWithMeta: AgentTurnEvent = {
        ...action.event,
        id: createEventId(),
        receivedAt: Date.now(),
      };

      const nextStatus: StreamStatus =
        eventWithMeta.event_type === "error" ? "error" : state.status;
      const errorMessage =
        eventWithMeta.event_type === "error" ? eventWithMeta.content : state.errorMessage;

      return {
        ...state,
        status: nextStatus,
        errorMessage,
        events: [...state.events, eventWithMeta],
        turns: appendByAgentTurn(state.turns, eventWithMeta),
      };
    }
    case "COMPLETE": {
      return {
        ...state,
        status: state.status === "error" ? "error" : "completed",
      };
    }
    case "ERROR": {
      return {
        ...state,
        status: "error",
        errorMessage: action.message,
      };
    }
    default: {
      return state;
    }
  }
}

export interface UseAgentStreamResult {
  status: StreamStatus;
  turns: AgentTurn[];
  events: AgentTurnEvent[];
  errorMessage: string | null;
  startStream: (input: StartStreamInput) => void;
  stopStream: () => void;
  reset: () => void;
}

export function useAgentStream(): UseAgentStreamResult {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const eventSourceRef = useRef<EventSource | null>(null);

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    stopStream();
    dispatch({ type: "RESET" });
  }, [stopStream]);

  useEffect(() => {
    return () => {
      stopStream();
    };
  }, [stopStream]);

  const startStream = useCallback(
    (input: StartStreamInput) => {
      stopStream();

      const prompt = input.prompt.trim();
      if (!prompt) {
        dispatch({ type: "ERROR", message: "Prompt cannot be empty." });
        return;
      }

      dispatch({ type: "CONNECTING" });

      const params = new URLSearchParams();
      params.set("prompt", prompt);
      if (input.modelName) {
        params.set("model_name", input.modelName);
      }
      if (typeof input.temperature === "number") {
        params.set("temperature", String(input.temperature));
      }
      if (typeof input.timeoutSeconds === "number") {
        params.set("timeout_seconds", String(input.timeoutSeconds));
      }

      const source = new EventSource(`/api/agents/run?${params.toString()}`);
      eventSourceRef.current = source;

      source.onopen = () => {
        dispatch({ type: "STREAMING" });
      };

      source.onmessage = (event: MessageEvent<string>) => {
        try {
          const parsed = normalizeIncomingEvent(JSON.parse(event.data));
          if (!parsed) {
            return;
          }

          dispatch({ type: "APPEND_EVENT", event: parsed });

          if (parsed.event_type === "final_answer" || parsed.event_type === "error") {
            source.close();
            if (eventSourceRef.current === source) {
              eventSourceRef.current = null;
            }
            dispatch({ type: "COMPLETE" });
          }
        } catch {
          dispatch({
            type: "ERROR",
            message: "Malformed stream event received from server.",
          });
          source.close();
          if (eventSourceRef.current === source) {
            eventSourceRef.current = null;
          }
        }
      };

      source.onerror = () => {
        dispatch({
          type: "ERROR",
          message: "Stream connection dropped before completion.",
        });
        source.close();
        if (eventSourceRef.current === source) {
          eventSourceRef.current = null;
        }
      };
    },
    [stopStream]
  );

  return useMemo(
    () => ({
      status: state.status,
      turns: state.turns,
      events: state.events,
      errorMessage: state.errorMessage,
      startStream,
      stopStream,
      reset,
    }),
    [state, startStream, stopStream, reset]
  );
}