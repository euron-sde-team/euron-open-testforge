// Loaded into every Node process of a sandboxed run (NODE_OPTIONS=--require ...).
//
// The sandbox has no /proc (see docs/architecture/sandbox.md), and Node's
// process.memoryUsage() reads /proc/self/statm for the resident set size, so it throws
// ENOENT there. Vitest calls it between test files and would wait forever on the error.
// This keeps every other field exact and reports the peak resident size from getrusage
// (which needs no /proc) when the current one cannot be read.
"use strict";
const v8 = require("node:v8");

const original = process.memoryUsage.bind(process);

function fallback() {
  const heap = v8.getHeapStatistics();
  return {
    rss: process.resourceUsage().maxRSS * 1024,
    heapTotal: heap.total_heap_size,
    heapUsed: heap.used_heap_size,
    external: heap.external_memory || 0,
    arrayBuffers: 0,
  };
}

function memoryUsage() {
  try {
    return original();
  } catch {
    return fallback();
  }
}
memoryUsage.rss = function rss() {
  try {
    return original.rss ? original.rss() : original().rss;
  } catch {
    return process.resourceUsage().maxRSS * 1024;
  }
};
process.memoryUsage = memoryUsage;
