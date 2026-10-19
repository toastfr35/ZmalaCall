// @test A-LLT-003
// @requirements LLR-AND-UI-002
// @environment native-display
// @plan Open the activity without enrollment; inspect setup instructions and minimum touch height.
// Enroll against local fixtures with online/offline contacts; inspect compact name buttons and
// rounded portraits, then tap the online name and inspect its outgoing SIP INVITE.
// Check that the contact screen omits the phone account name and ready status.
// Check balanced vertical space for two contacts; add enough contacts to overflow and verify
// top alignment and scrolling. No Reset setup action is present.
// @pass Setup explains using a supplied QR without server administration; setup labels, action
// geometry assertions pass on an Android display.
// Online names are green and callable, offline names gray/disabled, and tapping calls the named
// peer.
package org.zmala.phone;

import static org.junit.Assert.*;

import android.Manifest;
import androidx.test.rule.ActivityTestRule;
import androidx.test.rule.GrantPermissionRule;
import java.io.File;
import java.nio.file.Files;
import org.junit.*;

public class InterfaceTest {
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
  public void contactNamesShowPresenceAndDial() throws Exception {
    File file =
        new File(
            PhoneFixture.INSTRUMENTATION.getTargetContext().getNoBackupFilesDir(),
            "enrollment.json");
    Files.deleteIfExists(file.toPath());
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip()) {
      org.json.JSONObject config = PhoneFixture.config(sip.port());
      config
          .getJSONArray("contacts")
          .put(
              new org.json.JSONObject()
                  .put("id", "term2")
                  .put("name", "Kitchen")
                  .put("photo", "")
                  .put("can_call", true)
                  .put("can_receive", true)
                  .put("online", false));
      try (PhoneFixture.Http http = new PhoneFixture.Http(config)) {
        MainActivity screen = activity.launchActivity(null);
        PhoneFixture.scan(screen, PhoneFixture.qr(http.port(), "app"));
        PhoneFixture.dialog("Connect");
        PhoneFixture.waitFor(() -> PhoneFixture.enabledText(screen, "Living room"));
        PhoneFixture.INSTRUMENTATION.runOnMainSync(
            () -> {
              android.widget.Button online =
                  (android.widget.Button)
                      PhoneFixture.text(screen.getWindow().getDecorView(), "Living room");
              android.widget.Button offline =
                  (android.widget.Button)
                      PhoneFixture.text(screen.getWindow().getDecorView(), "Kitchen");
              assertTrue(online.isEnabled());
              assertFalse(offline.isEnabled());
              assertEquals(
                  MainActivity.GREEN,
                  ((android.graphics.drawable.GradientDrawable) online.getBackground())
                      .getColor()
                      .getDefaultColor());
              assertEquals(
                  MainActivity.OFFLINE,
                  ((android.graphics.drawable.GradientDrawable) offline.getBackground())
                      .getColor()
                      .getDefaultColor());
              assertTrue(online.getContentDescription().toString().contains("online"));
              assertTrue(offline.getContentDescription().toString().contains("offline"));
              android.view.ViewGroup row = (android.view.ViewGroup) online.getParent();
              assertEquals(2, row.getChildCount());
              android.widget.ImageView portrait = (android.widget.ImageView) row.getChildAt(0);
              assertTrue(portrait.getClipToOutline());
              assertTrue(
                  ((android.graphics.drawable.GradientDrawable) portrait.getBackground())
                          .getCornerRadius()
                      > 0);
              float density = screen.getResources().getDisplayMetrics().density;
              assertTrue(online.getHeight() >= 60 * density);
              assertTrue("Short names should fit a compact row", row.getHeight() <= 80 * density);
              assertNull(PhoneFixture.text(screen.getWindow().getDecorView(), "Video call"));
              assertNull(PhoneFixture.text(screen.getWindow().getDecorView(), "Available"));
              assertNull(PhoneFixture.text(screen.getWindow().getDecorView(), "Ready to call"));
              assertNull(PhoneFixture.text(screen.getWindow().getDecorView(), "Test phone"));
              assertNull(PhoneFixture.text(screen.getWindow().getDecorView(), "Reset setup"));
              android.view.ViewGroup rows = (android.view.ViewGroup) row.getParent();
              android.view.View last = rows.getChildAt(rows.getChildCount() - 1);
              assertEquals(
                  "Short list must be centered",
                  row.getTop(),
                  rows.getHeight() - last.getBottom(),
                  2);
            });
        PhoneFixture.snapshot("compact-contacts");
        for (int i = 0; i < 20; i++)
          config
              .getJSONArray("contacts")
              .put(
                  new org.json.JSONObject()
                      .put("id", "extra" + i)
                      .put("name", "Extra " + i)
                      .put("can_call", true)
                      .put("online", false));
        config.put("configuration_version", 2);
        PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Extra 19"));
        PhoneFixture.INSTRUMENTATION.waitForIdleSync();
        PhoneFixture.INSTRUMENTATION.runOnMainSync(
            () -> {
              android.view.View row =
                  (android.view.View)
                      PhoneFixture.text(screen.getWindow().getDecorView(), "Living room")
                          .getParent();
              android.view.ViewGroup rows = (android.view.ViewGroup) row.getParent();
              android.widget.ScrollView scroll = (android.widget.ScrollView) rows.getParent();
              assertTrue("Long list must scroll", scroll.canScrollVertically(1));
              assertTrue(
                  "Long list must start at the top",
                  row.getTop() <= 5 * screen.getResources().getDisplayMetrics().density);
            });
        PhoneFixture.click(screen, "Living room");
        String invite = sip.invites.poll(10, java.util.concurrent.TimeUnit.SECONDS);
        assertNotNull("Tapping an online name must start a call", invite);
        assertTrue(invite.startsWith("INVITE sip:term1@127.0.0.1"));
      }
    } finally {
      activity.finishActivity();
      Files.deleteIfExists(file.toPath());
    }
  }

  @Test
  public void setupInstructions() throws Exception {
    File file =
        new File(
            PhoneFixture.INSTRUMENTATION.getTargetContext().getNoBackupFilesDir(),
            "enrollment.json");
    Files.deleteIfExists(file.toPath());
    final MainActivity screen = activity.launchActivity(null);
    PhoneFixture.INSTRUMENTATION.runOnMainSync(
        () -> {
          android.widget.TextView button =
              PhoneFixture.text(screen.getWindow().getDecorView(), "Scan setup QR");
          assertNotNull(button);
          assertNotNull(
              PhoneFixture.text(
                  screen.getWindow().getDecorView(),
                  "Scan the setup QR code you received by email or on paper."));
          assertTrue(
              button.getMinimumHeight() >= 60 * screen.getResources().getDisplayMetrics().density);
          assertNotNull(
              PhoneFixture.text(
                  screen.getWindow().getDecorView(),
                  "Keep this screen open to receive calls"));
        });
  }
}
