export type AgentEventType =
  | "thought"
  | "tool_execution"
  | "final_answer"
  | "error";

export interface AgentStreamEvent {
  agent_name: string;
  event_type: AgentEventType;
  content: string;
}

export interface AgentTurnEvent extends AgentStreamEvent {
  id: string;
  receivedAt: number;
}

export interface AgentTurn {
  id: string;
  agentName: string;
  startedAt: number;
  events: AgentTurnEvent[];
}

export interface StartStreamInput {
  prompt: string;
  modelName?: string;
  temperature?: number;
  timeoutSeconds?: number;
}

export type StreamStatus = "idle" | "connecting" | "streaming" | "completed" | "error";