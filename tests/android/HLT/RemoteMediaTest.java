// @test A-HLT-006
// @requirements HLR-AND-CALL-005
// @environment hardware
// @plan Opt in with realNetwork=true on an already enrolled physical phone using validated cellular internet with Wi-Fi off, and supply a permitted auto-answering Pi contact. Launch the real activity without replacing enrollment or configuration, dial that contact or use direction=incoming with the native terminal-peer helper, and sample native media for 20 seconds after StreamsRunning. Require mandatory SRTP, relay ICE for both streams, bidirectional audio/video traffic and repeated decoded video callbacks. Re-arm the one-shot callback during sampling because ICE renegotiation can replace the decoder. Assert the corrected TURN reader and writer process live traffic. The incoming native Pi helper also asserts at least ten samples of decoded video and bidirectional audio/video traffic. Hang up in finally and compare enrollment bytes. This test makes a real call and is excluded unless explicitly selected and opted in.
// @pass The call uses cellular connectivity, SRTP and relay ICE; multiple samples show bidirectional audio/video bandwidth and fresh decoded frames; hangup clears the call and enrollment is unchanged. This proves media transport and video decoding, not audible speech quality, moving-camera quality or incoming push.
package org.zmala.phone;

import static org.junit.Assert.*;
import static org.junit.Assume.assumeTrue;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.os.Bundle;
import android.provider.Settings;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.rule.ActivityTestRule;
import java.io.File;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Rule;
import org.junit.Test;
import org.linphone.core.*;

public class RemoteMediaTest {
  @Rule
  public ActivityTestRule<MainActivity> activity =
      new ActivityTestRule<>(MainActivity.class, false, false);

  private void main(Runnable action) {
    InstrumentationRegistry.getInstrumentation().runOnMainSync(action);
  }

  private void waitFor(BooleanSupplier condition, int seconds) throws Exception {
    long end = System.nanoTime() + seconds * 1_000_000_000L;
    boolean[] done = {false};
    while (System.nanoTime() < end) {
      main(() -> done[0] = condition.getAsBoolean());
      if (done[0]) return;
      Thread.sleep(100);
    }
    fail("Timed out waiting for real call state");
  }

