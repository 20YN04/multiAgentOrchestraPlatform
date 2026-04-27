import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function sseHeaders(): HeadersInit {
  return {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  };
}

function makeErrorSseFrame(content: string): string {
  return `data: ${JSON.stringify({
    agent_name: "system",
    event_type: "error",
    content,
  })}\n\n`;
}

function toFiniteNumber(value: string | null, fallback: number): number {
  if (value === null) {
    return fallback;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }

  return parsed;
}

export async function GET(request: NextRequest): Promise<Response> {
  const search = request.nextUrl.searchParams;
  const prompt = (search.get("prompt") ?? "").trim();

  if (!prompt) {
    return new Response(makeErrorSseFrame("Prompt is required."), {
      status: 400,
      headers: sseHeaders(),
    });
  }

  const modelName = (search.get("model_name") ?? "gpt-4o-mini").trim() || "gpt-4o-mini";
  const temperature = toFiniteNumber(search.get("temperature"), 0.1);
  const timeoutSeconds = toFiniteNumber(search.get("timeout_seconds"), 120);

  const backendBaseUrl = process.env.NEXT_PUBLIC_AGENT_API_BASE_URL ?? "http://127.0.0.1:8000";
  const backendUrl = `${backendBaseUrl.replace(/\/$/, "")}/api/v1/agents/run`;

  const upstreamResponse = await fetch(backendUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      prompt,
      model_name: modelName,
      temperature,
      timeout_seconds: timeoutSeconds,
    }),
    cache: "no-store",
  }).catch(() => null);

  if (!upstreamResponse || !upstreamResponse.ok || !upstreamResponse.body) {
    return new Response(
      makeErrorSseFrame("Could not connect to the agent backend stream."),
      {
        status: 502,
        headers: sseHeaders(),
      }
    );
  }

  const stream = new ReadableStream<Uint8Array>({
    async start(controller): Promise<void> {
      const reader = upstreamResponse.body!.getReader();
      const encoder = new TextEncoder();

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }
          if (value) {
            controller.enqueue(value);
          }
        }
      } catch {
        controller.enqueue(
          encoder.encode(makeErrorSseFrame("Agent stream interrupted unexpectedly."))
        );
      } finally {
        reader.releaseLock();
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: sseHeaders(),
  });
}