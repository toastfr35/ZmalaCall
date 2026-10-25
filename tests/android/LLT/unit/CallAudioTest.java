// @test A-LLT-017
// @requirements LLR-AND-CALL-002
// @environment portable
// @plan Give the engine SDK doubles with speaker/earpiece devices and record default, core and
// current-call routes. Cycle all three listening choices independently of microphone mute;
// repeat without an earpiece and after the engine is stopped.
// @pass The next call defaults to speaker, active routing reaches the selected built-in device,
// only the listening mute changes speakerMuted, and microphone changes never change output.
// A device without an earpiece skips it and stopped controls are harmless.
package org.zmala.phone;

import static org.junit.Assert.*;

import java.lang.reflect.Proxy;
import org.junit.Test;
import org.linphone.core.*;

public class CallAudioTest {
  private static AudioDevice device(AudioDevice.Type type) {
    return (AudioDevice) Proxy.newProxyInstance(AudioDevice.class.getClassLoader(),
        new Class<?>[]{AudioDevice.class}, (p, m, a) -> {
          if (m.getName().equals("getType")) return type;
          throw new AssertionError(m.getName());
        });
  }

  @Test public void independentMuteAndRoutesIncludeFutureCalls() throws Exception {
    AudioDevice speaker = device(AudioDevice.Type.Speaker), ear = device(AudioDevice.Type.Earpiece);
    AudioDevice[] routes = new AudioDevice[3];
    boolean[] microphone = {true}, listening = {false}, hasEarpiece = {true};
    Core core = (Core) Proxy.newProxyInstance(Core.class.getClassLoader(), new Class<?>[]{Core.class},
        (p, m, a) -> {
          switch (m.getName()) {
            case "getAudioDevices": return hasEarpiece[0]
                ? new AudioDevice[]{ear, speaker} : new AudioDevice[]{speaker};
            case "setDefaultOutputAudioDevice": routes[0] = (AudioDevice) a[0]; return null;
            case "setOutputAudioDevice": routes[1] = (AudioDevice) a[0]; return null;
            case "setMicEnabled": microphone[0] = (boolean) a[0]; return null;
            default: throw new AssertionError(m.getName());
          }
        });
    Call call = (Call) Proxy.newProxyInstance(Call.class.getClassLoader(), new Class<?>[]{Call.class},
        (p, m, a) -> {
          switch (m.getName()) {
            case "setOutputAudioDevice": routes[2] = (AudioDevice) a[0]; return null;
            case "setSpeakerMuted": listening[0] = (boolean) a[0]; return null;
            default: throw new AssertionError(m.getName());
          }
        });
    CallEngine engine = new CallEngine(s -> {});
    var field = CallEngine.class.getDeclaredField("core"); field.setAccessible(true); field.set(engine, core);
    assertEquals(CallEngine.Output.SPEAKER, engine.output(CallEngine.Output.SPEAKER));
    assertSame(speaker, routes[0]); assertSame(speaker, routes[1]); assertNull(routes[2]);
    engine.call = call;
    engine.mute(true);
    for (CallEngine.Output choice : CallEngine.Output.values()) {
      assertEquals(choice, engine.output(choice));
      assertFalse(microphone[0]);
      assertEquals(choice == CallEngine.Output.MUTED, listening[0]);
      for (AudioDevice actual : routes) assertSame(choice == CallEngine.Output.EARPIECE ? ear : speaker, actual);
    }
    engine.mute(false); assertTrue(microphone[0]); assertTrue(listening[0]);
    engine.output(CallEngine.Output.SPEAKER); assertFalse(listening[0]);
    hasEarpiece[0] = false;
    assertEquals(CallEngine.Output.MUTED, engine.output(CallEngine.Output.EARPIECE));
    assertTrue(listening[0]);
    assertEquals(CallEngine.Output.EARPIECE, CallEngine.Output.SPEAKER.next());
    assertEquals(CallEngine.Output.MUTED, CallEngine.Output.EARPIECE.next());
    assertEquals(CallEngine.Output.SPEAKER, CallEngine.Output.MUTED.next());
    field.set(engine, null); engine.call = null;
    engine.output(CallEngine.Output.SPEAKER); engine.mute(true);
  }
}
