// @test A-LLT-015
// @requirements LLR-AND-HISTORY-002
// @environment portable
// @plan Deliver duplicate push/native rings, cancellations, answers and expiry, serialize and reload
// history, clear counts, prune removed contacts and classify incoming/sent/completed callbacks.
// @pass A missed call counts once across delivery paths and restart; answered/declined calls do not
// count, count clearing is retained, and callback badges apply only to the correct pending pair.
package org.zmala.phone;

import static org.junit.Assert.*;
import org.json.*;
import org.junit.Test;

public class NoticeBookTest {
  @Test public void duplicateMissedAndAnsweredCallsPersist() {
    NoticeBook book = new NoticeBook("");
    book.ring("call1", "peer", 100);
    book.ring("call1", "peer", 200);
    book.finish("call1", true); book.finish("call1", true);
    assertEquals(1, book.count("peer"));
    book = new NoticeBook(book.toString());
    book.ring("call1", "peer", 200); book.expire(300);
    assertEquals(1, book.count("peer"));
    book.ring("answered", "peer", 500); book.finish("answered", false); book.expire(600);
    assertEquals(1, book.count("peer"));
    book.ring("expired", "peer", 1000); book.expire(999); assertEquals(1, book.count("peer"));
    book.expire(1000); assertEquals(2, book.count("peer"));
    book.clear("peer"); book.expire(2000); assertEquals(0, book.count("peer"));
    book.ring("new", "peer", 1000); book.expire(2000);
    book.retain(new JSONArray()); assertEquals(0, book.count("peer"));
  }
  @Test public void callbacksMatchPairAndStatus() throws Exception {
    JSONArray entries = new JSONArray().put(new JSONObject().put("from", "peer").put("to", "me").put("status", "pending"));
    assertEquals(1, NoticeBook.callbacks(entries, "me", "peer"));
    assertEquals(2, NoticeBook.callbacks(entries, "peer", "me"));
    assertEquals(0, NoticeBook.callbacks(entries, "stranger", "peer"));
    entries.getJSONObject(0).put("status", "completed");
    assertEquals(0, NoticeBook.callbacks(entries, "me", "peer"));
  }
}
