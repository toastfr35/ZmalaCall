package org.zmala.phone;

import android.content.Context;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.json.JSONArray;

public final class PushFixture {
  public static Map<String, String> message(String id, String event, long expires)
      throws Exception {
    Map<String, String> data = new HashMap<>();
    data.put("event", event);
    data.put("call_id", id);
    data.put("caller", "term1");
    data.put("expires", String.valueOf(expires));
    data.put("device_id", PhoneFixture.ID);
    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(new SecretKeySpec(PhoneFixture.TOKEN.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
    byte[] digest =
        mac.doFinal(
            new JSONArray()
                .put(event)
                .put(id)
                .put("term1")
                .put(String.valueOf(expires))
                .put(PhoneFixture.ID)
                .toString()
                .getBytes(StandardCharsets.UTF_8));
    StringBuilder proof = new StringBuilder();
    for (byte b : digest) proof.append(String.format(Locale.ROOT, "%02x", b & 255));
    data.put("proof", proof.toString());
    return data;
  }

  public static void enroll(Context context, int port) throws Exception {
    Files.write(
        new File(context.getNoBackupFilesDir(), "enrollment.json").toPath(),
        PhoneFixture.qr(port, "app").getBytes(StandardCharsets.UTF_8));
    context.getSharedPreferences("push", 0).edit().clear().commit();
    PushAlerts.remember(context, PhoneFixture.config(5060));
  }
}
