// @test A-LLT-026
// @requirements LLR-AND-HISTORY-003
// @environment portable
// @plan Reconcile incoming, sent, unauthorized, malformed and expired requests. Persist posted
// history and replay snapshots after dismissal; cancel/complete/revoke and extend a deadline.
// Exercise the 32-active and 512-seen bounds and corrupt-storage recovery.
// @pass Only valid incoming requests are fresh; posted IDs stay deduplicated across reload,
// removed state clears active IDs and all persisted collections stay within bounds.
package org.zmala.phone;

import static org.junit.Assert.*;
import java.time.Instant;
import org.json.*;
import org.junit.Test;

public class CallbackBookTest {
  static final long NOW = 1700000000000L;
  static String id(int n) { return String.format(java.util.Locale.ROOT,"%08d-0000-0000-0000-000000000000",n); }
  static JSONObject request(int n) throws Exception {
    return new JSONObject().put("id",id(n)).put("from","term1").put("to","phone1")
        .put("status","pending").put("expires_at",Instant.ofEpochMilli(NOW+3600000).toString());
  }
  static JSONObject config(JSONArray requests) throws Exception {
    return new JSONObject().put("callbacks_enabled",true).put("sip",new JSONObject().put("username","phone1"))
        .put("contacts",new JSONArray().put(new JSONObject().put("id","term1").put("name","Living room").put("can_receive",true)))
        .put("callbacks",requests);
  }
  @Test public void directionsPermissionsExpiryAndPersistence() throws Exception {
    JSONObject incoming=request(1),sent=request(2).put("from","phone1").put("to","term1");
    JSONObject c=config(new JSONArray().put(incoming).put(sent).put(request(3).put("status","completed"))
        .put(request(4).put("expires_at",Instant.ofEpochMilli(NOW-1).toString())).put(new JSONObject()));
    CallbackBook book=new CallbackBook("{}");
    CallbackBook.Plan plan=book.reconcile(c,NOW);
    assertEquals(1,plan.fresh().size());assertEquals("Living room",plan.fresh().get(0).name());
    assertEquals(1,book.reconcile(c,NOW).fresh().size()); // No delivery recorded while channel/permission prevents posting.
    book.posted(plan.fresh().get(0));book=new CallbackBook(book.toString());
    assertTrue(book.reconcile(c,NOW).fresh().isEmpty()); // User dismissal does not reset seen state.
    assertEquals(1,book.reconcile(c,NOW).retained().size());
    incoming.put("expires_at",Instant.ofEpochMilli(NOW+7200000).toString());
    assertTrue(book.reconcile(c,NOW+3600001).fresh().isEmpty());
    incoming.put("status","cancelled");
    assertEquals(java.util.List.of(id(1)),book.reconcile(c,NOW).removed());
    assertTrue(book.reconcile(c,NOW).fresh().isEmpty());
    incoming.put("status","pending");
    c.getJSONArray("contacts").getJSONObject(0).put("can_receive",false);
    assertTrue(new CallbackBook("{}").reconcile(c,NOW).fresh().isEmpty());
    c.put("callbacks_enabled",false);
    assertTrue(new CallbackBook("{}").reconcile(c,NOW).fresh().isEmpty());
  }
  @Test public void stateAndStorageAreBounded() throws Exception {
    JSONArray many=new JSONArray();for(int n=0;n<400;n++)many.put(request(n));
    CallbackBook book=new CallbackBook("{}");CallbackBook.Plan plan=book.reconcile(config(many),NOW);
    assertEquals(32,plan.fresh().size());for(var entry:plan.fresh())book.posted(entry);
    assertTrue(book.reconcile(config(many),NOW).fresh().isEmpty());
    for(int n=400;n<1000;n++) {
      book.reconcile(config(new JSONArray()),NOW);
      var entry=book.reconcile(config(new JSONArray().put(request(n))),NOW).fresh().get(0);book.posted(entry);
    }
    JSONObject saved=new JSONObject(book.toString());assertEquals(512,saved.getJSONObject("seen").length());
    assertEquals(1,saved.getJSONObject("active").length());
    assertEquals(1,new CallbackBook("invalid").reconcile(config(new JSONArray().put(request(1))),NOW).fresh().size());
    assertEquals(1,book.reconcile(config(new JSONArray()),NOW).removed().size());
    assertEquals(0,new JSONObject(book.toString()).getJSONObject("active").length());
  }
}
