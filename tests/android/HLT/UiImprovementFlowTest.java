// @test A-HLT-010
// @requirements HLR-AND-ENROLL-001, HLR-AND-UI-001, HLR-AND-CALL-001, HLR-AND-CALL-005, HLR-AND-UPDATE-001
// @environment native-display
// @plan On a disposable Android emulator profile, import a generated QR image through the activity
// result path, inspect server confirmation and cancel without enrollment. Start a real native call
// against local HTTP/SIP fixtures; inject a configuration 503 and then 403.
// With notification permission unavailable, open the footer action and intercept the Android settings intent.
// Inject a newer verified-metadata candidate without a network download; inspect the quiet footer,
// explicit update dialog and simulated transfer/stage rendering. Do not claim package installation.
// Clear the earlier push fixtures' ring deadline before the idle-update scenario.
// Select French through Android's per-app locale API; inspect the actual contact/action screens.
// @pass QR import uses explicit confirmation without saving before acceptance. A 503 preserves the
// same native call with a reconnecting notice; access revocation stops it. Physical media is not qualified.
package org.zmala.phone;

import static org.junit.Assert.*;
import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import androidx.test.rule.ActivityTestRule;
import androidx.test.rule.GrantPermissionRule;
import java.io.*;
import java.nio.file.Files;
import org.junit.*;

