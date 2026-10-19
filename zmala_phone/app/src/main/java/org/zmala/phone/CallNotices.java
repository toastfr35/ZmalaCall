package org.zmala.phone;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONArray;

// @llr LLR-AND-HISTORY-002
final class CallNotices {
  private static synchronized NoticeBook change(Context context, java.util.function.Consumer<NoticeBook> action) {
    Enrollment enrollment = PushAlerts.enrollment(context);
    String owner = enrollment == null ? "" : enrollment.server + "|" + enrollment.deviceId;
    SharedPreferences prefs = context.getSharedPreferences("call_notices", 0);
    NoticeBook book = new NoticeBook(owner.equals(prefs.getString("owner", "")) ? prefs.getString("book", "") : "");
    book.expire(System.currentTimeMillis());
    action.accept(book);
    prefs.edit().putString("owner", owner).putString("book", book.toString()).apply();
    return book;
  }
  static void ring(Context context, String id, String peer, long expires) { change(context, b -> b.ring(id, peer, expires)); }
  static void finish(Context context, String id, boolean missed) { change(context, b -> b.finish(id, missed)); }
  static void answered(Context context, String id, String peer) { change(context, b -> { b.finish(id, false); b.clear(peer); }); }
  static void clear(Context context, String peer) { change(context, b -> b.clear(peer)); }
  static NoticeBook snapshot(Context context, JSONArray contacts) { return change(context, b -> b.retain(contacts)); }
}
