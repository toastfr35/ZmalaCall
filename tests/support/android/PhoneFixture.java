package org.zmala.phone;

import static org.junit.Assert.*;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.BooleanSupplier;
import org.json.*;

public final class PhoneFixture {
  public static final String TOKEN = "abcdefghijklmnopqrstuvwx",
      ID = "ZP-12345678-1234-1234-1234-123456789abc";
  public static final Instrumentation INSTRUMENTATION =
      InstrumentationRegistry.getInstrumentation();

  public static JSONObject config(int sipPort) throws Exception {
    return new JSONObject()
        .put("schema_version", 1)
        .put("configuration_version", 1)
        .put("account_type", "app")
        .put("device_id", ID)
        .put("call_auth_key", TOKEN)
        .put("display_name", "Test phone")
        .put(
            "sip",
            new JSONObject()
                .put("username", "phone1")
                .put("password", "test-password")
                .put("domain", "127.0.0.1")
                .put("proxy", "sip:127.0.0.1:" + sipPort + ";transport=udp"))
        .put(
            "contacts",
            new JSONArray()
                .put(
                    new JSONObject()
                        .put("id", "term1")
                        .put("name", "Living room")
                        .put("photo", "")
                        .put("can_call", true)
                        .put("can_receive", true)
                        .put("online", true)));
  }

  public static String qr(int port, String type) throws Exception {
    return new JSONObject()
        .put("type", "family-call-server")
        .put("version", 1)
        .put("account_type", type)
        .put("server_url", "http://127.0.0.1:" + port)
        .put("device_id", ID)
        .put("device_token", TOKEN)
        .toString();
  }

  public static void waitFor(BooleanSupplier condition) throws Exception {
    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(12);
    while (!condition.getAsBoolean() && System.nanoTime() < deadline) Thread.sleep(50);
    assertTrue("Timed out waiting for fixture condition", condition.getAsBoolean());
  }

  public static TextView text(View root, String target) {
    if (root instanceof TextView && ((TextView) root).getText().toString().equals(target))
      return (TextView) root;
    if (root instanceof ViewGroup)
      for (int i = 0; i < ((ViewGroup) root).getChildCount(); i++) {
        TextView found = text(((ViewGroup) root).getChildAt(i), target);
        if (found != null) return found;
      }
    return null;
  }

  public static void click(Activity activity, String label) {
    INSTRUMENTATION.runOnMainSync(
        () -> {
          View view = text(activity.getWindow().getDecorView(), label);
          if (view == null) view = description(activity.getWindow().getDecorView(), label);
          assertNotNull(label, view);
          assertTrue("Control must be visible: " + label, view.isShown());
          assertTrue(view.performClick());
        });
  }

  public static void scan(MainActivity activity, String qr) {
    INSTRUMENTATION.runOnMainSync(
        () -> {
          Intent result =
              new Intent().putExtra("SCAN_RESULT", qr).putExtra("SCAN_RESULT_FORMAT", "QR_CODE");
          activity.onActivityResult(49374, Activity.RESULT_OK, result);
        });
  }

  public static View description(View root, String label) {
    if (label.contentEquals(
        root.getContentDescription() == null ? "" : root.getContentDescription())) return root;
    if (root instanceof ViewGroup)
      for (int i = 0; i < ((ViewGroup) root).getChildCount(); i++) {
        View found = description(((ViewGroup) root).getChildAt(i), label);
        if (found != null) return found;
      }
    return null;
  }

  public static boolean hasDescription(Activity screen, String label) {
    java.util.concurrent.atomic.AtomicBoolean present =
        new java.util.concurrent.atomic.AtomicBoolean();
    INSTRUMENTATION.runOnMainSync(
        () -> {
          View view = description(screen.getWindow().getDecorView(), label);
          present.set(view != null && view.isShown());
        });
    return present.get();
  }

  public static void dialog(String button) {
    androidx.test.espresso.Espresso.onView(
            androidx.test.espresso.matcher.ViewMatchers.withText(button))
        .inRoot(androidx.test.espresso.matcher.RootMatchers.isDialog())
        .perform(
            new androidx.test.espresso.ViewAction() {
              public org.hamcrest.Matcher<View> getConstraints() {
                return androidx.test.espresso.matcher.ViewMatchers.isDisplayed();
              }

              public String getDescription() {
                return "Activate the visible dialog action";
              }

              public void perform(androidx.test.espresso.UiController controller, View view) {
                assertTrue(view.performClick());
                controller.loopMainThreadUntilIdle();
              }
            });
  }

