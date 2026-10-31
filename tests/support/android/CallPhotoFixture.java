package org.zmala.phone;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

/** Binary-safe disposable HTTP peer for call-photo tests; never talks to a family server. */
public final class CallPhotoFixture implements AutoCloseable {
  private final ServerSocket server = new ServerSocket(0);
  private final Thread thread;
  public volatile boolean sharing, failPhotoRequests;
  public volatile long remaining=12000;
  public volatile byte[] photo;
  public volatile int revision, renewals;
  public CallPhotoFixture(JSONObject config) throws IOException {
    thread = new Thread(() -> {
      while (!server.isClosed()) {
        try (Socket socket = server.accept()) {
          socket.setSoTimeout(5000);
          InputStream input = socket.getInputStream();
          String request = line(input), header;
          int length = 0;
          while (!(header = line(input)).isEmpty())
            if (header.toLowerCase(java.util.Locale.ROOT).startsWith("content-length:"))
              length = Integer.parseInt(header.substring(15).trim());
          byte[] body = input.readNBytes(length);
          JSONObject response = config;
          if (request.contains(" /api/call/photo?")) {
            if (failPhotoRequests) continue;
            if (request.startsWith("PUT ")) { photo = body; revision++; sharing = true; }
            if (request.startsWith("DELETE ")) { photo = null; revision++; sharing = false; }
            if (request.startsWith("POST ")) renewals++;
            response = new JSONObject().put("revision", revision).put("sharing", sharing)
                .put("lease_ms", 12000).put("remaining_ms", remaining);
          }
          byte[] bytes = request.contains("&image=1") && photo != null ? photo : response.toString().getBytes(StandardCharsets.UTF_8);
          socket.getOutputStream().write(("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
              + bytes.length + "\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
          socket.getOutputStream().write(bytes);
        } catch (Exception ignored) { }
      }
    }, "photo-fixture");
    thread.start();
  }
  private static String line(InputStream input) throws IOException {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    for (int c; (c = input.read()) != '\n';) {
      if (c < 0 || out.size() > 16384) throw new IOException("Incomplete fixture request");
      if (c != '\r') out.write(c);
    }
    return out.toString(StandardCharsets.US_ASCII);
  }
  public int port() { return server.getLocalPort(); }
  public void close() throws Exception { server.close(); thread.join(2000); }
}
