package org.zmala.phone;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

// @llr LLR-AND-UI-002
/** Best-effort images must never hold up configuration, presence or callback requests. */
final class PortraitQueue implements AutoCloseable {
  private final ThreadPoolExecutor worker = new ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS,
      new ArrayBlockingQueue<>(40), new ThreadPoolExecutor.DiscardPolicy());
  private long generation;

  /** In-flight HTTP may finish, but queued jobs and results from the old view are obsolete. */
  synchronized long begin() {
    generation++;
    worker.getQueue().clear();
    return generation;
  }

  synchronized boolean current(long ticket) {
    return ticket == generation && !worker.isShutdown();
  }

  synchronized void execute(long ticket, Runnable load) {
    if (current(ticket)) worker.execute(() -> {
      if (current(ticket)) load.run();
    });
  }

  @Override public synchronized void close() {
    generation++;
    worker.shutdownNow();
  }
}
