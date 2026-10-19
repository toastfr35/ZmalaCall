// @test A-LLT-013
// @requirements LLR-AND-UI-002
// @environment portable
// @plan Feed answer, stream restarts and decoded-frame callbacks through SDK call doubles and
// a monotonic fake clock. Re-arm a replaced decoder, reset on hangup, and deliver stale callbacks.
// @pass Answer and StreamsRunning alone never mark video ready; only the current call's decoded
// frame does. Timing starts at answer, is reported once, and stale/early frames cannot hide progress.
package org.zmala.phone;

import static org.junit.Assert.*;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;
import org.junit.Test;
import org.linphone.core.Call;
import org.linphone.core.CallListener;

public class VideoStartupTest {
  static final class Peer {
    CallListener listener;
    int requests, removed;
    final Call call = (Call) Proxy.newProxyInstance(Call.class.getClassLoader(), new Class<?>[]{Call.class},
        (proxy, method, args) -> {
          switch (method.getName()) {
            case "addListener": listener = (CallListener) args[0]; return null;
            case "removeListener": assertSame(listener, args[0]); removed++; return null;
            case "requestNotifyNextVideoFrameDecoded": requests++; return null;
            default: throw new AssertionError(method.getName());
          }
        });
  }

  @Test public void decodedFrameControlsReadinessAcrossRestartAndNextCall() {
    long[] now = {100};
    List<Long> times = new ArrayList<>();
    VideoStartup startup = new VideoStartup(() -> now[0], times::add);
    Peer first = new Peer(), second = new Peer();
    startup.state(first.call, Call.State.OutgoingRinging);
    first.listener.onNextVideoFrameDecoded(first.call);
    assertFalse(startup.ready(first.call));
    now[0] = 500;
    startup.state(first.call, Call.State.Connected);
    startup.state(first.call, Call.State.StreamsRunning);
    assertFalse(startup.ready(first.call));
    assertEquals(1, first.requests);
    startup.state(first.call, Call.State.Updating);
    startup.state(first.call, Call.State.StreamsRunning);
    startup.requestFrame(first.call);
    assertEquals(3, first.requests);
    assertFalse(startup.ready(first.call));
    now[0] = 1700;
    first.listener.onNextVideoFrameDecoded(first.call);
    first.listener.onNextVideoFrameDecoded(first.call);
    assertTrue(startup.ready(first.call));
    assertEquals(List.of(1200L), times);
    startup.requestFrame(first.call);
    assertEquals(3, first.requests);
    startup.reset();
    assertEquals(1, first.removed);
    assertFalse(startup.ready(first.call));
    startup.state(second.call, Call.State.Connected);
    first.listener.onNextVideoFrameDecoded(first.call);
    second.listener.onNextVideoFrameDecoded(first.call);
    assertFalse(startup.ready(second.call));
    now[0] = 1900;
    second.listener.onNextVideoFrameDecoded(second.call);
    assertEquals(List.of(1200L, 200L), times);
    assertTrue(startup.ready(second.call));
    startup.reset();
    startup.reset();
    assertEquals(1, second.removed);
  }
}
