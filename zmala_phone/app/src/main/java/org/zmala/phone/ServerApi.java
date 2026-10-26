package org.zmala.phone;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

// @llr LLR-AND-ENROLL-002
public final class ServerApi {
  static final class AccessRevoked extends IllegalStateException {
    AccessRevoked() { super("Account access was revoked. Scan a current App QR code."); }
  }

  // @llr LLR-AND-CALL-006
  static boolean temporaryFailure(Exception error) { return error instanceof java.io.IOException; }
  public static JSONObject configuration(Enrollment enrollment) throws Exception {
    return enrollment.validate(
        new JSONObject(
            new String(get(enrollment, "/api/app/config", 262144), StandardCharsets.UTF_8)));
  }

  public static byte[] photo(Enrollment enrollment, String path) throws Exception {
    if (!path.matches("/photos/[a-f0-9]+\\.(png|jpg)"))
      throw new IllegalArgumentException("Invalid photo.");
    return get(enrollment, path, 2097152);
  }

  private static byte[] get(Enrollment enrollment, String path, int limit) throws Exception {
    return request(enrollment, path, limit, null);
  }

  // @llr LLR-AND-HISTORY-002
  static void requestCallback(Enrollment enrollment, String peer) throws Exception {
    if (!peer.matches("[a-z][a-z0-9_-]{0,30}")) throw new IllegalArgumentException("Invalid contact.");
    request(enrollment, "/api/app/callbacks", 16384, new JSONObject().put("to", peer));
  }

  // @llr LLR-AND-HISTORY-002
  static void cancelCallback(Enrollment enrollment, String id) throws Exception {
    if (!id.matches("[a-f0-9-]{36}")) throw new IllegalArgumentException("Invalid callback request.");
    request(enrollment, "/api/app/callbacks/" + id, 16384, null, "DELETE");
  }

  // @llr LLR-AND-CALL-004
  public static JSONObject push(Enrollment enrollment, String path, JSONObject body)
      throws Exception {
    if (!path.equals("/api/app/push") && !path.equals("/api/app/call/decline"))
      throw new IllegalArgumentException("Invalid push action.");
    return new JSONObject(
        new String(request(enrollment, path, 8192, body), StandardCharsets.UTF_8));
  }

  private static byte[] request(Enrollment enrollment, String path, int limit, JSONObject body)
      throws Exception {
    return request(enrollment, path, limit, body, body == null ? "GET" : "POST");
  }

  private static byte[] request(Enrollment enrollment, String path, int limit, JSONObject body, String method)
      throws Exception {
    HttpURLConnection connection =
        (HttpURLConnection) enrollment.server.resolve(path).toURL().openConnection();
    connection.setConnectTimeout(6000);
    connection.setReadTimeout(6000);
    connection.setInstanceFollowRedirects(false);
    connection.setRequestProperty("Authorization", "Bearer " + enrollment.token);
    try {
      connection.setRequestMethod(method);
      if (body != null) {
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json");
        byte[] payload = body.toString().getBytes(StandardCharsets.UTF_8);
        connection.setFixedLengthStreamingMode(payload.length);
        try (java.io.OutputStream output = connection.getOutputStream()) {
          output.write(payload);
        }
      }
      int status = connection.getResponseCode();
      if (status == 401 || status == 403) throw new AccessRevoked();
      if (status != 200) throw new java.io.IOException("Server is unavailable (" + status + ").");
      try (InputStream stream = connection.getInputStream();
          ByteArrayOutputStream output = new ByteArrayOutputStream()) {
        byte[] buffer = new byte[8192];
        int size;
        while ((size = stream.read(buffer)) != -1) {
          if (output.size() + size > limit)
            throw new IllegalStateException("Server response is too large.");
          output.write(buffer, 0, size);
        }
        return output.toByteArray();
      }
    } finally {
      connection.disconnect();
    }
  }
}
