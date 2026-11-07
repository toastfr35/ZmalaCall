// @test A-LLT-001
// @requirements LLR-AND-ENROLL-002
// @environment portable
// @plan Parse valid and malformed QR payloads and app configurations; reject terminal identity,
// credentials in URLs, mismatched account identity, unsupported secure mode and oversized input.
// Reject coerced versions, invalid ports, malformed contact names/URIs/permissions/photos and duplicates.
// Serve redirects from a local HTTP fixture and verify no credentials reach the redirect target.
// Download a GIF larger than the static cap, reject the same oversized JPEG and invalid photo paths.
// Test setup storage round trips, invalidation of old work and SDK-specific denied permission policy.
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
  @Test public void setupOwnerFencesWorkAndPersistsEnrollment() throws Exception {
    File file = File.createTempFile("zmala-setup", ".json");
    try {
      SetupCoordinator setup = new SetupCoordinator(file);
      int ticket = setup.ticket(); setup.fetching(true); setup.invalidate();
      assertFalse(setup.current(ticket)); assertFalse(setup.fetching());
      Enrollment enrollment = new Enrollment(qr().toString()); setup.remember(enrollment);
      assertEquals(enrollment.serialized(), setup.load().serialized());
      assertTrue(SetupCoordinator.granted(36, permission -> !permission.endsWith("ACCESS_LOCAL_NETWORK")));
      assertFalse(SetupCoordinator.granted(37, permission -> !permission.endsWith("ACCESS_LOCAL_NETWORK")));
      assertFalse(SetupCoordinator.granted(36, permission -> !permission.endsWith("CAMERA")));
    } finally { file.delete(); }
  }
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
          qr().put("version", "1"),
          qr().put("version", 1.5),
          qr().put("version", true),
          qr().put("device_token", "short"),
          qr().put("device_id", "ZM-terminal"),
          qr().put("server_url", "http://user:pass@localhost"),
          qr().put("server_url", "https://localhost/path"),
          qr().put("server_url", "file:///private"),
          qr().put("server_url", "http://localhost:0"),
          qr().put("server_url", "http://localhost:65536")
        }) assertThrows(Exception.class, () -> new Enrollment(bad.toString()));
    assertThrows(Exception.class, () -> new Enrollment("x".repeat(8193)));
    for (Object version : new Object[]{"1", 1.5, true, JSONObject.NULL})
      assertThrows(Exception.class, () -> e.validate(config().put("schema_version", version)));
    for (int port : new int[]{1, 65535})
      assertEquals(port, new Enrollment(qr().put("server_url", "http://localhost:" + port).toString()).server.getPort());
    assertThrows(Exception.class, () -> e.validate(config().put("device_id", "other")));
    assertThrows(Exception.class, () -> e.validate(config().put("call_auth_key", "other")));
    assertThrows(
        Exception.class,
        () -> e.validate(config().put("secure_calls", new JSONObject().put("mode", "tls-relay"))));
  }

  @Test
  public void malformedContactsAreRejectedBeforeRendering() throws Exception {
    Enrollment enrollment = new Enrollment(qr().toString());
    JSONObject contact = new JSONObject().put("id", "phone2").put("name", "Family member")
        .put("sip_uri", "sip:phone2@localhost").put("can_call", true).put("can_receive", false);
    enrollment.validate(config().put("contacts", new org.json.JSONArray().put(contact)));
    for (Object invalid : new Object[]{JSONObject.NULL, "not an object", new org.json.JSONArray(),
        new JSONObject(), new JSONObject(contact.toString()).put("id", "bad id"),
        new JSONObject(contact.toString()).put("name", "  "),
        new JSONObject(contact.toString()).put("name", JSONObject.NULL),
        new JSONObject(contact.toString()).put("name", 123),
        new JSONObject(contact.toString()).put("id", 123)}) {
      assertThrows(Exception.class, () -> enrollment.validate(
          config().put("contacts", new org.json.JSONArray().put(invalid))));
    }
    assertThrows(Exception.class, () -> enrollment.validate(config().put("contacts",
        new org.json.JSONArray().put(contact).put(contact))));
    for (String field : new String[]{"can_call", "can_receive"}) {
      for (Object value : new Object[]{"true", "false", 1, JSONObject.NULL}) {
        JSONObject invalid = new JSONObject(contact.toString()).put(field, value);
        assertThrows(Exception.class, () -> enrollment.validate(config().put("contacts",
            new org.json.JSONArray().put(invalid))));
      }
      JSONObject missing = new JSONObject(contact.toString()); missing.remove(field);
      assertThrows(Exception.class, () -> enrollment.validate(config().put("contacts",
          new org.json.JSONArray().put(missing))));
    }
    for (Object value : new Object[]{false, 0, JSONObject.NULL, new JSONObject(),
        new org.json.JSONArray(), "/photos/../private.png", "https://other.test/portrait.png"}) {
      JSONObject invalid = new JSONObject(contact.toString()).put("photo", value);
      assertThrows(Exception.class, () -> enrollment.validate(config().put("contacts",
          new org.json.JSONArray().put(invalid))));
    }
    for (JSONObject invalid : new JSONObject[]{
        new JSONObject(contact.toString()).put("name", "n".repeat(81)),
        new JSONObject(contact.toString()).put("sip_uri", "sip:phone2@other.test"),
        new JSONObject(contact.toString()).put("sip_uri", "sip:other@localhost")}) {
      assertThrows(Exception.class, () -> enrollment.validate(config().put("contacts",
          new org.json.JSONArray().put(invalid))));
    }
    for (String photo : new String[]{"", "/photos/abcd.png", "/photos/abcd.jpg", "/photos/abcd.gif"})
      enrollment.validate(config().put("contacts", new org.json.JSONArray().put(
          new JSONObject(contact.toString()).put("photo", photo).put("name", "n".repeat(80)))));
    org.json.JSONArray tooMany = new org.json.JSONArray();
    for (int i = 0; i < 41; i++) tooMany.put(new JSONObject(contact.toString()).put("id", "phone" + i).put("sip_uri", "sip:phone" + i + "@localhost"));
    assertThrows(Exception.class, () -> enrollment.validate(config().put("contacts", tooMany)));
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
  @Test
  public void gifPortraitsUseTheirOwnBoundWithoutChangingStaticLimits() throws Exception {
    for (String extension : new String[]{"gif", "jpg"}) {
      try (ServerSocket server = new ServerSocket(0, 10, java.net.InetAddress.getByName("127.0.0.1"))) {
        server.setSoTimeout(5000);
        Thread responder = new Thread(() -> {
          try (Socket socket = server.accept()) {
            BufferedReader reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            while (!reader.readLine().isEmpty()) {}
            int size = 2097153;
            OutputStream out = socket.getOutputStream();
            out.write(("HTTP/1.1 200 OK\r\nContent-Length: " + size + "\r\nConnection: close\r\n\r\n").getBytes());
            out.write(new byte[size]);
          } catch (Exception ignored) { /* Static-limit rejection may close the socket early. */ }
        });
        responder.start();
        Enrollment e = new Enrollment(qr().put("server_url", "http://127.0.0.1:" + server.getLocalPort()).toString());
        String path = "/photos/" + "a".repeat(64) + "." + extension;
        if (extension.equals("gif")) assertEquals(2097153, ServerApi.photo(e, path).length);
        else assertThrows(Exception.class, () -> ServerApi.photo(e, path));
        responder.join(6000); assertFalse(responder.isAlive());
        assertThrows(IllegalArgumentException.class, () -> ServerApi.photo(e, "/photos/../secret.gif"));
      }
    }
  }

}
