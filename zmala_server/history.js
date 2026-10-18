'use strict';
/** Retain all pending work plus the most recent completed records, preserving event order. */
// @llr LLR-SRV-CALLBACK-005
/** @template {{id: string}} T @param {T[]} items @param {(item: T) => boolean} pending @param {number} [limit] @returns {T[]} */
function retainHistory(items, pending, limit = 200) {
  const completed = items.filter((item) => !pending(item));
  const remove = new Set(
    completed.slice(0, Math.max(0, completed.length - limit)).map((item) => item.id),
  );
  return items.filter((item) => !remove.has(item.id));
}
module.exports = { retainHistory };
