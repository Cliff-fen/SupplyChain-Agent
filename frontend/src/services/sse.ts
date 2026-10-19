export type SseEvent = { id?: number; event: string; data: Record<string, unknown> };

export function parseSseEvents(text: string): SseEvent[] {
  return text.split("\n\n").flatMap((block) => {
    const event = block.match(/^event: (.+)$/m)?.[1];
    const id = block.match(/^id: (\d+)$/m)?.[1];
    const raw = block.match(/^data: (.+)$/m)?.[1];
    if (!event || !raw) return [];
    try {
      return [{ id: id ? Number(id) : undefined, event, data: JSON.parse(raw) as Record<string, unknown> }];
    } catch {
      return [];
    }
  });
}

export async function readSseResponse(response: Response, onChunk?: (events: SseEvent[]) => void): Promise<string> {
  if (!response.body) return response.text();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    const chunkEvents = parseSseEvents(blocks.join("\n\n") + (blocks.length ? "\n\n" : ""));
    if (chunkEvents.length) onChunk?.(chunkEvents);
    text += blocks.join("\n\n") + (blocks.length ? "\n\n" : "");
  }
  text += buffer + decoder.decode();
  return text;
}
