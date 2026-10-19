package org.zmala.phone;

import org.json.JSONArray;
import org.json.JSONObject;

// @llr LLR-AND-HISTORY-002
/** Bounded per-enrollment history, shared by native and push call observations. */
final class NoticeBook {
  private final JSONObject data;
  NoticeBook(String saved) {
    JSONObject value;
    try {
      value = new JSONObject(saved);
      JSONArray events = value.getJSONArray("events");
      if (events.length() > 128 || value.getJSONObject("missed").length() > 128) throw new IllegalArgumentException();
      for (int i = 0; i < events.length(); i++) {
        JSONObject event = events.getJSONObject(i);
        event.getString("id"); event.getString("peer"); event.getLong("expires"); event.getBoolean("done");
      }
    }
    catch (Exception error) { value = new JSONObject(); set(value, "events", new JSONArray()); set(value, "missed", new JSONObject()); }
    data = value;
  }
  private static void set(JSONObject target, String key, Object value) {
    try { target.put(key, value); } catch (Exception error) { throw new IllegalArgumentException(error); }
  }
  private JSONObject event(String id) {
    JSONArray events = data.optJSONArray("events");
    for (int i = 0; i < events.length(); i++) if (id.equals(events.optJSONObject(i).optString("id"))) return events.optJSONObject(i);
    return null;
  }
  void ring(String id, String peer, long expires) {
    if (id == null || id.length() > 256 || peer == null || !peer.matches("[a-z][a-z0-9_-]{0,30}") || event(id) != null) return;
    JSONArray events = data.optJSONArray("events");
    while (events.length() >= 128) events.remove(0);
    JSONObject event = new JSONObject();
    set(event, "id", id); set(event, "peer", peer); set(event, "expires", expires); set(event, "done", false);
    events.put(event);
  }
  void finish(String id, boolean missed) {
    JSONObject event = event(id);
    if (event == null || event.optBoolean("done")) return;
    set(event, "done", true);
    String peer = event.optString("peer");
    if (missed) {
      JSONObject counts = data.optJSONObject("missed");
      if (!counts.has(peer) && counts.length() >= 128) counts.remove(counts.keys().next());
      set(counts, peer, Math.min(99, count(peer) + 1));
    }
  }
  void expire(long now) {
    JSONArray events = data.optJSONArray("events");
    for (int i = 0; i < events.length(); i++) {
      JSONObject event = events.optJSONObject(i);
      if (event.optLong("expires") <= now) finish(event.optString("id"), true);
    }
  }
  int count(String peer) { return Math.max(0, Math.min(99, data.optJSONObject("missed").optInt(peer))); }
  void clear(String peer) { data.optJSONObject("missed").remove(peer); }
  void retain(JSONArray contacts) {
    java.util.Set<String> allowed = new java.util.HashSet<>();
    for (int i = 0; i < contacts.length(); i++) allowed.add(contacts.optJSONObject(i).optString("id"));
    java.util.List<String> remove = new java.util.ArrayList<>();
    data.optJSONObject("missed").keys().forEachRemaining(key -> { if (!allowed.contains(key)) remove.add(key); });
    for (String key : remove) clear(key);
  }
  static int callbacks(JSONArray entries, String self, String peer) {
    int flags = 0;
    if (entries != null) for (int i = 0; i < entries.length(); i++) {
      JSONObject entry = entries.optJSONObject(i);
      if (entry == null || !"pending".equals(entry.optString("status"))) continue;
      if (self.equals(entry.optString("to")) && peer.equals(entry.optString("from"))) flags |= 1;
      if (self.equals(entry.optString("from")) && peer.equals(entry.optString("to"))) flags |= 2;
    }
    return flags;
  }
  @Override public String toString() { return data.toString(); }
}
