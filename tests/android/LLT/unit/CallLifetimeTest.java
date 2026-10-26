// @test A-LLT-024
// @requirements LLR-AND-CALL-002
// @environment portable
// @plan Deliver matching/stale/empty notification call IDs. Use SDK doubles to hide/reattach an
// existing call, observe camera state, native surface detach and active-background iterate schedule.
// @pass Only the matching action can end a call; visibility changes retain the same core/call,
// disable then restore its camera and never terminate or renegotiate it.
package org.zmala.phone;
import static org.junit.Assert.*;
import org.junit.Test;
import org.linphone.core.*;
import java.lang.reflect.Proxy;
import java.util.*;

public class CallLifetimeTest {
  @Test public void notificationActionsAreBoundToOneCall() {
    assertFalse(CallLifetime.mayEnd(null, null)); assertFalse(CallLifetime.mayEnd("", ""));
    assertFalse(CallLifetime.mayEnd("old", "current")); assertTrue(CallLifetime.mayEnd("current", "current"));
  }
  @Test public void backgroundingPausesOnlyCameraAndDetachesViews() throws Exception {
    List<Boolean> camera = new ArrayList<>(); List<Integer> schedules = new ArrayList<>(); int[] windows = {0}, foreground = {0};
    Call call = (Call) Proxy.newProxyInstance(Call.class.getClassLoader(), new Class<?>[]{Call.class}, (p, method, args) -> {
      assertEquals("setCameraEnabled", method.getName()); camera.add((boolean) args[0]); return null;
    });
    Core core = (Core) Proxy.newProxyInstance(Core.class.getClassLoader(), new Class<?>[]{Core.class}, (p, method, args) -> {
      switch (method.getName()) {
        case "setAutoIterateBackgroundSchedule": schedules.add((int) args[0]); return null;
        case "setNativeVideoWindowId": case "setNativePreviewWindowId": assertNull(args[0]); windows[0]++; return null;
        case "enterForeground": foreground[0]++; return null;
        default: throw new AssertionError("Unexpected lifecycle operation: " + method.getName());
      }
    });
    CallEngine engine = new CallEngine(status -> {});
    var field = CallEngine.class.getDeclaredField("core"); field.setAccessible(true); field.set(engine, core); engine.call = call;
    engine.background(true); assertSame(call, engine.call); assertSame(core, field.get(engine));
    engine.background(false); assertSame(call, engine.call);
    assertEquals(List.of(false, true), camera); assertEquals(List.of(20, 500), schedules);
    assertEquals(2, windows[0]); assertEquals(1, foreground[0]);
  }
}
