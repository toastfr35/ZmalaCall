// @test A-LLT-021
// @requirements LLR-AND-CALL-006
// @environment portable
// @plan Classify network/timeouts versus revoked access, invalid identity/security data and malformed JSON.
// @pass Only transport failures qualify for preserving an active call through configuration polling errors.
package org.zmala.phone;
import static org.junit.Assert.*;
import org.junit.Test;
public class RecoveryPolicyTest {
  @Test public void transportRecoveryNeverMasksRevocationOrInvalidConfiguration() {
    assertTrue(ServerApi.temporaryFailure(new java.io.IOException()));
    assertTrue(ServerApi.temporaryFailure(new java.net.SocketTimeoutException()));
    assertFalse(ServerApi.temporaryFailure(new ServerApi.AccessRevoked()));
    assertFalse(ServerApi.temporaryFailure(new IllegalArgumentException("Invalid security policy")));
    assertFalse(ServerApi.temporaryFailure(new org.json.JSONException("Invalid contact")));
    assertFalse(ServerApi.temporaryFailure(null));
  }
}
