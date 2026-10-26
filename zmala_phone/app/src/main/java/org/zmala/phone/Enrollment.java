package org.zmala.phone;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.json.JSONArray;
import org.json.JSONObject;

// @llr LLR-AND-ENROLL-002, LLR-AND-CALL-006
public final class Enrollment {
  public final URI server;
  public final String deviceId, token;
  private final String qr;

  public Enrollment(String text) throws Exception {
    if (text.length() > 8192) throw new IllegalArgumentException("QR code is too large.");
    JSONObject data = new JSONObject(text);
    if (!"family-call-server".equals(data.optString("type"))
        || data.optInt("version") != 1
        || !"app".equals(data.optString("account_type")))
      throw new IllegalArgumentException("Scan an App account QR code from ZmalaCall.");
    URI uri = new URI(data.getString("server_url"));
    if (!("https".equals(uri.getScheme()) || "http".equals(uri.getScheme()))
        || uri.getHost() == null
        || uri.getUserInfo() != null
        || uri.getQuery() != null
        || uri.getFragment() != null
        || !(uri.getPath().isEmpty() || uri.getPath().equals("/")))
      throw new IllegalArgumentException("Invalid server address.");
    deviceId = data.getString("device_id");
    token = data.getString("device_token");
    if (!deviceId.matches("ZP-[a-fA-F0-9-]{36}") || !token.matches("[A-Za-z0-9_-]{24,128}"))
      throw new IllegalArgumentException("Invalid app enrollment credentials.");
    server = uri.resolve("/");
    qr = text;
  }

  public String serialized() {
    return qr;
  }

  public JSONObject validate(JSONObject config) throws Exception {
    if (config.optInt("schema_version") != 1
        || !"app".equals(config.optString("account_type"))
        || !deviceId.equals(config.optString("device_id"))
        || !token.equals(config.optString("call_auth_key")))
      throw new IllegalArgumentException("The QR code does not match this app account.");
    JSONObject sip = config.getJSONObject("sip");
    if (!sip.getString("username").matches("[a-z][a-z0-9_-]{0,30}")
        || sip.getString("password").isEmpty()
        || sip.getString("domain").isEmpty()
        || !sip.getString("proxy").startsWith("sip:"))
      throw new IllegalArgumentException("Invalid calling configuration.");
    if (config.has("secure_calls") && !"https".equals(server.getScheme()))
      throw new IllegalArgumentException("Secure calls need a new HTTPS setup QR from your administrator.");
    SecureCalls.validate(config, System.currentTimeMillis() / 1000);
    JSONArray contacts = config.getJSONArray("contacts");
    if (contacts.length() > 40)
      throw new IllegalArgumentException("Too many contacts.");
    // Validate once at the API boundary: rendering and history reconciliation need real objects
    // with unique account IDs, rather than optJSONObject(null) failures on the UI thread.
    java.util.HashSet<String> ids = new java.util.HashSet<>();
    for (int i = 0; i < contacts.length(); i++) {
      JSONObject contact = contacts.getJSONObject(i);
      if (!(contact.get("id") instanceof String) || !(contact.get("name") instanceof String))
        throw new IllegalArgumentException("Invalid contact configuration.");
      String id = contact.getString("id");
      if (!id.matches("[a-z][a-z0-9_-]{0,30}") || !ids.add(id)
          || contact.getString("name").trim().isEmpty())
        throw new IllegalArgumentException("Invalid contact configuration.");
    }
    return config;
  }

  // @llr LLR-AND-CALL-002
  public static boolean allowedIncoming(
      JSONObject config, String user, String domain, String callId, String proof) {
    try {
      if (!config.getJSONObject("sip").getString("domain").equals(domain)
          || callId == null
          || proof == null) return false;
      JSONArray contacts = config.getJSONArray("contacts");
      boolean allowed = false;
      for (int i = 0; i < contacts.length(); i++) {
        JSONObject c = contacts.getJSONObject(i);
        if (user.equals(c.getString("id")) && c.optBoolean("can_receive")) allowed = true;
      }
      if (!allowed || !proof.matches("[a-f0-9]{64}")) return false;
      Mac mac = Mac.getInstance("HmacSHA256");
      mac.init(
          new SecretKeySpec(
              config.getString("call_auth_key").getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
      byte[] digest = mac.doFinal((callId + ":" + user).getBytes(StandardCharsets.UTF_8));
      StringBuilder expected = new StringBuilder();
      for (byte b : digest) expected.append(String.format("%02x", b & 255));
      return MessageDigest.isEqual(
          expected.toString().getBytes(StandardCharsets.US_ASCII),
          proof.getBytes(StandardCharsets.US_ASCII));
    } catch (Exception e) {
      return false;
    }
  }
}
