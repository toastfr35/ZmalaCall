// @test A-LLT-002
// @requirements LLR-AND-CALL-002
// @environment portable
// @plan Compute an independent incoming proof, then vary the caller, domain, call ID, permitted
// direction and proof to test admission and replay binding.
// @pass Only the permitted caller with matching domain, call ID and proof is admitted.
package org.zmala.phone;

import static org.junit.Assert.*;

import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.json.*;
import org.junit.Test;

public class CallAdmissionTest {
  @Test
  public void proofBindsCallerCallAndDirectory() throws Exception {
    JSONObject c = EnrollmentTest.config();
    c.put(
        "contacts",
        new JSONArray().put(new JSONObject().put("id", "term1").put("can_receive", true)));
    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(
        new SecretKeySpec(EnrollmentTest.TOKEN.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
    String proof =
        HexFormat.of().formatHex(mac.doFinal("call-1:term1".getBytes(StandardCharsets.UTF_8)));
    assertTrue(Enrollment.allowedIncoming(c, "term1", "localhost", "call-1", proof));
    assertFalse(Enrollment.allowedIncoming(c, "term1", "foreign", "call-1", proof));
    assertFalse(Enrollment.allowedIncoming(c, "outsider", "localhost", "call-1", proof));
    assertFalse(Enrollment.allowedIncoming(c, "term1", "localhost", "call-2", proof));
    assertFalse(Enrollment.allowedIncoming(c, "term1", "localhost", "call-1", "0".repeat(64)));
    c.getJSONArray("contacts").getJSONObject(0).put("can_receive", false);
    assertFalse(Enrollment.allowedIncoming(c, "term1", "localhost", "call-1", proof));
  }
}
