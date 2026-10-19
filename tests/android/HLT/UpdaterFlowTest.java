// @test A-HLT-009
// @requirements HLR-AND-UPDATE-001
// @environment native-display
// @plan On a disposable emulator, supply updateApk and updateVersion instrumentation arguments
// for a release-signed higher-version fixture. Replace only HTTPS transport with deterministic
// GitHub metadata/APK bytes, retaining the real updater, digest/archive verification and installer.
// Attempt a download during an actual outgoing SIP call, hang up, then opt in to automatic updates
// and allow installation. Installation replaces the process; the host checks version and retained
// enrollment marker afterward. No fixture arguments means skipped, not passed.
// @pass No APK is read during the call; after hangup the real Android self-update installs the
// same-key newer APK and the host observes unchanged enrollment. External TLS is not simulated evidence.
package org.zmala.phone;

import static org.junit.Assert.*;
import android.content.Context;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.rule.ActivityTestRule;
import java.io.*;
import java.net.*;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.concurrent.TimeUnit;
import org.json.*;
import org.junit.*;

public class UpdaterFlowTest {
  @Rule public ActivityTestRule<MainActivity> activity = new ActivityTestRule<>(MainActivity.class, false, false);
  @Test public void verifyAfterReplacement() throws Exception {
    Assume.assumeTrue("true".equals(InstrumentationRegistry.getArguments().getString("verifyUpdate")));
    Context c = PhoneFixture.INSTRUMENTATION.getTargetContext();
    assertEquals(InstrumentationRegistry.getArguments().getString("updateVersion"), AppUpdates.get(c).version());
    assertEquals(Files.readString(new File(c.getExternalFilesDir(null), "expected-enrollment.txt").toPath()),
        Files.readString(new File(c.getNoBackupFilesDir(), "enrollment.json").toPath()));
    assertEquals("APK transfer refused during native call", Files.readString(new File(c.getExternalFilesDir(null), "call-exclusion.txt").toPath()));
  }
  @Test public void realInstallerPreservesEnrollmentAfterCall() throws Exception {
    String path = InstrumentationRegistry.getArguments().getString("updateApk");
    Assume.assumeNotNull(path);
    Assume.assumeTrue(android.os.Build.VERSION.SDK_INT >= 31);
    Context c = PhoneFixture.INSTRUMENTATION.getTargetContext();
    String version = InstrumentationRegistry.getArguments().getString("updateVersion");
    File apk = new File(path);
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    try (InputStream in = new FileInputStream(apk)) {
      byte[] buffer = new byte[65536]; int count;
      while ((count = in.read(buffer)) != -1) digest.update(buffer, 0, count);
    }
    String metadata = new JSONObject().put("tag_name", "v" + version).put("draft", false).put("prerelease", false)
        .put("assets", new JSONArray().put(new JSONObject().put("name", "ZmalaPhone.apk").put("state", "uploaded")
            .put("size", apk.length()).put("digest", "sha256:" + AppUpdates.hex(digest.digest()))
            .put("browser_download_url", UpdatePolicy.DOWNLOAD + "v" + version + "/ZmalaPhone.apk"))).toString();
    java.util.concurrent.atomic.AtomicInteger downloads = new java.util.concurrent.atomic.AtomicInteger();
    URL.setURLStreamHandlerFactory(protocol -> !protocol.equals("https") ? null : new URLStreamHandler() {
      @Override protected URLConnection openConnection(URL url) {
        return new HttpURLConnection(url) {
          public void connect() {}
          public void disconnect() {}
          public boolean usingProxy() { return false; }
          public int getResponseCode() { return 200; }
          public InputStream getInputStream() throws IOException {
            if (url.toString().equals(UpdatePolicy.API)) return new ByteArrayInputStream(metadata.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            if (!url.toString().equals(UpdatePolicy.DOWNLOAD + "v" + version + "/ZmalaPhone.apk")) throw new IOException("Unexpected URL");
            downloads.incrementAndGet(); return new FileInputStream(apk);
          }
        };
      }
    });
    c.getSharedPreferences("updates", 0).edit().clear().putLong("later_until", System.currentTimeMillis() + 86400000).commit();
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip(); PhoneFixture.Http http = new PhoneFixture.Http(PhoneFixture.config(sip.port()))) {
      File enrollment = new File(c.getNoBackupFilesDir(), "enrollment.json");
      Files.writeString(enrollment.toPath(), PhoneFixture.qr(http.port(), "app"));
      Files.writeString(new File(c.getExternalFilesDir(null), "expected-enrollment.txt").toPath(), Files.readString(enrollment.toPath()));
      MainActivity screen = activity.launchActivity(null);
      PhoneFixture.waitFor(() -> PhoneFixture.enabledText(screen, "Living room"));
      PhoneFixture.waitFor(() -> c.getSharedPreferences("updates", 0).getString("release", "").contains(version));
      sip.ringOutgoing = true;
      PhoneFixture.click(screen, "Living room");
      assertNotNull(sip.invites.poll(10, TimeUnit.SECONDS));
      java.lang.reflect.Method download = AppUpdates.class.getDeclaredMethod("startDownload"); download.setAccessible(true);
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
        try { download.invoke(AppUpdates.get(c)); } catch (Exception error) { throw new AssertionError(error); }
      });
      assertEquals(0, downloads.get());
      Files.writeString(new File(c.getExternalFilesDir(null), "call-exclusion.txt").toPath(), "APK transfer refused during native call");
      PhoneFixture.click(screen, "Remote video. Tap to show call controls.");
      PhoneFixture.click(screen, "End call");
      PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Updates"));
      c.getSharedPreferences("updates", 0).edit().remove("later_until").putBoolean("automatic", true).commit();
      // Allow the production 30-second idle timer; the installer will terminate this test process.
      Thread.sleep(90000);
      fail("Expected process replacement by Android installer; host must check installed version");
    }
  }
}
