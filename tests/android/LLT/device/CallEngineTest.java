// @test A-LLT-004
// @requirements LLR-AND-CALL-002
// @environment native-sdk
// @plan Start the native engine against a disposable Digest-challenging UDP registrar, dial a permitted contact, inspect the resulting audio/video SDP, observe busy cleanup and stop registration. Exercise idempotent stop and controls after stop. Assert native AVPF feedback and NACK retransmission policy. Apply all four display rotations and check the native core orientation without replacing it.
// Accept and ACK a signed fixture call, switch the native camera twice, and watch for unwanted
// outgoing INVITEs. This verifies signaling and camera selection, not physical captured pixels.
// Keep an engine alive past the SDK's 20-second startup timer; inspect its foreground state
// and native Android helper's 20ms iteration schedule before and after that deadline.
// Inspect the native default speaker before a call. On an answered stream, select each output,
// assert its device/mute state independently of microphone mute, then switch cameras while muted.
// @pass Registration authenticates, the INVITE targets the permitted contact with audio and video and no bundle, and stop leaves no current call or registered state.
// Two switches restore the original native camera and retain StreamsRunning without a new INVITE.
// A visible-activity engine stays foreground with a 20ms timer after the startup boost expires.
// Speaker is the real next-call default; current-call device/mute and microphone stay independent.
package org.zmala.phone;

import static org.junit.Assert.*;

import android.Manifest;
import androidx.test.rule.GrantPermissionRule;
import java.util.concurrent.TimeUnit;
import org.junit.*;

public class CallEngineTest {
  @Rule public androidx.test.rule.ActivityTestRule<MainActivity> activity =
      new androidx.test.rule.ActivityTestRule<>(MainActivity.class, false, false);

