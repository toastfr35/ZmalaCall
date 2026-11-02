package org.zmala.phone;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.function.Predicate;

// @llr LLR-AND-ENROLL-002, LLR-AND-CALL-006
/** Screen-work identity and enrollment storage, independent of Android views. */
final class SetupCoordinator {
  private final File file;
  private int generation;
  private boolean fetching;
  SetupCoordinator(File file) { this.file = file; }
  int ticket() { return generation; }
  boolean current(int ticket) { return ticket == generation; }
  void invalidate() { generation++; fetching = false; }
  boolean fetching() { return fetching; }
  void fetching(boolean value) { fetching = value; }
  boolean enrolled() { return file.isFile(); }
  Enrollment load() throws Exception {
    return new Enrollment(new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8));
  }
  void remember(Enrollment enrollment) throws Exception {
    Files.write(file.toPath(), enrollment.serialized().getBytes(StandardCharsets.UTF_8));
  }
  org.json.JSONObject configuration(Enrollment enrollment) throws Exception {
    return ServerApi.configuration(enrollment);
  }
  static String[] permissions(int sdk) {
    return sdk >= 37 ? new String[]{"android.permission.CAMERA", "android.permission.RECORD_AUDIO", "android.permission.ACCESS_LOCAL_NETWORK"}
        : new String[]{"android.permission.CAMERA", "android.permission.RECORD_AUDIO"};
  }
  static boolean granted(int sdk, Predicate<String> granted) {
    for (String permission : permissions(sdk)) if (!granted.test(permission)) return false;
    return true;
  }
}
