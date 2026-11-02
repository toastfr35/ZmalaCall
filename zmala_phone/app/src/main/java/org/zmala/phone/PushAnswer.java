package org.zmala.phone;

import java.util.function.BooleanSupplier;
import java.util.function.Consumer;
import java.util.function.LongSupplier;

// @llr LLR-AND-CALL-004
/** Leave the native incoming-state callback before accepting a notification answer. */
final class PushAnswer {
  /** One verified answer intent, consumed once by the matching native call. */
  static final class Pending {
    final String callId;
    final long expires;
    Pending(String callId, long expires) { this.callId = callId; this.expires = expires; }
  }
  private Pending pending;
  void remember(String callId, long expires) { pending = new Pending(callId, expires); }
  Pending consume(String callId, long now) {
    if (pending == null) return null;
    if (pending.expires <= now) { pending = null; return null; }
    if (!pending.callId.equals(callId)) return null;
    Pending result = pending; pending = null; return result;
  }
  static void enqueue(Consumer<Runnable> queue, LongSupplier clock, long expires,
      BooleanSupplier stillIncoming, Runnable answer) {
    queue.accept(() -> {
      if (clock.getAsLong() < expires && stillIncoming.getAsBoolean()) answer.run();
    });
  }
}
