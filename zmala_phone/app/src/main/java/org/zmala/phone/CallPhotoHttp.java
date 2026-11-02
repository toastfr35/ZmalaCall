package org.zmala.phone;

import java.io.*;
import java.net.HttpURLConnection;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

// @llr LLR-AND-CALL-007
/** Authenticated live-call endpoint. Never follow redirects with enrollment credentials. */
final class CallPhotoHttp {
  static JSONObject request(Enrollment enrollment, String call, String method, long revision, byte[] bytes) throws Exception {
    return new JSONObject(new String(exchange(enrollment,call,method,revision,bytes,false),StandardCharsets.UTF_8));
  }
  static byte[] exchange(Enrollment enrollment, String call, String method, long revision, byte[] bytes, boolean image) throws Exception {
    String route = "/api/call/photo?call_id=" + URLEncoder.encode(call, StandardCharsets.UTF_8.name()) + "&revision=" + revision + (image ? "&image=1" : "");
    HttpURLConnection connection = (HttpURLConnection) enrollment.server.resolve(route).toURL().openConnection();
    HttpPolicy.configure(connection, 6000, 15000);
    connection.setRequestMethod(method);
    connection.setRequestProperty("Authorization", "Bearer " + enrollment.token);
    try {
      if (bytes != null) {
        if (bytes.length > 2097152) throw new IOException("Photo too large");
        connection.setDoOutput(true); connection.setRequestProperty("Content-Type", "image/jpeg");
        connection.setFixedLengthStreamingMode(bytes.length);
        try (OutputStream out = connection.getOutputStream()) { out.write(bytes); }
      }
      if (connection.getResponseCode() != 200) throw new IOException("Photo request failed");
      try (InputStream in = connection.getInputStream()) {
        return HttpPolicy.read(in, image ? 2097152 : 8192, "Response too large");
      }
    } finally { connection.disconnect(); }
  }
}