public class UiImprovementFlowTest {
  @Rule public GrantPermissionRule permissions = GrantPermissionRule.grant(
      Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO, "android.permission.ACCESS_LOCAL_NETWORK");
  @Rule public ActivityTestRule<MainActivity> activity = new ActivityTestRule<>(MainActivity.class, false, false);
  private File enrollment;
  @Before public void disposableProfileOnly() throws Exception {
    Assume.assumeTrue("Destructive setup scenario requires a disposable emulator", android.os.Build.MODEL.contains("sdk_gphone"));
    enrollment = new File(PhoneFixture.INSTRUMENTATION.getTargetContext().getNoBackupFilesDir(), "enrollment.json");
    Files.deleteIfExists(enrollment.toPath());
  }
  @After public void cleanup() throws Exception {
    if (enrollment != null) PhoneFixture.endSession();
    activity.finishActivity();
    if (enrollment != null) Files.deleteIfExists(enrollment.toPath());
  }
  @Test public void importedQrUsesTheSameConfirmationAndCancelKeepsSetupEmpty() throws Exception {
    File picture = new File(PhoneFixture.INSTRUMENTATION.getTargetContext().getCacheDir(), "qr-fixture.png");
    var matrix = new com.google.zxing.MultiFormatWriter().encode(PhoneFixture.qr(12345, "app"), com.google.zxing.BarcodeFormat.QR_CODE, 640, 640);
    Bitmap bitmap = Bitmap.createBitmap(640, 640, Bitmap.Config.ARGB_8888);
    for (int y = 0; y < 640; y++) for (int x = 0; x < 640; x++) bitmap.setPixel(x, y, matrix.get(x, y) ? 0xff000000 : 0xffffffff);
    try (OutputStream out = new FileOutputStream(picture)) { bitmap.compress(Bitmap.CompressFormat.PNG, 100, out); }
    bitmap.recycle();
    MainActivity screen = activity.launchActivity(null);
    assertTrue(PhoneFixture.hasText(screen, "Open QR image"));
    PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> screen.onActivityResult(9, Activity.RESULT_OK, new Intent().setData(Uri.fromFile(picture))));
    PhoneFixture.waitFor(() -> PhoneFixture.INSTRUMENTATION.getUiAutomation().getRootInActiveWindow() != null);
    PhoneFixture.dialog("Cancel");
    assertFalse(enrollment.exists());
    assertTrue(PhoneFixture.hasText(screen, "Scan setup QR"));
    Files.deleteIfExists(picture.toPath());
  }
  @Test public void pollingOutagePreservesAnAnsweredCallButRevocationStopsIt() throws Exception {
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip(); PhoneFixture.Http http = new PhoneFixture.Http(PhoneFixture.config(sip.port()))) {
      Files.writeString(enrollment.toPath(), PhoneFixture.qr(http.port(), "app"));
      MainActivity screen = activity.launchActivity(null);
      PhoneFixture.waitFor(() -> sip.authenticated);
      sip.incoming("recovery-ui", PhoneFixture.proof("recovery-ui"));
      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Answer video call"));
      PhoneFixture.click(screen, "Answer video call");
      PhoneFixture.waitFor(() -> PhoneFixture.hasDescription(screen, "Remote video. Tap to show call controls."));
      java.lang.reflect.Field field = MainActivity.class.getDeclaredField("engine"); field.setAccessible(true);
      CallEngine engine = (CallEngine) field.get(screen);
      org.linphone.core.Call call = engine.call; assertNotNull(call);
      http.configurationStatus = 503; refresh(screen);
      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Reconnecting to server…"));
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> assertSame(call, engine.call));
      http.configurationStatus = 403; refresh(screen);
      PhoneFixture.waitFor(() -> engine.call == null);
    }
  }
  @Test public void disabledNotificationsOfferTheAppSettingsAction() throws Exception {
    android.content.Context context = PhoneFixture.INSTRUMENTATION.getTargetContext();
    Assume.assumeFalse("Run this scenario with notification permission denied on the disposable emulator", PushAlerts.allowed(context));
    context.getSharedPreferences("push", 0).edit().putBoolean("permission_asked", true).commit();
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip(); PhoneFixture.Http http = new PhoneFixture.Http(
        PhoneFixture.config(sip.port()).put("push_enabled", true))) {
      Files.writeString(enrollment.toPath(), PhoneFixture.qr(http.port(), "app"));
      MainActivity screen = activity.launchActivity(null);
      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Notifications are off\nEnable notifications"));
      var monitor = PhoneFixture.INSTRUMENTATION.addMonitor(new android.content.IntentFilter(
          android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS), new android.app.Instrumentation.ActivityResult(Activity.RESULT_CANCELED, null), true);
      try {
        PhoneFixture.click(screen, "Notifications are off\nEnable notifications");
        assertEquals(1, monitor.getHits());
      } finally { PhoneFixture.INSTRUMENTATION.removeMonitor(monitor); }
    }
  }
  @Test public void updateDiscoveryIsQuietAndChosenProgressIsVisible() throws Exception {
    android.content.Context context = PhoneFixture.INSTRUMENTATION.getTargetContext();
    PhoneFixture.endSession();
    // Other scenarios intentionally create unexpired signed rings. This scenario starts idle,
    // rather than depending on execution order or waiting ninety seconds for unrelated alerts.
    var ringUntil = UpdateGate.class.getDeclaredField("ringUntil"); ringUntil.setAccessible(true);
    long previousRing = ringUntil.getLong(UpdateGate.INSTANCE);
    context.getSharedPreferences("updates", 0).edit().putLong("checked", System.currentTimeMillis())
        .putBoolean("automatic", false).commit();
    AppUpdates updater = AppUpdates.get(context);
    ringUntil.setLong(UpdateGate.INSTANCE, 0);
    var available = AppUpdates.class.getDeclaredField("available"); available.setAccessible(true);
    var dialog = AppUpdates.class.getDeclaredField("dialog"); dialog.setAccessible(true);
    var downloading = AppUpdates.class.getDeclaredField("downloading"); downloading.setAccessible(true);
    Object before = available.get(updater);
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip(); PhoneFixture.Http http = new PhoneFixture.Http(PhoneFixture.config(sip.port()))) {
      Files.writeString(enrollment.toPath(), PhoneFixture.qr(http.port(), "app"));
      MainActivity screen = activity.launchActivity(null);
      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Living room"));
      var metadata = new org.json.JSONObject().put("tag_name", "v99.0.0").put("draft", false).put("prerelease", false)
          .put("assets", new org.json.JSONArray().put(new org.json.JSONObject().put("name", "ZmalaPhone.apk")
          .put("state", "uploaded").put("size", 100).put("digest", "sha256:" + "a".repeat(64))
          .put("browser_download_url", UpdatePolicy.DOWNLOAD + "v99.0.0/ZmalaPhone.apk")));
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
        try { available.set(updater, UpdatePolicy.parse(metadata.toString(), updater.version()));
          screen.updateAvailabilityChanged();
        } catch (Exception error) { throw new AssertionError(error); }
      });
      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Update available"));
      assertNull(dialog.get(updater));
      PhoneFixture.click(screen, "Update available");
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
        try {
          downloading.setBoolean(updater, true);
          var percent = AppUpdates.class.getDeclaredField("downloadPercent"); percent.setAccessible(true); percent.setInt(updater, 37);
          var status = AppUpdates.class.getDeclaredField("status"); status.setAccessible(true); status.set(updater, "Downloading update… 37%");
          var render = AppUpdates.class.getDeclaredMethod("render"); render.setAccessible(true); render.invoke(updater);
          var bar = AppUpdates.class.getDeclaredField("progressView"); bar.setAccessible(true);
          android.widget.ProgressBar progress = (android.widget.ProgressBar) bar.get(updater);
          assertEquals(37, progress.getProgress()); assertFalse(progress.isIndeterminate());
          status.set(updater, "Checking update…"); percent.setInt(updater, -1); render.invoke(updater);
          assertTrue(progress.isIndeterminate());
        } catch (Exception error) { throw new AssertionError(error); }
      });
      PhoneFixture.dialog("Later");
    } finally {
      ringUntil.setLong(UpdateGate.INSTANCE, previousRing);
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
        try { available.set(updater, before); downloading.setBoolean(updater, false); }
        catch (Exception error) { throw new AssertionError(error); }
      });
    }
  }
  private static void refresh(MainActivity screen) {
    PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
      try {
        var method = MainActivity.class.getDeclaredMethod("refresh", boolean.class); method.setAccessible(true); method.invoke(screen, false);
      } catch (Exception error) { throw new AssertionError(error); }
    });
  }
  @Test public void androidLanguageSelectionUsesFrenchInTheActualActivity() throws Exception {
    android.content.Context context = PhoneFixture.INSTRUMENTATION.getTargetContext();
    android.app.LocaleManager locales = context.getSystemService(android.app.LocaleManager.class);
    android.os.LocaleList before = locales.getApplicationLocales();
    MainActivity screen = null;
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip(); PhoneFixture.Http http = new PhoneFixture.Http(PhoneFixture.config(sip.port()))) {
      Files.writeString(enrollment.toPath(), PhoneFixture.qr(http.port(), "app"));
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> locales.setApplicationLocales(android.os.LocaleList.forLanguageTags("fr")));
      screen = activity.launchActivity(null);
      MainActivity current = screen;
      PhoneFixture.waitFor(() -> PhoneFixture.hasText(current, "Disponible"));
      assertFalse(PhoneFixture.hasText(screen, "Prêt à appeler"));
      PhoneFixture.snapshot("contacts-fr");
      PhoneFixture.click(screen, "Living room");
      assertTrue(PhoneFixture.hasText(screen, "Appeler"));
      assertFalse(PhoneFixture.hasText(screen, "Call"));
      PhoneFixture.snapshot("contact-actions-fr");
    } finally {
      if (screen != null) {
        MainActivity current = screen;
        PhoneFixture.INSTRUMENTATION.runOnMainSync(current::finish);
        PhoneFixture.INSTRUMENTATION.waitForIdleSync();
      }
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> locales.setApplicationLocales(before));
    }
  }
}
