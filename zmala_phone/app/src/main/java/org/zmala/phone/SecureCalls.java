package org.zmala.phone;

import android.content.Context;
import java.io.File;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.security.KeyStore;
import java.security.cert.X509Certificate;
import java.util.Base64;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;
import org.json.JSONObject;
import org.linphone.core.*;

// @llr LLR-AND-CALL-006
/** Encrypted server relay policy; trust comes from Android, never the QR or server response. */
final class SecureCalls {
  private static final String HOST = "[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}";

  static JSONObject validate(JSONObject config, long now) throws Exception {
    String proxy = config.getJSONObject("sip").getString("proxy");
    if (!config.has("secure_calls")) {
      if (!proxy.matches("sip:" + HOST + ":[0-9]{1,5};transport=udp"))
        throw new IllegalArgumentException("Invalid local calling transport.");
      endpoint(proxy.substring(4, proxy.indexOf(';')));
      return null;
    }
    JSONObject policy = config.getJSONObject("secure_calls");
    if (!"tls-relay".equals(policy.optString("mode"))
        || !proxy.matches("sip:" + HOST + ":[0-9]{1,5};transport=tls"))
      throw new IllegalArgumentException("Secure calls require SIP TLS.");
    endpoint(proxy.substring(4, proxy.indexOf(';')));
    endpoint(policy.getString("turn_server"));
    for (String field : new String[] {"turn_username", "turn_password", "turn_realm"}) {
      String value = policy.getString(field);
      if (value.isEmpty()
          || value.length() > 512
          || value.chars().anyMatch(c -> c <= 32 || c == 127))
        throw new IllegalArgumentException("Invalid relay credentials.");
    }
    Object expires = policy.get("expires");
    if (!(expires instanceof Integer || expires instanceof Long)
        || ((Number) expires).longValue() <= now)
      throw new IllegalArgumentException("Relay credentials expired. Reconnect to your server.");
    return policy;
  }

  private static void endpoint(String value) {
    if (!value.matches(HOST + ":[0-9]{1,5}"))
      throw new IllegalArgumentException("Invalid encrypted relay endpoint.");
    int port = Integer.parseInt(value.substring(value.lastIndexOf(':') + 1));
    if (port < 1 || port > 65535) throw new IllegalArgumentException("Invalid relay port.");
  }

  static String settings(JSONObject config) throws Exception {
    return config.getJSONObject("sip").toString() + "\n" + config.optJSONObject("secure_calls");
  }

  static void configure(Core core, JSONObject config, Context context) throws Exception {
    JSONObject policy = validate(config, System.currentTimeMillis() / 1000);
    NatPolicy nat = core.createNatPolicy();
    boolean secure = policy != null;
    nat.setIceEnabled(secure);
    nat.setStunEnabled(secure);
    nat.setTurnEnabled(secure);
    nat.setUdpTurnTransportEnabled(false);
    nat.setTcpTurnTransportEnabled(false);
    nat.setTlsTurnTransportEnabled(secure);
    core.setMediaEncryption(secure ? MediaEncryption.SRTP : MediaEncryption.None);
    core.setMediaEncryptionMandatory(secure);
    core.setForcedIceRelayEnabled(secure);
    Transports transports = core.getTransports();
    transports.setUdpPort(secure ? 0 : -1);
    transports.setTcpPort(0);
    transports.setTlsPort(secure ? -1 : 0);
    transports.setDtlsPort(0);
    if (core.setTransports(transports) != 0)
      throw new IllegalStateException("Cannot configure call transport.");
    if (secure) {
      // TURN's native TLS client consumes a path, while SIP also accepts PEM data.
      // Give both stacks the same OS-derived trust store before starting the core.
      File roots = new File(context.getNoBackupFilesDir(), "android-roots.pem");
      File staged = new File(context.getNoBackupFilesDir(), "android-roots.pem.tmp");
      Files.write(staged.toPath(), androidRoots().getBytes(java.nio.charset.StandardCharsets.US_ASCII));
      Files.move(
          staged.toPath(),
          roots.toPath(),
          StandardCopyOption.ATOMIC_MOVE,
          StandardCopyOption.REPLACE_EXISTING);
      core.setRootCa(roots.getAbsolutePath());
      core.verifyServerCertificates(true);
      core.verifyServerCn(true);
      nat.setStunServer(policy.getString("turn_server"));
      nat.setStunServerUsername(policy.getString("turn_username"));
      core.addAuthInfo(
          Factory.instance()
              .createAuthInfo(
                  policy.getString("turn_username"),
                  null,
                  policy.getString("turn_password"),
                  null,
                  policy.getString("turn_realm"),
                  null));
    }
    core.setNatPolicy(nat);
  }

  private static String androidRoots() throws Exception {
    TrustManagerFactory factory =
        TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
    factory.init((KeyStore) null);
    StringBuilder pem = new StringBuilder();
    for (TrustManager manager : factory.getTrustManagers()) {
      if (manager instanceof X509TrustManager) {
        for (X509Certificate cert : ((X509TrustManager) manager).getAcceptedIssuers()) {
          pem.append("-----BEGIN CERTIFICATE-----\n")
              .append(
                  Base64.getMimeEncoder(64, new byte[] {'\n'}).encodeToString(cert.getEncoded()))
              .append("\n-----END CERTIFICATE-----\n");
        }
      }
    }
    if (pem.length() == 0)
      throw new IllegalStateException("No trusted Android certificates available.");
    return pem.toString();
  }
}
