// @test A-HLT-001

// @requirements HLR-AND-ENROLL-001, HLR-AND-UI-001, HLR-AND-CALL-001

// @environment native-display

// @plan Tap the setup action to open the real scanner, wait for its active camera preview and

// cancel;

// feed scanner results to the real activity, reject a Terminal code, confirm an App server,

// fetch authenticated HTTP configuration and register through the native SDK; inspect the permitted

// contact screen, answer a signed incoming call, toggle mute/speaker, hang up and return to the

// contact list without an in-app reset action.

// Tap an online contact name, verify its outgoing SIP request and return SIP 180; inspect Ringing

// before rejecting that call and exercising the incoming call.

// During the answered call, reveal icon controls, toggle audio and rotate; verify the same video

// surfaces survive before hanging up. With no fixture video packets, assert Connecting video

// remains visible after answer and after rotation.
// Cycle all three listening states while the microphone stays muted. Check call-stream volume
// key selection, dispatch a vertical video gesture and restore the original system volume.
// Enroll a directory with recently active, push-only and offline contacts. Assert all three
// colours/state labels and disabled offline action, and dial both the green and blue names.

// @pass The scanner opens without crashing and cancellation returns to setup without enrollment;

// the Terminal code does not enroll, the App code produces an enabled contact without the phone

// account name or ready-status text, SIP 180 shows Ringing,

// mute/speaker labels change, hangup restores contacts with no Reset setup action.

// The compact contact name is the outgoing call target; tapping it sends an INVITE to that contact.

// An answered fixture call without remote frames keeps the Connecting video indication.
// Listening state is independent of the microphone; swipes change bounded call volume and
// leave microphone mute selected. Ending the call restores default volume-key stream selection.
// Available is green, Try calling blue and Offline red; green/blue dial the named permitted peer.

// Camera optical QR reading and real audio/video quality are separate physical checks.

package org.zmala.phone;



import static org.junit.Assert.*;



import android.Manifest;

import android.app.Instrumentation;

import androidx.test.rule.ActivityTestRule;

import androidx.test.rule.GrantPermissionRule;

import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry;

import androidx.test.runner.lifecycle.Stage;

import com.journeyapps.barcodescanner.CaptureActivity;

import com.journeyapps.barcodescanner.DecoratedBarcodeView;

import java.io.File;

import java.nio.file.Files;

import org.junit.*;



public class EnrollmentFlowTest {
  private static org.json.JSONObject presenceConfig(int port) throws Exception {
    org.json.JSONObject config = PhoneFixture.config(port);
    config.getJSONArray("contacts").put(new org.json.JSONObject()
        .put("id", "phone2").put("name", "Sleeping phone").put("photo", "")
        .put("can_call", true).put("can_receive", true).put("online", true).put("presence", "push"));
    config.getJSONArray("contacts").put(new org.json.JSONObject()
        .put("id", "term2").put("name", "Kitchen").put("photo", "")
        .put("can_call", true).put("can_receive", true).put("online", false).put("presence", "offline"));
    return config;
  }

  @Rule

  public GrantPermissionRule permissions =

      GrantPermissionRule.grant(

          android.os.Build.VERSION.SDK_INT >= 37

              ? new String[] {

                Manifest.permission.CAMERA,

                Manifest.permission.RECORD_AUDIO,

                "android.permission.ACCESS_LOCAL_NETWORK"

              }

              : new String[] {Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO});



  @Rule

  public ActivityTestRule<MainActivity> activity =

      new ActivityTestRule<>(MainActivity.class, false, false);



  @Test

