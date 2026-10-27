// @test A-LLT-003
// @requirements LLR-AND-UI-002, LLR-AND-UPDATE-002, LLR-AND-HISTORY-002
// @environment native-display
// @plan Open setup and inspect QR instructions/actions. Enroll with available, push-only and offline
// contacts. Assert each card is one interactive target with correct colour and rounded portrait.
// Open contact actions, inspect simultaneous incoming/sent callback words, clear missed counts,
// request/cancel a callback through authenticated HTTP and navigate Back/Contacts. Offline Call
// stays disabled. Call from an available contact page and inspect its outgoing SIP INVITE.
// @pass Offline cards open their actions without calling, callbacks change Request to Cancel only
// after server confirmation, missed clearing is visible, and enabled Call targets the selected peer.
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
      config.put("callbacks_enabled", true).put("callbacks", new org.json.JSONArray().put(
          new org.json.JSONObject().put("from", "term1").put("to", "phone1").put("status", "pending")).put(
          new org.json.JSONObject().put("from", "phone1").put("to", "term1").put("status", "pending")));
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
      config.getJSONArray("contacts").put(new org.json.JSONObject()
          .put("id", "phone2").put("name", "Sleeping phone").put("photo", "")
          .put("can_call", true).put("can_receive", true).put("online", true).put("presence", "push"));
      try (PhoneFixture.Http http = new PhoneFixture.Http(config)) {
        MainActivity screen = activity.launchActivity(null);
        PhoneFixture.scan(screen, PhoneFixture.qr(http.port(), "app"));
        PhoneFixture.dialog("Connect");
        PhoneFixture.waitFor(() -> PhoneFixture.enabledText(screen, "Living room"));
        CallNotices.ring(screen, "missed-fixture", "term1", System.currentTimeMillis() + 60000);
        CallNotices.finish(screen, "missed-fixture", true);
        PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "1 missed call · Please call back · Callback requested"));
        PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
          android.view.View root = screen.getWindow().getDecorView();
          for (Object[] expected : new Object[][]{{"Living room", MainActivity.GREEN}, {"Kitchen", MainActivity.RED}, {"Sleeping phone", MainActivity.BLUE}}) {
            ContactCard card = card(PhoneFixture.text(root, (String) expected[0]));
            assertEquals((int) expected[1], card.color);
            assertTrue(card.isClickable()); assertTrue(card.isEnabled());
            assertTrue(card.portrait.getClipToOutline());
            assertFalse(card.portrait.isClickable());
          }
          assertNull(PhoneFixture.text(root, "Ready to call"));
          assertNull(PhoneFixture.text(root, "Test phone"));
          assertNotNull(PhoneFixture.text(root, "v" + AppUpdates.get(screen).version()));
          assertEquals(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT, screen.getRequestedOrientation());
        });
        PhoneFixture.snapshot("compact-contacts");
        PhoneFixture.click(screen, "Living room");
        assertTrue(PhoneFixture.hasText(screen, "Please call back\nCallback requested" )
            || PhoneFixture.hasText(screen, "1 missed call\nPlease call back\nCallback requested"));
        assertTrue(PhoneFixture.hasText(screen, "Cancel request"));
        PhoneFixture.click(screen, "Clear missed calls");
        assertFalse(PhoneFixture.hasText(screen, "Clear missed calls"));
        PhoneFixture.click(screen, "Contacts");
        PhoneFixture.click(screen, "Kitchen");
        assertFalse(PhoneFixture.enabledText(screen, "Call"));
        PhoneFixture.snapshot("contact-actions-offline");
        PhoneFixture.click(screen, "Request callback");
        PhoneFixture.waitFor(() -> http.callbackRequests > 0);
        assertEquals("term2", http.callbackRecipient);
        PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Cancel request"));
        PhoneFixture.snapshot("contact-actions-sent");
        PhoneFixture.click(screen, "Cancel request");
        PhoneFixture.waitFor(() -> http.callbackCancellations == 1);
        PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Request callback"));
        PhoneFixture.INSTRUMENTATION.runOnMainSync(screen::onBackPressed);
        PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Living room"));
        sip.ringOutgoing = true;
        PhoneFixture.click(screen, "Living room");
        PhoneFixture.waitFor(() -> PhoneFixture.enabledText(screen, "Call"));
        PhoneFixture.click(screen, "Call");
        String invite = sip.invites.poll(10, java.util.concurrent.TimeUnit.SECONDS);
        assertNotNull("Tapping an online name must start a call", invite);
        assertTrue(invite.startsWith("INVITE sip:term1@127.0.0.1"));
        PhoneFixture.INSTRUMENTATION.runOnMainSync(() ->
            assertNull(PhoneFixture.text(screen.getWindow().getDecorView(), "v" + AppUpdates.get(screen).version())));
        assertEquals(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED, screen.getRequestedOrientation());
        PhoneFixture.click(screen, "Remote video. Tap to show call controls.");
        PhoneFixture.click(screen, "End call");
        PhoneFixture.waitFor(() -> screen.getRequestedOrientation() == android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);
      }
    } finally {
      activity.finishActivity();
      Files.deleteIfExists(file.toPath());
    }
  }

  private static ContactCard card(android.view.View view) {
    while (!(view instanceof ContactCard)) view = (android.view.View) view.getParent();
    return (ContactCard) view;
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
          assertNull(PhoneFixture.text(screen.getWindow().getDecorView(), "v" + AppUpdates.get(screen).version()));
          assertNotNull(
              PhoneFixture.text(
                  screen.getWindow().getDecorView(),
                  "Scan the setup QR code you received by email or on paper."));
          assertTrue(
              button.getMinimumHeight() >= 60 * screen.getResources().getDisplayMetrics().density);
          assertNotNull(PhoneFixture.text(screen.getWindow().getDecorView(), "Open QR image"));
        });
  }
}
