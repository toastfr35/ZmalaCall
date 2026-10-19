package org.zmala.phone;

import java.util.function.BooleanSupplier;
import java.util.function.Consumer;
import java.util.function.LongSupplier;

// @llr LLR-AND-CALL-004
/** Leave the native incoming-state callback before accepting a notification answer. */
final class PushAnswer {
  static void enqueue(Consumer<Runnable> queue, LongSupplier clock, long expires,
      BooleanSupplier stillIncoming, Runnable answer) {
    queue.accept(() -> {
      if (clock.getAsLong() < expires && stillIncoming.getAsBoolean()) answer.run();
    });
  }
}
