// @test A-HLT-002
// @requirements HLR-AND-CALL-001
// @environment native-sdk
// @plan Register the native Android call engine with a disposable SIP peer, send a forged incoming
// INVITE then a signed allowed caller, answer it and inspect the native video answer, hang up and
// stop. No RTP quality or physical Pi interoperability is inferred.
// @pass Forged calls never become current, valid signed calls can be answered with video and
// terminated, and stop clears state.
package org.zmala.phone;

import static org.junit.Assert.*;

import android.Manifest;
import androidx.test.rule.GrantPermissionRule;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.*;

public class NativeCallingTest {
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

  @Test
  public void incomingAdmissionAndAnswer() throws Exception {
    CallEngine engine = new CallEngine(status -> {});
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip()) {
      org.json.JSONObject config = PhoneFixture.config(sip.port());
      PhoneFixture.INSTRUMENTATION.runOnMainSync(
          () -> {
            try {
              engine.start(PhoneFixture.INSTRUMENTATION.getTargetContext(), config);
            } catch (Exception e) {
              throw new AssertionError(e);
            }
          });
      PhoneFixture.waitFor(() -> engine.registered);
      sip.incoming("forged", "0".repeat(64));
      String rejected = null;
      long end = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
      while (System.nanoTime() < end) {
        String r = sip.responses.poll(1, TimeUnit.SECONDS);
        if (r != null && r.startsWith("SIP/2.0 603")) {
          rejected = r;
          break;
        }
      }
      assertNotNull("Forged INVITE must be declined", rejected);
      assertNull(engine.call);
      Mac mac = Mac.getInstance("HmacSHA256");
      mac.init(
          new SecretKeySpec(PhoneFixture.TOKEN.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
      StringBuilder proof = new StringBuilder();
      for (byte b : mac.doFinal("allowed:term1".getBytes(StandardCharsets.UTF_8)))
        proof.append(String.format("%02x", b & 255));
      sip.incoming("allowed", proof.toString());
      PhoneFixture.waitFor(() -> engine.call != null);
      PhoneFixture.INSTRUMENTATION.runOnMainSync(engine::answer);
      String answer = null;
      end = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
      while (System.nanoTime() < end) {
        String r = sip.responses.poll(1, TimeUnit.SECONDS);
        if (r != null && r.startsWith("SIP/2.0 200") && r.contains("m=video ")) {
          answer = r;
          break;
        }
      }
      assertNotNull("Accepted call must answer with video SDP", answer);
      PhoneFixture.INSTRUMENTATION.runOnMainSync(engine::hangup);
      PhoneFixture.waitFor(() -> engine.call == null);
    } finally {
      PhoneFixture.INSTRUMENTATION.runOnMainSync(engine::stop);
    }
    assertFalse(engine.registered);
    assertNull(engine.call);
  }
}