  public void setupButtonOpensScannerAndCancellationReturnsToSetup() throws Exception {

    File file =

        new File(

            PhoneFixture.INSTRUMENTATION.getTargetContext().getNoBackupFilesDir(),

            "enrollment.json");

    assertFalse("Scanner launch check requires an unenrolled test device", file.exists());

    MainActivity screen = activity.launchActivity(null);

    Instrumentation.ActivityMonitor monitor =

        PhoneFixture.INSTRUMENTATION.addMonitor(CaptureActivity.class.getName(), null, false);

    CaptureActivity scanner = null;

    try {

      PhoneFixture.click(screen, "Scan setup QR");

      scanner = (CaptureActivity) monitor.waitForActivityWithTimeout(10000);

      assertNotNull("The setup action must launch the real scanner", scanner);

      CaptureActivity opened = scanner;

      PhoneFixture.waitFor(

          () -> {

            java.util.concurrent.atomic.AtomicBoolean resumed =

                new java.util.concurrent.atomic.AtomicBoolean();

            PhoneFixture.INSTRUMENTATION.runOnMainSync(

                () ->

                    resumed.set(

                        ActivityLifecycleMonitorRegistry.getInstance().getLifecycleStageOf(opened)

                            == Stage.RESUMED));

            return resumed.get();

          });

      PhoneFixture.INSTRUMENTATION.runOnMainSync(

          () -> {

            DecoratedBarcodeView view =

                opened.findViewById(com.google.zxing.client.android.R.id.zxing_barcode_scanner);

            assertNotNull("Scanner layout must be inflated", view);

            assertNotNull(

                "Scanner must create a camera instance", view.getBarcodeView().getCameraInstance());

          });

      PhoneFixture.waitFor(

          () -> {

            java.util.concurrent.atomic.AtomicBoolean preview =

                new java.util.concurrent.atomic.AtomicBoolean();

            PhoneFixture.INSTRUMENTATION.runOnMainSync(

                () -> {

                  DecoratedBarcodeView view =

                      opened.findViewById(

                          com.google.zxing.client.android.R.id.zxing_barcode_scanner);

                  preview.set(view.getBarcodeView().isPreviewActive());

                });

            return preview.get();

          });

      PhoneFixture.snapshot("scanner");

      PhoneFixture.INSTRUMENTATION.runOnMainSync(opened::onBackPressed);

      PhoneFixture.waitFor(

          () -> {

            java.util.concurrent.atomic.AtomicBoolean resumed =

                new java.util.concurrent.atomic.AtomicBoolean();

            PhoneFixture.INSTRUMENTATION.runOnMainSync(

                () ->

                    resumed.set(

                        ActivityLifecycleMonitorRegistry.getInstance().getLifecycleStageOf(screen)

                            == Stage.RESUMED));

            return resumed.get();

          });

      assertTrue(PhoneFixture.hasText(screen, "Scan setup QR"));

      assertFalse("Cancelling the scanner must not enroll", file.exists());

    } finally {

      if (scanner != null) {

        CaptureActivity opened = scanner;

        PhoneFixture.INSTRUMENTATION.runOnMainSync(opened::finish);

      }

      PhoneFixture.INSTRUMENTATION.removeMonitor(monitor);

    }

  }



  @Test

