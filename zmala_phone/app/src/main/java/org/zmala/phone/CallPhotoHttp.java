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
    String route = "/api/call/photo?call_id=" + URLEncoder.encode(call, StandardCharsets.UTF_8.name()) + "&revision=" + revision;
    HttpURLConnection connection = (HttpURLConnection) enrollment.server.resolve(route).toURL().openConnection();
    connection.setConnectTimeout(6000); connection.setReadTimeout(15000);
    connection.setInstanceFollowRedirects(false);
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
      try (InputStream in = connection.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
        byte[] buffer = new byte[1024]; int n;
        while ((n = in.read(buffer)) != -1) {
          if (out.size()+n > 8192) throw new IOException("Response too large");
          out.write(buffer, 0, n);
        }
        return new JSONObject(out.toString(StandardCharsets.UTF_8.name()));
      }
    } finally { connection.disconnect(); }
  }
}
