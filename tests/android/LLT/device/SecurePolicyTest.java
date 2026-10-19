// @test A-LLT-010
// @requirements LLR-AND-CALL-006
// @environment native-sdk
// @plan Configure a real native core with the secure profile, inspect TLS-only SIP and TURN, forced ICE relay, certificate/name checks, a private OS-derived CA file shared by both TLS stacks, and mandatory SRTP. Renew the profile while refreshing the directory and verify the applied transport stays unchanged until an idle restart. Reject expired policy before native startup. Verify LAN mode separately retains UDP without ICE.
// @pass Native policy is encrypted and relay-only, renewal remains pending after directory refresh, invalid policy cannot start, and LAN behavior is retained. This test does not qualify remote TLS handshakes or media.
package org.zmala.phone;

import static org.junit.Assert.*;

import org.json.JSONObject;
import org.junit.Test;
import org.linphone.core.*;

public class SecurePolicyTest {
  @Test
  public void nativePolicyAndPendingRenewal() throws Exception {
    PhoneFixture.INSTRUMENTATION.runOnMainSync(
        () -> {
          CallEngine engine = new CallEngine(status -> {});
          try {
            JSONObject config = PhoneFixture.config(5061);
            config.getJSONObject("sip").put("proxy", "sip:127.0.0.1:5061;transport=tls");
            config.put(
                "secure_calls",
                new JSONObject()
                    .put("mode", "tls-relay")
                    .put("turn_server", "127.0.0.1:5349")
                    .put("turn_username", "test:phone1")
                    .put("turn_password", "test-secret")
                    .put("turn_realm", "test")
                    .put("expires", System.currentTimeMillis() / 1000 + 3600));
            engine.start(PhoneFixture.INSTRUMENTATION.getTargetContext(), config);
            java.lang.reflect.Field field = CallEngine.class.getDeclaredField("core");
            field.setAccessible(true);
            Core core = (Core) field.get(engine);
            assertTrue(core.isVerifyServerCertificates());
            assertTrue(core.isVerifyServerCn());
            java.nio.file.Path roots = new java.io.File(core.getRootCa()).toPath();
            assertEquals(
                PhoneFixture.INSTRUMENTATION.getTargetContext().getNoBackupFilesDir().toPath(),
                roots.getParent());
            assertTrue(
                new String(java.nio.file.Files.readAllBytes(roots), java.nio.charset.StandardCharsets.US_ASCII).contains("-----BEGIN CERTIFICATE-----"));
            assertTrue(core.isMediaEncryptionMandatory());
            assertEquals(MediaEncryption.SRTP, core.getMediaEncryption());
            assertTrue(core.isForcedIceRelayEnabled());
            assertEquals(0, core.getTransports().getUdpPort());
            assertEquals(0, core.getTransports().getTcpPort());
            assertNotEquals(0, core.getTransportsUsed().getTlsPort());
            NatPolicy nat = core.getNatPolicy();
            assertTrue(nat.isIceEnabled());
            assertTrue(nat.isTurnEnabled());
            assertTrue(nat.isTlsTurnTransportEnabled());
            assertFalse(nat.isUdpTurnTransportEnabled());
            assertFalse(nat.isTcpTurnTransportEnabled());
            assertEquals("127.0.0.1:5349", nat.getStunServer());
            assertFalse(engine.requiresRestart(config));
            JSONObject renewed = new JSONObject(config.toString());
            renewed.getJSONObject("secure_calls").put("turn_password", "renewed-secret");
            assertTrue(engine.requiresRestart(renewed));
            engine.refresh(renewed);
            assertSame(core, field.get(engine));
            assertTrue(engine.requiresRestart(renewed));
            engine.start(PhoneFixture.INSTRUMENTATION.getTargetContext(), renewed);
            assertFalse(engine.requiresRestart(renewed));
            JSONObject expired = new JSONObject(renewed.toString());
            expired.getJSONObject("secure_calls").put("expires", 1);
            assertThrows(
                Exception.class,
                () -> engine.start(PhoneFixture.INSTRUMENTATION.getTargetContext(), expired));
            engine.start(
                PhoneFixture.INSTRUMENTATION.getTargetContext(), PhoneFixture.config(5060));
            Core lan = (Core) field.get(engine);
            assertFalse(lan.getNatPolicy().isIceEnabled());
            assertFalse(lan.isMediaEncryptionMandatory());
            assertEquals(MediaEncryption.None, lan.getMediaEncryption());
          } catch (Exception error) {
            throw new AssertionError(error);
          } finally {
            engine.stop();
          }
        });
  }
}