  public void enrollDirectoryAndCall() throws Exception {

    File file =

        new File(

            PhoneFixture.INSTRUMENTATION.getTargetContext().getNoBackupFilesDir(),

            "enrollment.json");

    Files.deleteIfExists(file.toPath());

    try (PhoneFixture.Sip sip = new PhoneFixture.Sip();

        PhoneFixture.Http http = new PhoneFixture.Http(presenceConfig(sip.port()))) {

      MainActivity screen = activity.launchActivity(null);

      PhoneFixture.scan(screen, PhoneFixture.qr(http.port(), "terminal"));

      PhoneFixture.dialog("OK");

      assertFalse(file.exists());

      PhoneFixture.scan(screen, PhoneFixture.qr(http.port(), "app"));

      PhoneFixture.dialog("Connect");

      PhoneFixture.waitFor(() -> http.authorized);

      PhoneFixture.waitFor(() -> file.exists());

      PhoneFixture.waitFor(() -> sip.authenticated);

      PhoneFixture.INSTRUMENTATION.waitForIdleSync();

      PhoneFixture.INSTRUMENTATION.runOnMainSync(

          () -> assertNotNull(PhoneFixture.text(screen.getWindow().getDecorView(), "Living room")));

      assertTrue(http.authorized);

      assertFalse(Files.readString(file.toPath()).contains("test-password"));

      PhoneFixture.waitFor(() -> PhoneFixture.enabledText(screen, "Living room"));

      assertFalse(PhoneFixture.hasText(screen, "Ready to call"));

      assertFalse(PhoneFixture.hasText(screen, "Test phone"));

      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
        android.view.View root = screen.getWindow().getDecorView();
        for (Object[] state : new Object[][]{{"Living room", "Available", MainActivity.GREEN},
            {"Sleeping phone", "Try calling", MainActivity.BLUE}, {"Kitchen", "Offline", MainActivity.RED}}) {
          android.view.View item = PhoneFixture.text(root, (String) state[0]);
          while (!(item instanceof ContactCard)) item = (android.view.View) item.getParent();
          assertEquals((int) state[2], ((ContactCard) item).color);
          assertNotNull(PhoneFixture.text(item, (String) state[1]));
          assertTrue(item.isClickable());
        }
      });
      PhoneFixture.click(screen, "Kitchen");
      assertFalse(PhoneFixture.enabledText(screen, "Call"));
      PhoneFixture.click(screen, "Contacts");
      sip.ringOutgoing = true;
      PhoneFixture.click(screen, "Sleeping phone");
      PhoneFixture.click(screen, "Call");
      String pushInvite = sip.invites.poll(10, java.util.concurrent.TimeUnit.SECONDS);
      assertNotNull(pushInvite);
      assertTrue(pushInvite.startsWith("INVITE sip:phone2@127.0.0.1"));
      sip.respond(pushInvite, 486, "");
      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Contacts")
          && !PhoneFixture.hasDescription(screen, "End call"));
      PhoneFixture.click(screen, "Contacts");

      PhoneFixture.snapshot("contacts");

      sip.ringOutgoing = true;

      PhoneFixture.click(screen, "Living room");
      PhoneFixture.click(screen, "Call");

      String outgoing = sip.invites.poll(10, java.util.concurrent.TimeUnit.SECONDS);

      assertNotNull(outgoing);

      assertTrue(outgoing.startsWith("INVITE sip:term1@127.0.0.1"));

      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Ringing…"));

      PhoneFixture.snapshot("outgoing-ringing");

      sip.ringOutgoing = false;

      sip.respond(outgoing, 486, "");

      PhoneFixture.waitFor(

          () ->

              PhoneFixture.hasText(screen, "Living room")

                  && !PhoneFixture.hasText(screen, "End call"));

      sip.incoming("screen-call", PhoneFixture.proof("screen-call"));

      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Answer video call"));

      PhoneFixture.snapshot("incoming");

      PhoneFixture.click(screen, "Answer video call");

      PhoneFixture.waitFor(

          () -> PhoneFixture.hasDescription(screen, "Remote video. Tap to show call controls."));

      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Connecting video…"));

      assertFalse(PhoneFixture.hasText(screen, "Living room"));

      assertFalse(PhoneFixture.hasText(screen, "ZmalaPhone"));

      PhoneFixture.click(screen, "Remote video. Tap to show call controls.");

      PhoneFixture.click(screen, "Mute microphone");

      assertTrue(PhoneFixture.hasDescription(screen, "Unmute microphone"));

      PhoneFixture.click(screen, "Loudspeaker. Switch to earpiece");

      if (PhoneFixture.hasDescription(screen, "Earpiece. Mute call sound"))
        PhoneFixture.click(screen, "Earpiece. Mute call sound");
      assertTrue(PhoneFixture.hasDescription(screen, "Call sound muted. Switch to loudspeaker"));
      assertTrue(PhoneFixture.hasDescription(screen, "Unmute microphone"));
      PhoneFixture.click(screen, "Call sound muted. Switch to loudspeaker");
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
        android.media.AudioManager audio = (android.media.AudioManager) screen.getSystemService(android.content.Context.AUDIO_SERVICE);
        int stream = android.media.AudioManager.STREAM_VOICE_CALL;
        int originalVolume = audio.getStreamVolume(stream);
        int maximum = audio.getStreamMaxVolume(stream);
        int minimum = audio.getStreamMinVolume(stream);
        try {
          assertEquals(stream, screen.getVolumeControlStream());
          audio.setStreamVolume(stream, minimum, 0);
          float density = screen.getResources().getDisplayMetrics().density;
          android.view.View video = PhoneFixture.description(screen.getWindow().getDecorView(), "Remote video. Tap to show call controls.");
          for (int[] step : new int[][]{{0, 200}, {2, 136}, {1, 136}}) {
            android.view.MotionEvent event = android.view.MotionEvent.obtain(0, 10, step[0], 100 * density, step[1] * density, 0);
            video.dispatchTouchEvent(event); event.recycle();
          }
          assertEquals(Math.min(maximum, minimum + 2), audio.getStreamVolume(stream));
          for (int[] step : new int[][]{{0, 200}, {2, 2000}, {1, 2000}}) {
            android.view.MotionEvent event = android.view.MotionEvent.obtain(0, 10, step[0], 100 * density, step[1] * density, 0);
            video.dispatchTouchEvent(event); event.recycle();
          }
          assertEquals(minimum, audio.getStreamVolume(stream));
          for (int[] step : new int[][]{{0, 2000}, {2, 200}, {1, 200}}) {
            android.view.MotionEvent event = android.view.MotionEvent.obtain(0, 10, step[0], 100 * density, step[1] * density, 0);
            video.dispatchTouchEvent(event); event.recycle();
          }
          assertEquals(maximum, audio.getStreamVolume(stream));
          assertNotNull(PhoneFixture.description(screen.getWindow().getDecorView(), "Unmute microphone"));
        } finally { audio.setStreamVolume(stream, originalVolume, 0); }
      });

      PhoneFixture.snapshot("active-call");

      android.view.View[] surfaces = new android.view.View[2];

      PhoneFixture.INSTRUMENTATION.runOnMainSync(

          () -> {

            surfaces[0] =

                PhoneFixture.description(

                    screen.getWindow().getDecorView(), "Remote video. Tap to show call controls.");

            surfaces[1] =

                PhoneFixture.description(

                    screen.getWindow().getDecorView(), "Your camera. Tap to show call controls.");

            screen.setRequestedOrientation(

                android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);

          });

      PhoneFixture.waitFor(

          () ->

              screen.getResources().getConfiguration().orientation

                  == android.content.res.Configuration.ORIENTATION_LANDSCAPE);

      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Connecting video…"));

      PhoneFixture.INSTRUMENTATION.runOnMainSync(

          () -> {

            assertSame(

                surfaces[0],

                PhoneFixture.description(

                    screen.getWindow().getDecorView(), "Remote video. Tap to show call controls."));

            assertSame(

                surfaces[1],

                PhoneFixture.description(

                    screen.getWindow().getDecorView(), "Your camera. Tap to show call controls."));

          });

      PhoneFixture.snapshot("active-call-landscape");

      PhoneFixture.click(screen, "Remote video. Tap to show call controls.");

      PhoneFixture.click(screen, "End call");

      PhoneFixture.INSTRUMENTATION.runOnMainSync(

          () ->

              screen.setRequestedOrientation(

                  android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT));

      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Living room"));

      assertEquals(android.media.AudioManager.USE_DEFAULT_STREAM_TYPE, screen.getVolumeControlStream());

      assertFalse(PhoneFixture.hasText(screen, "Reset setup"));

      assertTrue(file.exists());

    } finally {

      activity.finishActivity();

      Files.deleteIfExists(file.toPath());

    }

  }

}
