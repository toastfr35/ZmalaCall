package org.zmala.phone;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

// @llr LLR-AND-UPDATE-002
/** Public update transport, deliberately independent of enrolled-server authentication. */
final class UpdateHttp {
  private UpdateHttp() {}

  // Keep connection creation injectable so redirect and resource ownership tests need no network.
  interface Opener {
    HttpURLConnection open(URI uri) throws IOException;
  }

  private static final Opener SYSTEM = uri -> (HttpURLConnection) uri.toURL().openConnection();

  static String metadata() throws IOException {
    return metadata(SYSTEM);
  }

  static String metadata(Opener opener) throws IOException {
    HttpURLConnection connection = connect(URI.create(UpdatePolicy.API), false, opener);
    try (InputStream in = connection.getInputStream();
        ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      byte[] buffer = new byte[8192];
      int count;
      while ((count = in.read(buffer)) != -1) {
        if (out.size() + count > 1048576) throw new IOException("Metadata limit");
        out.write(buffer, 0, count);
      }
      return out.toString(StandardCharsets.UTF_8.name());
    } finally {
      connection.disconnect();
    }
  }

  /** The caller owns the successful connection and must disconnect it after consuming its body. */
  static HttpURLConnection connect(URI start, boolean download) throws IOException {
    return connect(start, download, SYSTEM);
  }

  static HttpURLConnection connect(URI start, boolean download, Opener opener) throws IOException {
    URI uri = start;
    for (int hop = 0; hop < 6; hop++) {
      // Revalidate every hop before opening it; metadata must never redirect at all.
      if (download ? !UpdatePolicy.allowedDownload(uri) : !UpdatePolicy.API.equals(uri.toString()))
        throw new IOException("Untrusted update address");
      HttpURLConnection connection = opener.open(uri);
      boolean handedOff = false;
      try {
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(10000);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty("User-Agent", "ZmalaPhone-updater");
        connection.setRequestProperty("Accept", download ? "application/octet-stream" : "application/vnd.github+json");
        int code = connection.getResponseCode();
        if (code == 200) {
          handedOff = true;
          return connection;
        }
        String location = connection.getHeaderField("Location");
        if (!download || !Arrays.asList(301, 302, 303, 307, 308).contains(code) || location == null)
          throw new IOException("Update server unavailable");
        try {
          uri = uri.resolve(location);
        } catch (IllegalArgumentException error) {
          throw new IOException("Invalid update redirect", error);
        }
      } finally {
        if (!handedOff) connection.disconnect();
      }
    }
    throw new IOException("Too many redirects");
  }
}
