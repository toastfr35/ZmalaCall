// @test A-HLT-011
// @requirements HLR-AND-CALL-001, HLR-AND-CALL-003, HLR-AND-UI-001
// @environment native-display
// @plan On a disposable emulator, answer a signed SIP fixture call, move the activity behind Home,
// inspect the ongoing service notification and paused native camera, reject a stale hangup intent,
// return, recreate the activity, lock/wake the screen and hang up from the notification while hidden.
// @pass The same core/call survives Home, recreation and screen-off. Camera pauses/restores, no
// replacement INVITE is sent, and hidden hangup clears service, registration, notification and audio focus.
// This verifies SDK/Android lifecycle behavior, not real microphone quality, vendor power policy or Doze.
package org.zmala.phone;

import static org.junit.Assert.*;
import android.Manifest;
import android.app.*;
import android.content.*;
import androidx.test.rule.ActivityTestRule;
import androidx.test.rule.GrantPermissionRule;
import java.io.*;
import java.nio.file.Files;
import org.junit.*;

public class CallContinuityTest {
  @Rule public GrantPermissionRule permissions = GrantPermissionRule.grant(Manifest.permission.CAMERA,
      Manifest.permission.RECORD_AUDIO, Manifest.permission.POST_NOTIFICATIONS, "android.permission.ACCESS_LOCAL_NETWORK");
  @Rule public ActivityTestRule<MainActivity> activity = new ActivityTestRule<>(MainActivity.class, false, false);
  @Test public void activeCallSurvivesHomeRecreationAndScreenOff() throws Exception {
    Assume.assumeTrue("Requires a disposable emulator", android.os.Build.MODEL.contains("sdk_gphone"));
    Context context = PhoneFixture.INSTRUMENTATION.getTargetContext();
    File enrollment = new File(context.getNoBackupFilesDir(), "enrollment.json");
    CallSession session = CallSession.get(context);
    PhoneFixture.endSession();
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip(); PhoneFixture.Http http = new PhoneFixture.Http(PhoneFixture.config(sip.port()))) {
      Files.writeString(enrollment.toPath(), PhoneFixture.qr(http.port(), "app"));
      MainActivity screen = activity.launchActivity(null);
      PhoneFixture.waitFor(() -> sip.authenticated);
      sip.incoming("continuity", PhoneFixture.proof("continuity"));
      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Answer video call"));
      PhoneFixture.click(screen, "Answer video call");
      PhoneFixture.waitFor(() -> session.engine.call != null && session.engine.call.getState() == org.linphone.core.Call.State.StreamsRunning);
      org.linphone.core.Call call = session.engine.call;
      var field = CallEngine.class.getDeclaredField("core"); field.setAccessible(true);
      Object core = field.get(session.engine);
      PhoneFixture.waitFor(() -> ongoing(context) != null);
      assertTrue(call.isCameraEnabled());
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> screen.moveTaskToBack(true));
      PhoneFixture.waitFor(() -> !session.visible && !call.isCameraEnabled());
      assertSame(call, session.engine.call); assertSame(core, field.get(session.engine));
      assertFalse("Backgrounding must not unregister", sip.unregistered);
      context.startService(new Intent(context, CallService.class).setAction(CallService.END).putExtra(CallService.CALL_ID, "old-call"));
      PhoneFixture.INSTRUMENTATION.waitForIdleSync(); assertSame(call, session.engine.call);
      Notification active = ongoing(context);
      assertNotNull(active); assertTrue((active.flags & Notification.FLAG_ONGOING_EVENT) != 0);
      active.contentIntent.send();
      PhoneFixture.waitFor(() -> session.visible && call.isCameraEnabled());
      assertSame(call, session.engine.call);
      PhoneFixture.INSTRUMENTATION.runOnMainSync(screen::recreate);
      PhoneFixture.waitFor(() -> session.visible && resumed() != screen);
      MainActivity replacement = resumed(); assertNotNull(replacement);
      assertSame(call, session.engine.call); assertSame(core, field.get(session.engine));
      PhoneFixture.waitFor(() -> call.isCameraEnabled());
      shell("input keyevent KEYCODE_SLEEP");
      PhoneFixture.waitFor(() -> !session.visible && !call.isCameraEnabled());
      assertSame(call, session.engine.call); assertNotNull(ongoing(context));
      shell("input keyevent KEYCODE_WAKEUP"); shell("wm dismiss-keyguard");
      ongoing(context).contentIntent.send();
      PhoneFixture.waitFor(() -> session.visible && call.isCameraEnabled());
      assertNull("Camera visibility must not renegotiate", sip.invites.poll(300, java.util.concurrent.TimeUnit.MILLISECONDS));
      MainActivity current = resumed();
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> current.moveTaskToBack(true));
      PhoneFixture.waitFor(() -> !session.visible);
      active = ongoing(context); boolean ended = false;
      for (Notification.Action action : active.actions) if (action.title.toString().equals("End call")) {
        action.actionIntent.send(); ended = true;
      }
      assertTrue("Ongoing notification needs an End call action", ended);
      PhoneFixture.waitFor(() -> session.engine.call == null && ongoing(context) == null && !session.engine.registered);
      assertEquals(android.media.AudioManager.MODE_NORMAL, context.getSystemService(android.media.AudioManager.class).getMode());
    } finally {
      PhoneFixture.endSession(); shell("input keyevent KEYCODE_WAKEUP"); shell("wm dismiss-keyguard");
      MainActivity current = resumed();
      if (current != null) PhoneFixture.INSTRUMENTATION.runOnMainSync(current::finish);
      activity.finishActivity(); Files.deleteIfExists(enrollment.toPath());
    }
  }
  private static MainActivity resumed() {
    java.util.concurrent.atomic.AtomicReference<MainActivity> found = new java.util.concurrent.atomic.AtomicReference<>();
    PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
      for (Activity activity : androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry.getInstance()
          .getActivitiesInStage(androidx.test.runner.lifecycle.Stage.RESUMED))
        if (activity instanceof MainActivity) found.set((MainActivity) activity);
    });
    return found.get();
  }
  private static Notification ongoing(Context context) {
    for (var notification : context.getSystemService(NotificationManager.class).getActiveNotifications())
      if (notification.getId() == CallService.NOTIFICATION) return notification.getNotification();
    return null;
  }
  private static void shell(String command) throws Exception {
    try (android.os.ParcelFileDescriptor descriptor = PhoneFixture.INSTRUMENTATION.getUiAutomation().executeShellCommand(command);
        InputStream input = new FileInputStream(descriptor.getFileDescriptor())) { input.readAllBytes(); }
  }
}
