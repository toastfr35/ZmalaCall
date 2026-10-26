// @test A-LLT-019
// @requirements LLR-AND-UI-002
// @environment portable
// @plan Block a portrait fetch, replace the contact view, then release it. Queue more than forty
// images and close the loader. Check obsolete results/jobs and bounded best-effort overload.
// @pass Old queued jobs never run, in-flight results lose validity, current work completes, overload
// is discarded without blocking the caller, and closing invalidates tickets and refuses new work.
package org.zmala.phone;

import static org.junit.Assert.*;

import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.Test;

public class PortraitQueueTest {
  private static void await(CountDownLatch latch) {
    try { assertTrue("Portrait worker did not progress", latch.await(5, TimeUnit.SECONDS)); }
    catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new AssertionError(error); }
  }

  @Test public void replacingTheViewDropsObsoleteJobsAndResults() {
    CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
    AtomicInteger obsolete = new AtomicInteger();
    try (PortraitQueue queue = new PortraitQueue()) {
      long first = queue.begin();
      queue.execute(first, () -> {
        entered.countDown();
        await(release);
        if (queue.current(first)) obsolete.incrementAndGet();
      });
      await(entered);
      queue.execute(first, obsolete::incrementAndGet);
      long next = queue.begin();
      assertFalse(queue.current(first));
      CountDownLatch current = new CountDownLatch(1);
      queue.execute(first, obsolete::incrementAndGet);
      queue.execute(next, current::countDown);
      release.countDown();
      await(current);
      assertEquals(0, obsolete.get());
      assertTrue(queue.current(next));
    } finally { release.countDown(); }
  }

  @Test public void overloadIsBoundedAndClosingInvalidatesTickets() {
    CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
    AtomicInteger completed = new AtomicInteger();
    PortraitQueue queue = new PortraitQueue();
    try {
      long ticket = queue.begin();
      queue.execute(ticket, () -> { entered.countDown(); await(release); });
      await(entered);
      CountDownLatch full = new CountDownLatch(40);
      for (int i = 0; i < 80; i++) queue.execute(ticket, () -> {
        completed.incrementAndGet();
        full.countDown();
      });
      release.countDown();
      await(full);
      queue.close();
      assertFalse(queue.current(ticket));
      queue.execute(ticket, () -> fail("A closed queue accepted a job"));
      assertEquals(40, completed.get());
    } finally { release.countDown(); queue.close(); }
  }
}
