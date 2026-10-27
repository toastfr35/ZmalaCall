// @test A-LLT-018
// @requirements LLR-AND-UPDATE-002
// @environment portable
// @plan Use fake HTTP connections to check fixed metadata origin, per-hop APK redirect validation,
// redirect limits, request headers/timeouts, bounded metadata and resource cleanup on success/error.
// @pass No untrusted hop opens, metadata never redirects, only public headers are sent, metadata
// stops above 1 MiB and every rejected or consumed connection is disconnected with streams closed.
package org.zmala.phone;

import static org.junit.Assert.*;

import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.Test;

public class UpdateHttpTest {
  static class Connection extends HttpURLConnection {
    int status = 200;
    String location;
    boolean disconnected, closed, failStatus, failRead;
    byte[] body = "{}".getBytes(java.nio.charset.StandardCharsets.UTF_8);

    Connection() throws Exception { super(new URL(UpdatePolicy.API)); }
    @Override public void connect() {}
    @Override public void disconnect() { disconnected = true; }
    @Override public boolean usingProxy() { return false; }
    @Override public int getResponseCode() throws IOException {
      if (failStatus) throw new IOException("Status failed");
      return status;
    }
    @Override public String getHeaderField(String name) { return location; }
    @Override public InputStream getInputStream() {
      return new FilterInputStream(new ByteArrayInputStream(body)) {
        @Override public int read(byte[] data, int offset, int length) throws IOException {
          if (failRead) throw new IOException("Read failed");
          return super.read(data, offset, length);
        }
        @Override public void close() { closed = true; }
      };
    }
  }

  @Test public void publicMetadataHasLimitsAndAlwaysReleasesResources() throws Exception {
    Connection ok = new Connection();
    assertEquals("{}", UpdateHttp.metadata(uri -> {
      assertEquals(UpdatePolicy.API, uri.toString());
      return ok;
    }));
    assertEquals(10000, ok.getConnectTimeout());
    assertEquals(10000, ok.getReadTimeout());
    assertFalse(ok.getInstanceFollowRedirects());
    assertEquals(Map.of("User-Agent", List.of("ZmalaPhone-updater"),
        "Accept", List.of("application/vnd.github+json")), ok.getRequestProperties());
    assertTrue(ok.closed && ok.disconnected);

    Connection exact = new Connection();
    exact.body = new byte[1048576];
    assertEquals(1048576, UpdateHttp.metadata(uri -> exact).length());
    Connection oversized = new Connection();
    oversized.body = new byte[1048577];
    assertThrows(IOException.class, () -> UpdateHttp.metadata(uri -> oversized));
    assertTrue(oversized.closed && oversized.disconnected);
    Connection readFailure = new Connection();
    readFailure.failRead = true;
    assertThrows(IOException.class, () -> UpdateHttp.metadata(uri -> readFailure));
    assertTrue(readFailure.closed && readFailure.disconnected);
    Connection statusFailure = new Connection();
    statusFailure.failStatus = true;
    assertThrows(IOException.class, () -> UpdateHttp.metadata(uri -> statusFailure));
    assertTrue(statusFailure.disconnected);
  }

  @Test public void redirectsAreCheckedBeforeEachConnectionAndHaveABudget() throws Exception {
    URI asset = URI.create(UpdatePolicy.DOWNLOAD + "v0.3.8/ZmalaPhone.apk");
    Connection redirectedMetadata = new Connection();
    redirectedMetadata.status = 302;
    redirectedMetadata.location = UpdatePolicy.API;
    AtomicInteger opens = new AtomicInteger();
    assertThrows(IOException.class, () -> UpdateHttp.metadata(uri -> {
      opens.incrementAndGet();
      return redirectedMetadata;
    }));
    assertEquals(1, opens.get());
    assertTrue(redirectedMetadata.disconnected);

    for (String location : List.of("https://attacker.test/apk", "http://github.com/file",
        "https://token@github.com/file", "https://github.com:444/file", "http://[bad")) {
      Connection denied = new Connection();
      denied.status = 307;
      denied.location = location;
      opens.set(0);
      assertThrows(IOException.class, () -> UpdateHttp.connect(asset, true, uri -> {
        opens.incrementAndGet();
        return denied;
      }));
      assertEquals(1, opens.get());
      assertTrue(denied.disconnected);
    }
    opens.set(0);
    assertThrows(IOException.class, () -> UpdateHttp.connect(URI.create("https://attacker.test/"), true, uri -> {
      opens.incrementAndGet();
      throw new AssertionError("Untrusted connection opened");
    }));
    assertEquals(0, opens.get());

    List<Connection> loop = new ArrayList<>();
    for (int i = 0; i < 6; i++) {
      Connection hop = new Connection();
      hop.status = 308;
      hop.location = "/again";
      loop.add(hop);
    }
    opens.set(0);
    assertThrows(IOException.class, () -> UpdateHttp.connect(asset, true, uri -> loop.get(opens.getAndIncrement())));
    assertEquals(6, opens.get());
    assertTrue(loop.stream().allMatch(c -> c.disconnected));
  }

  @Test public void acceptedAssetConnectionIsOwnedByTheDownloader() throws Exception {
    URI asset = URI.create(UpdatePolicy.DOWNLOAD + "v0.3.8/ZmalaPhone.apk");
    URI destination = URI.create("https://release-assets.githubusercontent.com/file?signature=public");
    Connection redirect = new Connection(), download = new Connection();
    redirect.status = 302;
    redirect.location = destination.toString();
    List<URI> visited = new ArrayList<>();
    assertSame(download, UpdateHttp.connect(asset, true, uri -> {
      visited.add(uri);
      return visited.size() == 1 ? redirect : download;
    }));
    assertEquals(List.of(asset, destination), visited);
    assertTrue(redirect.disconnected);
    assertFalse(download.disconnected);
    assertEquals("application/octet-stream", download.getRequestProperty("Accept"));
    download.disconnect();
  }
}
