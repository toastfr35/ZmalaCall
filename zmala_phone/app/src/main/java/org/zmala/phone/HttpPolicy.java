package org.zmala.phone;

import java.io.*;
import java.net.HttpURLConnection;

// @llr LLR-AND-ENROLL-002, LLR-AND-CALL-007, LLR-AND-UPDATE-002
/** Shared mechanics only: callers retain credentials, URL trust and error policy. */
final class HttpPolicy {
  static final class LimitExceeded extends IOException {
    LimitExceeded(String message) { super(message); }
  }
  static void configure(HttpURLConnection connection, int connect, int read) {
    connection.setConnectTimeout(connect); connection.setReadTimeout(read);
    connection.setInstanceFollowRedirects(false);
  }
  static byte[] read(InputStream in, int limit, String error) throws IOException {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    byte[] buffer = new byte[8192];
    while (true) {
      if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Request cancelled");
      int size = in.read(buffer);
      if (size == -1) return out.toByteArray();
      if (size > limit - out.size()) throw new LimitExceeded(error);
      out.write(buffer,0,size);
    }
  }
}
