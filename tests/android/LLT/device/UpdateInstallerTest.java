// @test A-LLT-016
// @requirements LLR-AND-UPDATE-002
// @environment native-sdk
// @plan Use Android PackageManager on the installed app APK, instrumentation APK and corrupt bytes
// through the production verification method. Deliver a forged unmatched installer-result ID.
// @pass Reinstall/downgrade, wrong package and unreadable archive are rejected before session commit;
// an unrelated callback cannot acquire or release the installation gate.
package org.zmala.phone;

import static org.junit.Assert.*;
import android.content.*;
import android.content.pm.PackageInstaller;
import java.io.File;
import java.lang.reflect.*;
import java.nio.file.Files;
import org.json.*;
import org.junit.Test;

public class UpdateInstallerTest {
  @Test public void archivesAndCallbacksFailClosed() throws Exception {
    Context c = PhoneFixture.INSTRUMENTATION.getTargetContext();
    AppUpdates updater = AppUpdates.get(c);
    String next = "99.0.0";
    UpdatePolicy release = UpdatePolicy.parse(new JSONObject().put("tag_name", "v" + next)
        .put("draft", false).put("prerelease", false).put("assets", new JSONArray().put(
            new JSONObject().put("name", "ZmalaPhone.apk").put("state", "uploaded").put("size", 100)
                .put("digest", "sha256:" + "a".repeat(64))
                .put("browser_download_url", UpdatePolicy.DOWNLOAD + "v" + next + "/ZmalaPhone.apk"))).toString(), updater.version());
    Method verify = AppUpdates.class.getDeclaredMethod("verify", File.class, UpdatePolicy.class);
    verify.setAccessible(true);
    File corrupt = new File(c.getCacheDir(), "bad-update.apk");
    Files.write(corrupt.toPath(), new byte[]{0, 1, 2});
    try {
      for (File file : new File[]{new File(c.getApplicationInfo().sourceDir),
          new File(PhoneFixture.INSTRUMENTATION.getContext().getApplicationInfo().sourceDir), corrupt}) {
        try { verify.invoke(updater, file, release); fail("Unacceptable archive accepted"); }
        catch (InvocationTargetException expected) { assertTrue(expected.getCause() instanceof java.io.IOException); }
      }
      boolean before = UpdateGate.INSTANCE.installing();
      updater.result(new Intent().putExtra(PackageInstaller.EXTRA_SESSION_ID, Integer.MAX_VALUE)
          .putExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_SUCCESS));
      assertEquals(before, UpdateGate.INSTANCE.installing());
    } finally { Files.deleteIfExists(corrupt.toPath()); }
  }
}
