// @test A-LLT-009
// @requirements LLR-AND-CALL-006
// @environment portable
// @plan Validate HTTPS secure enrollment, both default 443 and distinct TLS ports, malformed endpoints, missing or expired credentials, unsupported transport and HTTP downgrade. Compare applied settings across hourly relay credential renewal and directory-only updates.
// @pass Invalid policies are rejected, valid profiles retain TLS on the selected ports, and only transport/credential changes require a new core. No native handshakes or media are inferred.
package org.zmala.phone;

import static org.junit.Assert.*;

import org.json.JSONObject;
import org.junit.Test;

public class SecureCallsTest {
  static JSONObject secure() throws Exception {
    JSONObject config = EnrollmentTest.config();
    config.getJSONObject("sip").put("proxy", "sip:zmala.example.org:5061;transport=tls");
    return config.put(
        "secure_calls",
        new JSONObject()
            .put("mode", "tls-relay")
            .put("turn_server", "zmala.example.org:5349")
            .put("turn_username", "2000:phone1")
            .put("turn_password", "secret")
            .put("turn_realm", "zmala.example.org")
            .put("expires", 2000));
  }

  @Test
  public void validationAndEnrollmentBoundaries() throws Exception {
    assertNotNull(SecureCalls.validate(secure(), 1000));
    JSONObject ports443 = secure();
    ports443.getJSONObject("sip").put("proxy", "sip:zmala.example.org:443;transport=tls");
    ports443.getJSONObject("secure_calls").put("turn_server", "zmala.example.org:443");
    assertNotNull(SecureCalls.validate(ports443, 1000));
    assertNull(SecureCalls.validate(EnrollmentTest.config(), 1000));
    for (String endpoint :
        new String[] {
          "host:0", "host:65536", "host:1;transport=udp", "user@host:443", "https://host:443"
        }) {
      JSONObject bad = secure();
      bad.getJSONObject("secure_calls").put("turn_server", endpoint);
      assertThrows(Exception.class, () -> SecureCalls.validate(bad, 1000));
    }
    for (Object expiry : new Object[] {1000, 999, true, "2000", 2000.5}) {
      JSONObject bad = secure();
      bad.getJSONObject("secure_calls").put("expires", expiry);
      assertThrows(Exception.class, () -> SecureCalls.validate(bad, 1000));
    }
    for (String field : new String[] {"turn_username", "turn_password", "turn_realm"}) {
      JSONObject bad = secure();
      bad.getJSONObject("secure_calls").put(field, "a\nb");
      assertThrows(Exception.class, () -> SecureCalls.validate(bad, 1000));
    }
    JSONObject bad = secure();
    bad.remove("secure_calls");
    assertThrows(Exception.class, () -> SecureCalls.validate(bad, 1000));
    JSONObject downgrade = secure();
    downgrade.getJSONObject("sip").put("proxy", "sip:host:5060;transport=udp");
    assertThrows(Exception.class, () -> SecureCalls.validate(downgrade, 1000));
    JSONObject current = secure();
    current.getJSONObject("secure_calls").put("expires", System.currentTimeMillis() / 1000 + 3600);
    Enrollment http = new Enrollment(EnrollmentTest.qr().toString());
    assertThrows(Exception.class, () -> http.validate(current));
    Enrollment https =
        new Enrollment(
            EnrollmentTest.qr().put("server_url", "https://zmala.example.org").toString());
    assertSame(current, https.validate(current));
  }

  @Test
  public void renewalChangesTransportKeyButDirectoryDoesNot() throws Exception {
    JSONObject config = secure();
    String key = SecureCalls.settings(config);
    config.put("contacts", new org.json.JSONArray().put(new JSONObject().put("id", "term1")));
    assertEquals(key, SecureCalls.settings(config));
    config.getJSONObject("secure_calls").put("turn_password", "new-hour");
    assertNotEquals(key, SecureCalls.settings(config));
  }
}
