// @test A-LLT-001
// @requirements LLR-AND-ENROLL-002
// @environment portable
// @plan Parse valid and malformed QR payloads and app configurations; reject terminal identity,
// credentials in URLs, mismatched account identity, unsupported secure mode and oversized input.
// Serve redirects from a local HTTP fixture and verify no credentials reach the redirect target.
// @pass All parser, identity, transport and redirect boundary assertions pass.
package org.zmala.phone;

import static org.junit.Assert.*;

import java.io.*;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONObject;
import org.junit.Test;

public class EnrollmentTest {
  static final String TOKEN = "abcdefghijklmnopqrstuvwx";

  static JSONObject qr() throws Exception {
    return new JSONObject()
        .put("type", "family-call-server")
        .put("version", 1)
        .put("account_type", "app")
        .put("server_url", "http://127.0.0.1:8080")
        .put("device_id", "ZP-12345678-1234-1234-1234-123456789abc")
        .put("device_token", TOKEN);
  }

  static JSONObject config() throws Exception {
    return new JSONObject()
        .put("schema_version", 1)
        .put("account_type", "app")
        .put("device_id", qr().getString("device_id"))
        .put("call_auth_key", TOKEN)
        .put(
            "sip",
            new JSONObject()
                .put("username", "phone1")
                .put("password", "secret")
                .put("domain", "localhost")
                .put("proxy", "sip:localhost:5060;transport=udp"))
        .put("contacts", new org.json.JSONArray());
  }

  @Test
  public void qrAndIdentityBoundaries() throws Exception {
    Enrollment e = new Enrollment(qr().toString());
    assertEquals("127.0.0.1", e.server.getHost());
    assertEquals(TOKEN, e.token);
    e.validate(config());
    for (JSONObject bad :
        new JSONObject[] {
          qr().put("account_type", "terminal"),
          qr().put("version", 2),
          qr().put("device_token", "short"),
          qr().put("device_id", "ZM-terminal"),
          qr().put("server_url", "http://user:pass@localhost"),
          qr().put("server_url", "https://localhost/path"),
          qr().put("server_url", "file:///private")
        }) assertThrows(Exception.class, () -> new Enrollment(bad.toString()));
    assertThrows(Exception.class, () -> new Enrollment("x".repeat(8193)));
    assertThrows(Exception.class, () -> e.validate(config().put("device_id", "other")));
    assertThrows(Exception.class, () -> e.validate(config().put("call_auth_key", "other")));
    assertThrows(
        Exception.class,
        () -> e.validate(config().put("secure_calls", new JSONObject().put("mode", "tls-relay"))));
  }

  @Test
  public void redirectsAreNeverFollowedAndErrorsDoNotLeakTokens() throws Exception {
    try (ServerSocket server =
        new ServerSocket(0, 10, java.net.InetAddress.getByName("127.0.0.1"))) {
      server.setSoTimeout(1000);
      AtomicBoolean leaked = new AtomicBoolean();
      Thread responder =
          new Thread(
              () -> {
                try (Socket socket = server.accept()) {
                  BufferedReader input =
                      new BufferedReader(new InputStreamReader(socket.getInputStream()));
                  String line;
                  StringBuilder headers = new StringBuilder();
                  while ((line = input.readLine()) != null && !line.isEmpty())
                    headers.append(line).append("\n");
                  if (!headers.toString().contains("Bearer " + TOKEN)) leaked.set(true);
                  socket
                      .getOutputStream()
                      .write(
                          "HTTP/1.1 302 Found\r\nLocation: /leak\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                              .getBytes());
                } catch (Exception ignored) {
                  leaked.set(true);
                }
                try (Socket unexpected = server.accept()) {
                  leaked.set(true);
                } catch (Exception expected) {
                }
              });
      responder.start();
      Enrollment e =
          new Enrollment(
              qr().put("server_url", "http://127.0.0.1:" + server.getLocalPort()).toString());
      Exception failure = assertThrows(Exception.class, () -> ServerApi.configuration(e));
      assertFalse(failure.getMessage().contains(TOKEN));
      responder.join(3000);
      assertFalse(leaked.get());
    }
  }
}