  @Test
  public void foregroundTimerSurvivesStartupBoost() throws Exception {
    java.nio.file.Files.deleteIfExists(new java.io.File(
        PhoneFixture.INSTRUMENTATION.getTargetContext().getNoBackupFilesDir(), "enrollment.json").toPath());
    activity.launchActivity(null);
    CallEngine engine = new CallEngine(status -> {});
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip()) {
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
        try { engine.start(PhoneFixture.INSTRUMENTATION.getTargetContext(), PhoneFixture.config(sip.port())); }
        catch (Exception e) { throw new AssertionError(e); }
      });
      PhoneFixture.waitFor(() -> engine.registered);
      checkForeground(engine);
      Thread.sleep(21000);
      checkForeground(engine);
    } finally { PhoneFixture.INSTRUMENTATION.runOnMainSync(engine::stop); }
  }

  private static void checkForeground(CallEngine engine) {
    PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
      try {
        var coreField = CallEngine.class.getDeclaredField("core");
        coreField.setAccessible(true);
        org.linphone.core.Core core = (org.linphone.core.Core) coreField.get(engine);
        assertFalse("Visible engine must not use background iteration", core.isInBackground());
        Class<?> helper = Class.forName("org.linphone.core.tools.AndroidPlatformHelper");
        Object instance = helper.getMethod("instance").invoke(null);
        var schedule = helper.getDeclaredField("mIterateSchedule");
        schedule.setAccessible(true);
        assertEquals(20, schedule.getInt(instance));
      } catch (ReflectiveOperationException e) { throw new AssertionError(e); }
    });
  }

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
  public void cameraSwitchDoesNotRenegotiate() throws Exception {
    CallEngine engine = new CallEngine(status -> {});
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip()) {
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
        try {
          engine.start(PhoneFixture.INSTRUMENTATION.getTargetContext(), PhoneFixture.config(sip.port()));
        } catch (Exception e) { throw new AssertionError(e); }
      });
      PhoneFixture.waitFor(() -> engine.registered);
      sip.incoming("camera-switch", PhoneFixture.proof("camera-switch"));
      PhoneFixture.waitFor(() -> engine.call != null);
      PhoneFixture.INSTRUMENTATION.runOnMainSync(engine::answer);
      String answer = null;
      long end = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
      while (System.nanoTime() < end) {
        String response = sip.responses.poll(1, TimeUnit.SECONDS);
        if (response != null && response.startsWith("SIP/2.0 200") && response.contains("m=video ")) {
          answer = response;
          break;
        }
      }
      assertNotNull(answer);
      sip.send("ACK sip:phone1@127.0.0.1 SIP/2.0\r\nVia: SIP/2.0/UDP 127.0.0.1:"
          + sip.port() + ";branch=z9hG4bK-camera-ack\r\nFrom: " + PhoneFixture.Sip.header(answer, "From")
          + "\r\nTo: " + PhoneFixture.Sip.header(answer, "To")
          + "\r\nCall-ID: camera-switch\r\nCSeq: 1 ACK\r\nMax-Forwards: 70\r\nContent-Length: 0\r\n\r\n");
      PhoneFixture.waitFor(() -> engine.call.getState() == org.linphone.core.Call.State.StreamsRunning);
      var field = CallEngine.class.getDeclaredField("core");
      field.setAccessible(true);
      org.linphone.core.Core core = (org.linphone.core.Core) field.get(engine);
      org.linphone.core.Call original = engine.call;
      String[] cameras = new String[3];
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
        assertEquals(org.linphone.core.AudioDevice.Type.Speaker, core.getDefaultOutputAudioDevice().getType());
        assertEquals(org.linphone.core.AudioDevice.Type.Speaker, original.getOutputAudioDevice().getType());
        engine.mute(true);
        for (CallEngine.Output mode : CallEngine.Output.values()) {
          CallEngine.Output actual = engine.output(mode);
          assertFalse(core.isMicEnabled());
          assertEquals(actual == CallEngine.Output.MUTED, original.getSpeakerMuted());
          assertEquals(actual == CallEngine.Output.EARPIECE ? org.linphone.core.AudioDevice.Type.Earpiece
              : org.linphone.core.AudioDevice.Type.Speaker, original.getOutputAudioDevice().getType());
        }
        engine.mute(false);
        assertTrue(core.isMicEnabled());
        assertTrue(original.getSpeakerMuted());
        cameras[0] = core.getVideoDevice();
        engine.flipCamera();
        cameras[1] = core.getVideoDevice();
      });
      assertNotEquals("Fixture needs two native cameras", cameras[0], cameras[1]);
      assertNull("Camera switch sent a reINVITE", sip.invites.poll(2, TimeUnit.SECONDS));
      PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
        engine.flipCamera();
        cameras[2] = core.getVideoDevice();
      });
      assertEquals(cameras[0], cameras[2]);
      assertNull("Return to front sent a reINVITE", sip.invites.poll(2, TimeUnit.SECONDS));
      assertSame(original, engine.call);
      assertEquals(org.linphone.core.Call.State.StreamsRunning, engine.call.getState());
      assertTrue(engine.call.getSpeakerMuted());
    } finally {
      PhoneFixture.INSTRUMENTATION.runOnMainSync(engine::stop);
    }
  }

  @Test
  public void nativeOutgoingAndCleanup() throws Exception {
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
      assertTrue(sip.authenticated);
      java.lang.reflect.Field coreField = CallEngine.class.getDeclaredField("core");
      coreField.setAccessible(true);
      org.linphone.core.Core core = (org.linphone.core.Core) coreField.get(engine);
      PhoneFixture.INSTRUMENTATION.runOnMainSync(
          () -> {
            assertEquals(org.linphone.core.AVPFMode.Enabled, core.getAvpfMode());
            assertTrue(core.isRetransmissionOnNackEnabled());
            for (int degrees : new int[] {90, 180, 270, 0}) {
              engine.rotateVideo(degrees);
              assertEquals(degrees, core.getDeviceRotation());
            }
          });
      assertSame(core, coreField.get(engine));
      PhoneFixture.INSTRUMENTATION.runOnMainSync(
          () -> {
            try {
              engine.dial(config.getJSONArray("contacts").getJSONObject(0));
            } catch (Exception e) {
              throw new AssertionError(e);
            }
          });
      String invite = sip.invites.poll(10, TimeUnit.SECONDS);
      assertNotNull(invite);
      assertTrue(invite.startsWith("INVITE sip:term1@127.0.0.1"));
      assertTrue(invite.contains("m=audio "));
      assertTrue(invite.contains("m=video "));
      assertFalse(invite.contains("a=group:BUNDLE"));
      PhoneFixture.waitFor(() -> engine.call == null);
    } finally {
      PhoneFixture.INSTRUMENTATION.runOnMainSync(
          () -> {
            engine.stop();
            engine.stop();
            engine.mute(true);
            engine.flipCamera();
            engine.hangup();
          });
    }
    assertFalse(engine.registered);
    assertNull(engine.call);
  }
}
