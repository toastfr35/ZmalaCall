// @test A-LLT-014
// @requirements LLR-AND-UPDATE-002
// @environment portable
// @plan Parse stable, draft, old, malformed, duplicate and oversized release assets. Reject foreign
// download origins, credentials and cleartext redirects. Compare signed-package identity, version,
// debug flags and signer bytes. Interleave ringing, call start/end and installation reservations.
// Recheck automatic eligibility after interaction during staging, permission/network changes
// and clock reset, including the exact 30-second idle boundary.
// @pass Only a newer stable exact APK with bounded size and SHA256 is selected; invalid packages
// are rejected. A ring or active call prevents commit, and committed installation prevents a new call.
// Automatic eligibility is lost on interaction and returns only after thirty new idle seconds.
package org.zmala.phone;

import static org.junit.Assert.*;
import java.net.URI;
import org.json.*;
import org.junit.Test;

public class UpdatePolicyTest {
  @Test public void automaticCommitRequiresFreshIdleWindow() {
    assertFalse(UpdatePolicy.automaticReady(true, true, false, 39999, 10000));
    assertTrue(UpdatePolicy.automaticReady(true, true, false, 40000, 10000));
    assertFalse(UpdatePolicy.automaticReady(true, true, false, 40000, 39999));
    assertFalse(UpdatePolicy.automaticReady(false, true, false, 40000, 10000));
    assertFalse(UpdatePolicy.automaticReady(true, false, false, 40000, 10000));
    assertFalse(UpdatePolicy.automaticReady(true, true, true, 40000, 10000));
    assertFalse(UpdatePolicy.automaticReady(true, true, false, 1000, 10000));
  }
  JSONObject release() throws Exception {
    return new JSONObject().put("tag_name", "v0.3.8").put("draft", false).put("prerelease", false)
        .put("assets", new JSONArray().put(new JSONObject().put("name", "ZmalaPhone.apk")
            .put("browser_download_url", UpdatePolicy.DOWNLOAD + "v0.3.8/ZmalaPhone.apk")
            .put("digest", "sha256:" + "a".repeat(64)).put("state", "uploaded").put("size", 100)));
  }
  @Test public void onlyNewStableExactAssets() throws Exception {
    assertEquals("0.3.8", UpdatePolicy.parse(release().toString(), "0.3.7").version);
    assertNull(UpdatePolicy.parse(release().toString(), "0.3.8"));
    assertNull(UpdatePolicy.parse(release().toString(), "0.4.0"));
    assertNull(UpdatePolicy.parse(release().put("prerelease", true).toString(), "0.3.7"));
    assertNull(UpdatePolicy.parse(release().put("draft", true).toString(), "0.3.7"));
    assertTrue(UpdatePolicy.compare("0.10.0", "0.9.9") > 0);
    assertThrows(IllegalArgumentException.class, () -> UpdatePolicy.compare("0.3.8-rc1", "0.3.7"));
    for (String field : new String[]{"browser_download_url", "digest", "state", "size"}) {
      JSONObject invalid = release();
      invalid.getJSONArray("assets").getJSONObject(0).put(field, field.equals("size") ? UpdatePolicy.MAX_APK + 1 : "bad");
      assertThrows(Exception.class, () -> UpdatePolicy.parse(invalid.toString(), "0.3.7"));
    }
    JSONObject duplicate = release();
    duplicate.getJSONArray("assets").put(duplicate.getJSONArray("assets").getJSONObject(0));
    assertThrows(Exception.class, () -> UpdatePolicy.parse(duplicate.toString(), "0.3.7"));
  }
  @Test public void redirectsAndPackageIdentityFailClosed() {
    assertTrue(UpdatePolicy.allowedDownload(URI.create("https://release-assets.githubusercontent.com/file?token=example")));
    for (String url : new String[]{"http://github.com/file", "https://github.com.evil.test/file", "https://evil.test/file",
        "https://user:password@github.com/file", "https://github.com:8443/file"})
      assertFalse(url, UpdatePolicy.allowedDownload(URI.create(url)));
    byte[][] key = {new byte[]{1, 2, 3}}, wrong = {new byte[]{1, 2, 4}};
    assertTrue(UpdatePolicy.validPackage("org.zmala.phone", "0.3.8", 17, 16, false, key, key, "0.3.8"));
    assertFalse(UpdatePolicy.validPackage("other.app", "0.3.8", 17, 16, false, key, key, "0.3.8"));
    assertFalse(UpdatePolicy.validPackage("org.zmala.phone", "0.3.8", 16, 16, false, key, key, "0.3.8"));
    assertFalse(UpdatePolicy.validPackage("org.zmala.phone", "0.3.8", 17, 16, true, key, key, "0.3.8"));
    assertFalse(UpdatePolicy.validPackage("org.zmala.phone", "0.3.8", 17, 16, false, wrong, key, "0.3.8"));
    assertFalse(UpdatePolicy.validPackage("org.zmala.phone", "0.3.7", 17, 16, false, key, key, "0.3.8"));
  }
  @Test public void callsAndInstallationAreMutuallyExclusive() {
    UpdateGate gate = new UpdateGate();
    assertTrue(gate.ring(500));
    assertFalse(gate.beginInstall(499));
    assertTrue(gate.beginCall());
    assertFalse(gate.beginInstall(501));
    gate.endCall();
    assertTrue(gate.beginInstall(501));
    assertFalse(gate.beginCall());
    assertFalse(gate.ring(900));
    assertFalse(gate.beginInstall(502));
    gate.restoreInstall(false);
    assertTrue(gate.beginCall());
  }
}
