// @test A-LLT-012
// @requirements LLR-AND-CALL-002
// @environment portable
// @plan Supply front/back/static camera devices through SDK interface doubles. Switch twice,
// record the selected devices and reject any update that supplies new call parameters.
// @pass The sequence is back then front, with only local updates and the same current call.
package org.zmala.phone;

import static org.junit.Assert.*;

import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;
import org.junit.Test;
import org.linphone.core.Call;
import org.linphone.core.Core;

public class CameraSwitchTest {
  @Test
  public void twoSwitchesRestoreFrontWithoutRenegotiation() throws Exception {
    String[] selected = {"FrontFacingCamera"};
    List<String> changes = new ArrayList<>();
    List<String> updates = new ArrayList<>();
    Core core = (Core) Proxy.newProxyInstance(Core.class.getClassLoader(), new Class<?>[] {Core.class},
        (proxy, method, args) -> {
          switch (method.getName()) {
            case "getVideoDevicesList":
              return new String[] {"FrontFacingCamera", "BackFacingCamera", "StaticImage: Static picture"};
            case "getVideoDevice": return selected[0];
            case "setVideoDevice":
              selected[0] = (String) args[0];
              changes.add(selected[0]);
              return 0;
            default: throw new AssertionError("Unexpected core operation: " + method.getName());
          }
        });
    Call call = (Call) Proxy.newProxyInstance(Call.class.getClassLoader(), new Class<?>[] {Call.class},
        (proxy, method, args) -> {
          assertEquals("update", method.getName());
          assertNull("Camera changes must not renegotiate SDP", args[0]);
          updates.add(selected[0]);
          return 0;
        });
    CallEngine engine = new CallEngine(status -> {});
    var field = CallEngine.class.getDeclaredField("core");
    field.setAccessible(true);
    field.set(engine, core);
    engine.call = call;
    engine.flipCamera();
    engine.flipCamera();
    assertEquals(List.of("BackFacingCamera", "FrontFacingCamera"), changes);
    assertEquals(changes, updates);
    assertSame(call, engine.call);
  }
}
