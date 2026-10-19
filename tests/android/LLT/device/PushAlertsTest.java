// @test A-LLT-008
// @requirements LLR-AND-CALL-004
// @environment native-sdk
// @plan On a disposable emulator with notification permission and full-screen intents disabled, persist a fixture enrollment, deliver signed data messages without an activity, inspect native call actions and timeout, then test duplicate, forged, expired and cancel-before-ring messages. Use a local HTTP fixture to verify bearer token registration, rejection of unapproved paths, disabled-sender retries and explicit token removal.
// @pass The alert offers Answer/Decline with the cached caller name, expires automatically and cannot reappear after cancellation. This exercises the FCM callback path, not Google's transport.
package org.zmala.phone;

import static org.junit.Assert.*;

import android.app.*;
import android.content.*;
import androidx.test.rule.GrantPermissionRule;
import java.io.File;
import java.util.*;
import org.junit.*;

public class PushAlertsTest {
  @Rule
  public GrantPermissionRule permission =
      GrantPermissionRule.grant(android.Manifest.permission.POST_NOTIFICATIONS);

  @Test
  public void registrationTracksPermissionAndSenderReadiness() throws Exception {
    Context c = PhoneFixture.INSTRUMENTATION.getTargetContext();
    org.json.JSONObject config = PhoneFixture.config(5060).put("push_enabled", false);
    try (PhoneFixture.Http http = new PhoneFixture.Http(config)) {
      Enrollment enrollment = new Enrollment(PhoneFixture.qr(http.port(), "app"));
      java.util.concurrent.BlockingQueue<Boolean> results =
          new java.util.concurrent.LinkedBlockingQueue<>();
      for (int attempt = 0; attempt < 2; attempt++) {
        PushAlerts.upload(c, enrollment, "fixture-token-123456789012", results::add);
        assertEquals(Boolean.FALSE, results.poll(10, java.util.concurrent.TimeUnit.SECONDS));
      }
      assertTrue(http.authorized);
      assertTrue(http.lastRequest.startsWith("POST /api/app/push"));
      assertTrue(http.lastBody.contains("fixture-token-123456789012"));
      config.put("push_enabled", true);
      PushAlerts.upload(c, enrollment, "fixture-token-123456789012", results::add);
      assertEquals(Boolean.TRUE, results.poll(10, java.util.concurrent.TimeUnit.SECONDS));
      PushAlerts.upload(c, enrollment, null, results::add);
      assertEquals(Boolean.FALSE, results.poll(10, java.util.concurrent.TimeUnit.SECONDS));
      assertTrue(new org.json.JSONObject(http.lastBody).isNull("token"));
      try {
        ServerApi.push(enrollment, "/api/admin", new org.json.JSONObject());
        fail("Unapproved endpoint accepted");
      } catch (IllegalArgumentException expected) {
        assertEquals("Invalid push action.", expected.getMessage());
      }
    }
  }

  @Test
  public void notificationsAuthenticateExpireAndCancel() throws Exception {
    Context c = PhoneFixture.INSTRUMENTATION.getTargetContext();
    NotificationManager manager = c.getSystemService(NotificationManager.class);
    PushFixture.enroll(c, 8080);
    try {
      manager.cancelAll();
      Map<String, String> ring =
          PushFixture.message("alert-1", "ring", System.currentTimeMillis() + 60000);
      Map<String, String> bad = new HashMap<>(ring);
      bad.put("proof", "0".repeat(64));
      PushAlerts.receive(c, bad);
      assertEquals(0, manager.getActiveNotifications().length);
      PushAlerts.receive(c, ring);
      PhoneFixture.waitFor(() -> manager.getActiveNotifications().length == 1);
      Notification n = manager.getActiveNotifications()[0].getNotification();
      assertEquals(Notification.CATEGORY_CALL, n.category);
      assertTrue(n.getTimeoutAfter() > 0 && n.getTimeoutAfter() <= 60000);
      assertEquals(
          "Living room",
          n.extras.getParcelable(Notification.EXTRA_CALL_PERSON, Person.class).getName());
      assertTrue(
          Arrays.toString(Arrays.stream(n.actions).map(a -> a.title.toString()).toArray()),
          Arrays.stream(n.actions)
              .anyMatch(
                  a ->
                      (a.title.toString().equals("Answer") || a.title.toString().equals("Video"))));
      assertTrue(Arrays.stream(n.actions).anyMatch(a -> a.title.toString().equals("Decline")));
      PushAlerts.receive(c, ring);
      assertEquals(1, manager.getActiveNotifications().length);
      PushAlerts.receive(
          c, PushFixture.message("alert-1", "cancel", System.currentTimeMillis() + 60000));
      PhoneFixture.waitFor(() -> manager.getActiveNotifications().length == 0);
      PushAlerts.receive(c, ring);
      assertEquals(0, manager.getActiveNotifications().length);
      PushAlerts.receive(
          c, PushFixture.message("out-of-order", "cancel", System.currentTimeMillis() + 60000));
      PushAlerts.receive(
          c, PushFixture.message("out-of-order", "ring", System.currentTimeMillis() + 60000));
      assertEquals(0, manager.getActiveNotifications().length);
      PushAlerts.receive(c, PushFixture.message("expired", "ring", System.currentTimeMillis() - 1));
      assertEquals(0, manager.getActiveNotifications().length);
      PushAlerts.receive(
          c, PushFixture.message("timeout", "ring", System.currentTimeMillis() + 2000));
      PhoneFixture.waitFor(() -> manager.getActiveNotifications().length == 1);
      PhoneFixture.waitFor(() -> manager.getActiveNotifications().length == 0);
    } finally {
      manager.cancelAll();
      new File(c.getNoBackupFilesDir(), "enrollment.json").delete();
    }
  }
}
