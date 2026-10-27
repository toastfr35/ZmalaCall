package org.zmala.phone;

import java.time.Instant;
import java.util.*;
import org.json.*;

// @llr LLR-AND-HISTORY-003
/** Bounded notification history; dismissed requests stay seen until their deadline. */
final class CallbackBook {
  record Entry(String id, String peer, String name, long expires) {}
  record Plan(List<Entry> fresh, List<String> removed, List<Entry> retained) {}
  private JSONObject seen, active;

  CallbackBook(String saved) {
    try {
      JSONObject data = new JSONObject(saved);
      seen = data.getJSONObject("seen"); active = data.getJSONObject("active");
      if (seen.length() > 512 || active.length() > 32) throw new IllegalArgumentException();
    } catch (Exception ignored) { seen = new JSONObject(); active = new JSONObject(); }
  }

  Plan reconcile(JSONObject configuration, long now) {
    Map<String, Entry> valid = new LinkedHashMap<>();
    Map<String, JSONObject> contacts = new HashMap<>();
    JSONArray directory = configuration.optJSONArray("contacts");
    if (directory != null) for (int i = 0; i < directory.length(); i++) {
      JSONObject peer = directory.optJSONObject(i);
      if (peer != null && peer.optBoolean("can_receive")) contacts.put(peer.optString("id"), peer);
    }
    JSONObject sip = configuration.optJSONObject("sip");
    String self = sip == null ? "" : sip.optString("username");
    JSONArray requests = configuration.optJSONArray("callbacks");
    if (configuration.optBoolean("callbacks_enabled") && requests != null)
      for (int i = 0; i < Math.min(requests.length(), 400); i++) try {
        JSONObject request = requests.getJSONObject(i);
        String id = request.getString("id"), peer = request.getString("from");
        JSONObject contact = contacts.get(peer);
        long expires = Instant.parse(request.getString("expires_at")).toEpochMilli();
        if (contact != null && self.equals(request.optString("to"))
            && "pending".equals(request.optString("status")) && expires > now
            && id.matches("[a-f0-9-]{36}") && peer.matches("[a-z][a-z0-9_-]{0,30}"))
          valid.put(id, new Entry(id, peer, contact.optString("name", peer), expires));
      } catch (Exception ignored) { /* A malformed record cannot create an alert. */ }
    List<String> removed = new ArrayList<>(), expired = new ArrayList<>();
    active.keys().forEachRemaining(id -> { if (!valid.containsKey(id)) removed.add(id); });
    for (String id : removed) active.remove(id);
    // Settings may extend a pending deadline. Retain its seen state across that change.
    for (Entry entry : valid.values()) if (seen.has(entry.id())) try { seen.put(entry.id(),entry.expires()); }
      catch (JSONException error) { throw new IllegalArgumentException(error); }
    seen.keys().forEachRemaining(id -> { if (seen.optLong(id) <= now) expired.add(id); });
    for (String id : expired) seen.remove(id);
    List<Entry> fresh = new ArrayList<>();
    List<Entry> retained = new ArrayList<>();
    for (Entry entry : valid.values()) if (active.has(entry.id())) retained.add(entry);
    for (Entry entry : valid.values())
      if (!seen.has(entry.id()) && fresh.size() + active.length() < 32) fresh.add(entry);
    return new Plan(fresh, removed, retained);
  }

  void posted(Entry entry) {
    try {
      if (!seen.has(entry.id()) && seen.length() >= 512) {
        String oldest = null;
        for (Iterator<String> keys = seen.keys(); keys.hasNext();) {
          String key = keys.next();
          if (oldest == null || seen.optLong(key) < seen.optLong(oldest)) oldest = key;
        }
        if (oldest != null) seen.remove(oldest);
      }
      seen.put(entry.id(), entry.expires()); active.put(entry.id(), entry.peer());
    } catch (JSONException error) { throw new IllegalArgumentException(error); }
  }
  @Override public String toString() {
    try { return new JSONObject().put("seen", seen).put("active", active).toString(); }
    catch (JSONException error) { throw new IllegalArgumentException(error); }
  }
}
