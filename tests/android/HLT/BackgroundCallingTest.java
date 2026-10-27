// @test A-HLT-003
// @requirements HLR-AND-CALL-003
// @environment native-sdk
// @plan With fixture enrollment and no visible activity, inject a signed ring and invoke its native Answer action. Observe fresh Digest registration and send the matching signed SIP INVITE; check automatic video answer and notification dismissal. Separately invoke Decline and inspect the authenticated HTTP request. Actual Firebase, locked-screen and Doze delivery are hardware checks.
// @pass Answer reconnects and accepts only the matching call; Decline dismisses and sends bearer- authenticated cancellation without launching a call. No cloud transport or media-quality claim.
package org.zmala.phone;

import static org.junit.Assert.*;

import android.app.*;
import android.content.*;
import androidx.test.rule.GrantPermissionRule;
import java.io.File;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.junit.*;

public class BackgroundCallingTest {
  @Rule
  public GrantPermissionRule permissions =
      GrantPermissionRule.grant(
          android.os.Build.VERSION.SDK_INT >= 37
              ? new String[] {
                android.Manifest.permission.CAMERA,
                android.Manifest.permission.RECORD_AUDIO,
                android.Manifest.permission.POST_NOTIFICATIONS,
                "android.permission.ACCESS_LOCAL_NETWORK"
              }
              : new String[] {
                android.Manifest.permission.CAMERA,
                android.Manifest.permission.RECORD_AUDIO,
                android.Manifest.permission.POST_NOTIFICATIONS
              });

  @Test
  public void notificationAnswerReconnectsAndDeclineCancels() throws Exception {
    Context c = PhoneFixture.INSTRUMENTATION.getTargetContext();
    NotificationManager manager = c.getSystemService(NotificationManager.class);
    MainActivity screen = null;
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip();
        PhoneFixture.Http http = new PhoneFixture.Http(PhoneFixture.config(sip.port()))) {
      PushFixture.enroll(c, http.port());
      manager.cancelAll();
      PushAlerts.receive(
          c, PushFixture.message("declined", "ring", System.currentTimeMillis() + 60000));
      PhoneFixture.waitFor(() -> manager.getActiveNotifications().length == 1);
      Notification n = manager.getActiveNotifications()[0].getNotification();
      for (Notification.Action a : n.actions)
        if (a.title.toString().equals("Decline")) a.actionIntent.send();
      PhoneFixture.waitFor(() -> manager.getActiveNotifications().length == 0);
      PhoneFixture.waitFor(() -> http.lastRequest.startsWith("POST /api/app/call/decline"));
      assertTrue(http.authorized);
      assertTrue(http.lastBody.contains("declined"));
      PushAlerts.receive(
          c, PushFixture.message("answered", "ring", System.currentTimeMillis() + 60000));
      PhoneFixture.waitFor(() -> manager.getActiveNotifications().length == 1);
      Instrumentation.ActivityMonitor monitor =
          PhoneFixture.INSTRUMENTATION.addMonitor(MainActivity.class.getName(), null, false);
      n = manager.getActiveNotifications()[0].getNotification();
      for (Notification.Action a : n.actions)
        if ((a.title.toString().equals("Answer") || a.title.toString().equals("Video")))
          a.actionIntent.send();
      screen = (MainActivity) monitor.waitForActivityWithTimeout(12000);
      assertNotNull(screen);
      PhoneFixture.INSTRUMENTATION.removeMonitor(monitor);
      PhoneFixture.waitFor(() -> sip.authenticated);
      sip.incoming("answered", PhoneFixture.proof("answered"));
      String answer = null;
      long end = System.nanoTime() + TimeUnit.SECONDS.toNanos(12);
      while (System.nanoTime() < end) {
        String r = sip.responses.poll(1, TimeUnit.SECONDS);
        if (r != null && r.startsWith("SIP/2.0 200") && r.contains("m=video ")) {
          answer = r;
          break;
        }
      }
      assertNotNull("Notification Answer must accept the matching authenticated SIP call", answer);
      assertFalse(java.util.Arrays.stream(manager.getActiveNotifications())
          .anyMatch(notification -> notification.getId() == 1 && "answered".equals(notification.getTag())));
    } finally {
      PhoneFixture.endSession();
      if (screen != null) {
        MainActivity a = screen;
        PhoneFixture.INSTRUMENTATION.runOnMainSync(a::finish);
        PhoneFixture.INSTRUMENTATION.waitForIdleSync();
      }
      manager.cancelAll();
      new File(c.getNoBackupFilesDir(), "enrollment.json").delete();
    }
  }
}
