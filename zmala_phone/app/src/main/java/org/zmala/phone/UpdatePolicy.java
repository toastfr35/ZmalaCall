package org.zmala.phone;

import java.net.URI;
import java.util.Arrays;
import org.json.JSONArray;
import org.json.JSONObject;

// @llr LLR-AND-UPDATE-002
/** Public release metadata is a hint; package identity and signature are checked separately. */
final class UpdatePolicy {
  static final String API = "https://api.github.com/repos/toastfr35/ZmalaCall/releases/latest";
  static final String DOWNLOAD = "https://github.com/toastfr35/ZmalaCall/releases/download/";
  static final long MAX_APK = 512L * 1024 * 1024;
  final String version, url, digest;
  final long size;

  private UpdatePolicy(String version, String url, String digest, long size) {
    this.version = version; this.url = url; this.digest = digest; this.size = size;
  }

  static int compare(String left, String right) {
    if (!left.matches("[0-9]{1,6}\\.[0-9]{1,6}\\.[0-9]{1,6}")
        || !right.matches("[0-9]{1,6}\\.[0-9]{1,6}\\.[0-9]{1,6}"))
      throw new IllegalArgumentException("Unsupported release version");
    String[] a = left.split("\\."), b = right.split("\\.");
    for (int i = 0; i < 3; i++) {
      int difference = Integer.compare(Integer.parseInt(a[i]), Integer.parseInt(b[i]));
      if (difference != 0) return difference;
    }
    return 0;
  }

  static UpdatePolicy parse(String json, String installed) throws Exception {
    JSONObject release = new JSONObject(json);
    if (release.getBoolean("draft") || release.getBoolean("prerelease")) return null;
    String tag = release.getString("tag_name");
    if (!tag.startsWith("v")) throw new IllegalArgumentException("Invalid release tag");
    String version = tag.substring(1);
    if (compare(version, installed) <= 0) return null;
    JSONArray assets = release.getJSONArray("assets");
    UpdatePolicy result = null;
    for (int i = 0; i < assets.length(); i++) {
      JSONObject asset = assets.getJSONObject(i);
      if (!"ZmalaPhone.apk".equals(asset.optString("name"))) continue;
      if (result != null) throw new IllegalArgumentException("Duplicate APK");
      String url = asset.getString("browser_download_url"), digest = asset.getString("digest");
      long size = asset.getLong("size");
      if (!url.equals(DOWNLOAD + tag + "/ZmalaPhone.apk")
          || !"uploaded".equals(asset.getString("state"))
          || !digest.matches("sha256:[a-fA-F0-9]{64}") || size <= 0 || size > MAX_APK)
        throw new IllegalArgumentException("Invalid release asset");
      result = new UpdatePolicy(version, url, digest.substring(7).toLowerCase(java.util.Locale.ROOT), size);
    }
    if (result == null) throw new IllegalArgumentException("Release has no Android download");
    return result;
  }

  static boolean allowedDownload(URI uri) {
    return "https".equals(uri.getScheme()) && uri.getUserInfo() == null
        && (uri.getPort() == -1 || uri.getPort() == 443)
        && Arrays.asList("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")
            .contains(uri.getHost());
  }

  static boolean validPackage(String packageName, String version, long code, long installedCode,
      boolean debuggable, byte[][] signers, byte[][] installedSigners, String expectedVersion) {
    return "org.zmala.phone".equals(packageName) && expectedVersion.equals(version)
        && code > installedCode && !debuggable && signers != null && installedSigners != null
        && signers.length == 1 && installedSigners.length == 1
        && java.security.MessageDigest.isEqual(signers[0], installedSigners[0]);
  }
}