  public static boolean hasText(Activity screen, String label) {
    java.util.concurrent.atomic.AtomicBoolean present =
        new java.util.concurrent.atomic.AtomicBoolean();
    INSTRUMENTATION.runOnMainSync(
        () -> present.set(text(screen.getWindow().getDecorView(), label) != null));
    return present.get();
  }

  public static boolean enabledText(Activity screen, String label) {
    java.util.concurrent.atomic.AtomicBoolean enabled =
        new java.util.concurrent.atomic.AtomicBoolean();
    INSTRUMENTATION.runOnMainSync(
        () -> {
          View view = text(screen.getWindow().getDecorView(), label);
          enabled.set(view != null && view.isShown() && view.isEnabled());
        });
    return enabled.get();
  }

  public static String proof(String callId) throws Exception {
    javax.crypto.Mac mac = javax.crypto.Mac.getInstance("HmacSHA256");
    mac.init(
        new javax.crypto.spec.SecretKeySpec(TOKEN.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
    StringBuilder value = new StringBuilder();
    for (byte b : mac.doFinal((callId + ":term1").getBytes(StandardCharsets.UTF_8)))
      value.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
    return value.toString();
  }

  public static void snapshot(String name) throws Exception {
    // Allow window dismissal animations and the compositor to display the asserted UI state.
    INSTRUMENTATION.waitForIdleSync();
    android.os.SystemClock.sleep(400);
    android.graphics.Bitmap bitmap = INSTRUMENTATION.getUiAutomation().takeScreenshot();
    if (bitmap != null)
      try (java.io.FileOutputStream out =
          new java.io.FileOutputStream(
              new java.io.File(
                  INSTRUMENTATION.getTargetContext().getExternalFilesDir(null), name + ".png"))) {
        bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, out);
      }
  }

  public static class Http implements AutoCloseable {
    public final ServerSocket server;
    public volatile boolean authorized;
    public volatile String lastRequest = "", lastBody = "";
    public volatile int callbackRequests;
    public volatile String callbackRecipient;
    private final Thread thread;

    public Http(JSONObject config) throws Exception {
      server = new ServerSocket(0, 10, InetAddress.getByName("127.0.0.1"));
      thread =
          new Thread(
              () -> {
                while (!server.isClosed())
                  try (Socket socket = server.accept()) {
                    BufferedReader reader =
                        new BufferedReader(new InputStreamReader(socket.getInputStream()));
                    String line;
                    StringBuilder request = new StringBuilder();
                    while ((line = reader.readLine()) != null && !line.isEmpty())
                      request.append(line).append("\n");
                    authorized = request.toString().contains("Bearer " + TOKEN);
                    int length = 0;
                    for (String header : request.toString().split("\n"))
                      if (header.toLowerCase(java.util.Locale.ROOT).startsWith("content-length:"))
                        length = Integer.parseInt(header.substring(15).trim());
                    char[] received = new char[length];
                    int offset = 0;
                    while (offset < length) {
                      int count = reader.read(received, offset, length - offset);
                      if (count < 0) break;
                      offset += count;
                    }
                    lastBody = new String(received, 0, offset);
                    lastRequest = request.toString();
                    if (lastRequest.startsWith("POST /api/app/callbacks ")) {
                      callbackRecipient = new JSONObject(lastBody).getString("to");
                      callbackRequests++;
                    }
                    byte[] body = config.toString().getBytes(StandardCharsets.UTF_8);
                    socket
                        .getOutputStream()
                        .write(
                            ("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                                    + body.length
                                    + "\r\nConnection: close\r\n\r\n")
                                .getBytes(StandardCharsets.US_ASCII));
                    socket.getOutputStream().write(body);
                  } catch (Exception ignored) {
                  }
              });
      thread.start();
    }

    public int port() {
      return server.getLocalPort();
    }

    public void close() throws Exception {
      server.close();
      thread.join(2000);
    }
  }

  public static class Sip implements AutoCloseable {
    public final DatagramSocket socket;
    public final BlockingQueue<String> invites = new LinkedBlockingQueue<>();
    public final BlockingQueue<String> responses = new LinkedBlockingQueue<>();
    public volatile boolean authenticated, unregistered, ringOutgoing;
    public volatile SocketAddress client;
    private final Thread thread;

    public Sip() throws Exception {
      socket = new DatagramSocket(0, InetAddress.getByName("127.0.0.1"));
      thread =
          new Thread(
              () -> {
                while (!socket.isClosed())
                  try {
                    byte[] bytes = new byte[65535];
                    DatagramPacket packet = new DatagramPacket(bytes, bytes.length);
                    socket.receive(packet);
                    String request =
                        new String(bytes, 0, packet.getLength(), StandardCharsets.UTF_8);
                    client = packet.getSocketAddress();
                    if (request.startsWith("SIP/2.0 ")) {
                      responses.add(request);
                    } else if (request.startsWith("REGISTER ")) {
                      authenticated |= request.contains("Authorization:");
                      unregistered |=
                          request.contains("expires=0") || request.contains("Expires: 0");
                      String extra =
                          authenticated
                              ? "Contact: " + header(request, "Contact") + "\r\nExpires: 60\r\n"
                              : "WWW-Authenticate: Digest"
                                    + " realm=\"127.0.0.1\",nonce=\"fixture-nonce\",algorithm=MD5,qop=\"auth\"\r\n";
                      respond(request, authenticated ? 200 : 401, extra);
                    } else if (request.startsWith("INVITE ")) {
                      invites.add(request);
                      respond(request, ringOutgoing ? 180 : 486, "");
                    } else if (request.startsWith("BYE ") || request.startsWith("CANCEL "))
                      respond(request, 200, "");
                  } catch (Exception ignored) {
                  }
              });
      thread.start();
    }

    public int port() {
      return socket.getLocalPort();
    }

    public static String header(String request, String name) {
      for (String line : request.split("\r\n"))
        if (line.regionMatches(true, 0, name + ":", 0, name.length() + 1))
          return line.substring(name.length() + 1).trim();
      return "";
    }

    public void respond(String request, int code, String extra) throws Exception {
      send(
          "SIP/2.0 "
              + code
              + " "
              + (code == 200
                  ? "OK"
                  : code == 401 ? "Unauthorized" : code == 180 ? "Ringing" : "Busy Here")
              + "\r\nVia: "
              + header(request, "Via")
              + "\r\nFrom: "
              + header(request, "From")
              + "\r\nTo: "
              + header(request, "To")
              + ";tag=fixture\r\nCall-ID: "
              + header(request, "Call-ID")
              + "\r\nCSeq: "
              + header(request, "CSeq")
              + "\r\n"
              + extra
              + "Content-Length: 0\r\n\r\n");
    }

    public void send(String text) throws Exception {
      byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
      socket.send(new DatagramPacket(bytes, bytes.length, client));
    }

    public void incoming(String callId, String proof) throws Exception {
      String sdp =
          "v=0\r\n"
              + "o=- 1 1 IN IP4 127.0.0.1\r\n"
              + "s=fixture\r\n"
              + "c=IN IP4 127.0.0.1\r\n"
              + "t=0 0\r\n"
              + "m=audio 41000 RTP/AVP 0\r\n"
              + "a=rtpmap:0 PCMU/8000\r\n"
              + "m=video 41002 RTP/AVP 96\r\n"
              + "a=rtpmap:96 VP8/90000\r\n";
      send(
          "INVITE sip:phone1@127.0.0.1 SIP/2.0\r\nVia: SIP/2.0/UDP 127.0.0.1:"
              + port()
              + ";branch=z9hG4bK-"
              + callId
              + ";rport\r\n"
              + "From: <sip:term1@127.0.0.1>;tag=caller\r\n"
              + "To: <sip:phone1@127.0.0.1>\r\n"
              + "Call-ID: "
              + callId
              + "\r\nCSeq: 1 INVITE\r\nContact: <sip:term1@127.0.0.1:"
              + port()
              + ">\r\nMax-Forwards: 70\r\nX-Family-Auth: "
              + proof
              + "\r\nContent-Type: application/sdp\r\nContent-Length: "
              + sdp.length()
              + "\r\n\r\n"
              + sdp);
    }

    public void close() throws Exception {
      socket.close();
      thread.join(2000);
    }
  }
}
