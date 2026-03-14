/**
 * Delta buffer for smooth character-by-character SSE stream rendering.
 * Manages per-actor queues with timed flush to avoid rendering jank.
 */

import type { GameStreamEvent } from "@/lib/game-types";

const STREAM_RENDER_INTERVAL_MS = 26;
const STREAM_LATIN_CHUNK_SIZE = 3;

interface DeltaBufferEntry {
  queue: string[];
  pumping: boolean;
  endEvent?: GameStreamEvent;
  timerId: number | null;
}

export class StreamBuffer {
  private buffers: Record<string, DeltaBufferEntry> = {};

  constructor(
    private onAppend: (actorKey: string, delta: string) => void,
    private onFinalize: (actorKey: string, endEvent: GameStreamEvent) => void,
  ) {}

  /** Get the actor key from a stream event. */
  static getActorKey(evt: GameStreamEvent): string {
    return evt.character_id || evt.character_name || "__unknown_stream_actor";
  }

  /** Split delta text into display-sized chunks. */
  private splitDelta(deltaText: string): string[] {
    if (!deltaText) return [];
    const chars = Array.from(deltaText);
    const hasCJK = /[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]/.test(deltaText);
    const step = hasCJK ? 1 : STREAM_LATIN_CHUNK_SIZE;
    const chunks: string[] = [];
    for (let i = 0; i < chars.length; i += step) {
      chunks.push(chars.slice(i, i + step).join(""));
    }
    return chunks;
  }

  /** Pump the next chunk from an actor's queue. */
  private pump(actorKey: string): void {
    const buffer = this.buffers[actorKey];
    if (!buffer) return;
    if (buffer.queue.length === 0) {
      buffer.pumping = false;
      buffer.timerId = null;
      if (buffer.endEvent) {
        const endEvent = buffer.endEvent;
        delete this.buffers[actorKey];
        this.onFinalize(actorKey, endEvent);
      }
      return;
    }
    const nextChunk = buffer.queue.shift()!;
    this.onAppend(actorKey, nextChunk);
    buffer.timerId = window.setTimeout(() => this.pump(actorKey), STREAM_RENDER_INTERVAL_MS);
  }

  /** Reset buffer for an actor (called on stream_start). */
  resetActor(actorKey: string): void {
    const existing = this.buffers[actorKey];
    if (existing?.timerId !== null && existing?.timerId !== undefined) {
      window.clearTimeout(existing.timerId);
    }
    this.buffers[actorKey] = { queue: [], pumping: false, timerId: null };
  }

  /** Enqueue delta chunks for an actor. */
  enqueueDelta(evt: GameStreamEvent): void {
    if (!evt.delta) return;
    const actorKey = StreamBuffer.getActorKey(evt);
    let buffer = this.buffers[actorKey];
    if (!buffer) {
      buffer = { queue: [], pumping: false, timerId: null };
      this.buffers[actorKey] = buffer;
    }
    buffer.queue.push(...this.splitDelta(evt.delta));
    if (!buffer.pumping) {
      buffer.pumping = true;
      this.pump(actorKey);
    }
  }

  /** Mark stream end for an actor. If no pending data, finalize immediately. */
  markEnd(actorKey: string, endEvent: GameStreamEvent): void {
    let buffer = this.buffers[actorKey];
    if (!buffer) {
      buffer = { queue: [], pumping: false, timerId: null };
      this.buffers[actorKey] = buffer;
    }
    buffer.endEvent = endEvent;
    if (!buffer.pumping && buffer.queue.length === 0) {
      delete this.buffers[actorKey];
      this.onFinalize(actorKey, endEvent);
    }
  }

  /** Clear all pending buffers and cancel timers. */
  clear(): void {
    for (const key of Object.keys(this.buffers)) {
      const timerId = this.buffers[key]?.timerId;
      if (timerId !== null && timerId !== undefined) {
        window.clearTimeout(timerId);
      }
    }
    this.buffers = {};
  }

  /** Check if any buffer has pending data. */
  hasPending(): boolean {
    return Object.values(this.buffers).some(
      (buffer) => buffer.pumping || buffer.queue.length > 0
    );
  }

  /** Run a function when all buffers are idle. */
  runWhenIdle(fn: () => void): void {
    if (!this.hasPending()) {
      fn();
      return;
    }
    window.setTimeout(() => this.runWhenIdle(fn), STREAM_RENDER_INTERVAL_MS);
  }
}
