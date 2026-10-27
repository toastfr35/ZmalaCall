// @test A-LLT-007
// @requirements LLR-AND-CALL-004, LLR-AND-HISTORY-003
// @environment portable
// @plan Sign a fixed canonical push payload independently, mutate each authenticated field, and check valid ring/cancel, missing identity/proof, expired and excessively distant deadlines. Queue notification acceptance with a fake main loop and clock; change eligibility or expire authorization before draining it.
// @pass Only a correctly signed, current message for this enrollment is accepted. Media acceptance is deferred beyond the incoming callback and is suppressed when eligibility or authorization expires before execution.
package org.zmala.phone;

import static org.junit.Assert.*;

import java.nio.charset.StandardCharsets;
import java.util.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.Test;

public class PushMessageTest {
  @Test
  public void notificationAnswerLeavesCallbackAndRechecksEligibility() {
    List<Runnable> queue = new ArrayList<>();
    long[] now = {100};
    boolean[] incoming = {true};
    int[] answered = {0};
    PushAnswer.enqueue(queue::add, () -> now[0], 200, () -> incoming[0], () -> answered[0]++);
    assertEquals(0, answered[0]);
    queue.remove(0).run();
    assertEquals(1, answered[0]);

    PushAnswer.enqueue(queue::add, () -> now[0], 200, () -> incoming[0], () -> answered[0]++);
    incoming[0] = false; // Cancellation, a replacement call or activity visibility loss.
    queue.remove(0).run();
    assertEquals(1, answered[0]);
    incoming[0] = true;
    PushAnswer.enqueue(queue::add, () -> now[0], 200, () -> incoming[0], () -> answered[0]++);
    now[0] = 200;
    queue.remove(0).run();
    assertEquals(1, answered[0]);
  }

  @Test
  public void proofAndLifetime() throws Exception {
    Enrollment e = new Enrollment(EnrollmentTest.qr().toString());
    Map<String, String> data = new HashMap<>();
    data.put("event", "ring");
    data.put("call_id", "call-1");
    data.put("caller", "term1");
    data.put("expires", "160000");
    data.put("device_id", e.deviceId);
    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(new SecretKeySpec(e.token.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
    String body = "[\"ring\",\"call-1\",\"term1\",\"160000\",\"" + e.deviceId + "\"]";
    data.put("proof", HexFormat.of().formatHex(mac.doFinal(body.getBytes(StandardCharsets.UTF_8))));
    assertNotNull(PushMessage.verify(e, data, 100000));
    assertNull(PushMessage.verify(e, data, 160000));
    assertNull(PushMessage.verify(e, data, 69999));
    for (String key :
        new String[] {"event", "call_id", "caller", "expires", "device_id", "proof"}) {
      Map<String, String> altered = new HashMap<>(data);
      altered.put(key, "invalid");
      assertNull(key, PushMessage.verify(e, altered, 100000));
      altered.remove(key);
      assertNull(key, PushMessage.verify(e, altered, 100000));
    }
    data.put("event", "cancel");
    data.put(
        "proof",
        HexFormat.of()
            .formatHex(
                mac.doFinal(body.replace("ring", "cancel").getBytes(StandardCharsets.UTF_8))));
    assertEquals("cancel", PushMessage.verify(e, data, 100000).event);
    data.put("event","callback");
    data.put("proof",HexFormat.of().formatHex(mac.doFinal(body.replace("ring","callback").getBytes(StandardCharsets.UTF_8))));
    assertEquals("callback",PushMessage.verify(e,data,100000).event);
    data.put("caller","other");assertNull(PushMessage.verify(e,data,100000));
  }
}