  @Test
  public void cellularRelayMedia() throws Exception {
    Bundle args = InstrumentationRegistry.getArguments();
    assumeTrue(
        "Explicit real-device opt-in required", "true".equals(args.getString("realNetwork")));
    Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    assertEquals(0, Settings.Global.getInt(context.getContentResolver(), "wifi_on"));
    ConnectivityManager cm =
        (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
    NetworkCapabilities network = cm.getNetworkCapabilities(cm.getActiveNetwork());
    assertNotNull(network);
    assertTrue(network.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR));
    assertTrue(network.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED));
    File enrollment = new File(context.getNoBackupFilesDir(), "enrollment.json");
    byte[] original = Files.readAllBytes(enrollment.toPath());
    Enrollment account =
        new Enrollment(new String(original, java.nio.charset.StandardCharsets.UTF_8));
    assertEquals("https", account.server.getScheme());
    JSONObject config = ServerApi.configuration(account);
    assertEquals("tls-relay", config.getJSONObject("secure_calls").getString("mode"));
    JSONObject contact = null;
    for (int i = 0; i < config.getJSONArray("contacts").length(); i++) {
      JSONObject candidate = config.getJSONArray("contacts").getJSONObject(i);
      if (candidate.getString("id").equals(args.getString("contact"))) contact = candidate;
    }
    assertNotNull("Choose an existing permitted contact", contact);
    if (!"incoming".equals(args.getString("direction"))) assertTrue(contact.getBoolean("online"));
    MainActivity screen = activity.launchActivity(null);
    Field field = MainActivity.class.getDeclaredField("engine");
    field.setAccessible(true);
    CallEngine engine = (CallEngine) field.get(screen);
    JSONArray samples = new JSONArray();
    AtomicInteger frames = new AtomicInteger();
    try {
      waitFor(() -> engine.registered, 30);
      main(() -> assertNull("Do not interrupt an existing call", engine.call));
      JSONObject selected = contact;
      if ("incoming".equals(args.getString("direction"))) {
        waitFor(
            () -> engine.call != null && engine.call.getState() == Call.State.IncomingReceived, 90);
        main(
            () -> {
              assertEquals(args.getString("contact"), engine.call.getRemoteAddress().getUsername());
              engine.answer();
            });
      } else {
        main(
            () -> {
              try {
                engine.dial(selected);
              } catch (Exception e) {
                throw new AssertionError(e);
              }
            });
      }
      waitFor(() -> engine.call != null && engine.call.getState() == Call.State.StreamsRunning, 60);
      main(
          () -> {
            engine.call.addListener(
                new CallListenerStub() {
                  @Override
                  public void onNextVideoFrameDecoded(Call call) {
                    frames.incrementAndGet();
                    call.requestNotifyNextVideoFrameDecoded();
                  }
                });
            engine.call.requestNotifyNextVideoFrameDecoded();
          });
      int good = 0;
      for (int i = 0; i < 20; i++) {
        Thread.sleep(1000);
        boolean[] valid = {false};
        main(
            () -> {
              assertNotNull("Call ended unexpectedly", engine.call);
              Call call = engine.call;
              assertEquals(MediaEncryption.SRTP, call.getCurrentParams().getMediaEncryption());
              CallStats audio = call.getAudioStats(), video = call.getVideoStats();
              call.requestNotifyNextVideoFrameDecoded();
              try {
                JSONObject sample =
                    new JSONObject()
                        .put("turn_reads", TurnTransport.readCount())
                        .put("turn_writes", TurnTransport.writeCount())
                        .put("frames", frames.get())
                        .put("received_fps", call.getCurrentParams().getReceivedFramerate())
                        .put("sent_fps", call.getCurrentParams().getSentFramerate());
                for (String kind : new String[] {"audio", "video"}) {
                  CallStats stats = kind.equals("audio") ? audio : video;
                  sample.put(
                      kind,
                      new JSONObject()
                          .put("up", stats.getUploadBandwidth())
                          .put("down", stats.getDownloadBandwidth())
                          .put("loss_percent", stats.getReceiverLossRate())
                          .put("local_loss_percent", stats.getLocalLossRate())
                          .put("late_packets", stats.getLatePacketsCumulativeNumber())
                          .put("received_packets", stats.getRtpPacketRecv())
                          .put("ice", stats.getIceState().toString()));
                }
                samples.put(sample);
                valid[0] =
                    audio.getIceState() == IceState.RelayConnection
                        && video.getIceState() == IceState.RelayConnection
                        && audio.getUploadBandwidth() > 1
                        && audio.getDownloadBandwidth() > 1
                        && video.getUploadBandwidth() > 5
                        && video.getDownloadBandwidth() > 5;
              } catch (Exception e) {
                throw new AssertionError(e);
              }
            });
        if (valid[0]) good++;
        if (i == 10) {
          android.graphics.Bitmap screenshot =
              InstrumentationRegistry.getInstrumentation().getUiAutomation().takeScreenshot();
          try (java.io.FileOutputStream output =
              new java.io.FileOutputStream(
                  new File(context.getNoBackupFilesDir(), "remote-media-screen.png"))) {
            screenshot.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, output);
          }
          screenshot.recycle();
        }
      }
      assertTrue("Sustained relayed bidirectional media: " + samples, good >= 10);
      assertTrue("Fresh decoded remote video frames: " + frames.get(), frames.get() >= 10);
      assertTrue("Corrected TURN reader receives live traffic", TurnTransport.readCount() > 0);
      assertTrue("Corrected TURN writer sends live traffic", TurnTransport.writeCount() > 0);
    } finally {
      main(engine::hangup);
      waitFor(() -> engine.call == null, 10);
      Files.writeString(
          new File(context.getNoBackupFilesDir(), "remote-media-report.json").toPath(),
          samples.toString(2));
      assertArrayEquals(original, Files.readAllBytes(enrollment.toPath()));
    }
  }
}
