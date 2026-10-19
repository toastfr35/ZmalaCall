package org.zmala.phone;

import java.util.function.LongConsumer;
import java.util.function.LongSupplier;
import org.linphone.core.Call;
import org.linphone.core.CallListenerStub;

// @llr LLR-AND-UI-002
/** Tracks decoded video, independently of SIP answer and ICE stream restarts. */
final class VideoStartup {
  private final LongSupplier clock;
  private final LongConsumer firstFrame;
  private Call tracked;
  private CallListenerStub listener;
  private long answeredAt = -1;
  private boolean ready;

  VideoStartup(LongSupplier clock, LongConsumer firstFrame) {
    this.clock = clock;
    this.firstFrame = firstFrame;
  }

  void state(Call call, Call.State state) {
    if (call != tracked) {
      reset();
      tracked = call;
      listener = new CallListenerStub() {
        @Override
        public void onNextVideoFrameDecoded(Call source) {
          if (tracked != call || source != call || ready || answeredAt < 0) return;
          ready = true;
          firstFrame.accept(clock.getAsLong() - answeredAt);
        }
      };
      call.addListener(listener);
    }
    if (state == Call.State.Connected && answeredAt < 0) answeredAt = clock.getAsLong();
    if (state == Call.State.StreamsRunning) requestFrame(call);
  }

  void requestFrame(Call call) {
    // ICE can replace the decoder after StreamsRunning. Re-arm until it delivers a frame.
    if (tracked == call && !ready && answeredAt >= 0) call.requestNotifyNextVideoFrameDecoded();
  }

  boolean ready(Call call) {
    return call != null && call == tracked && ready;
  }

  void reset() {
    Call previous = tracked;
    CallListenerStub previousListener = listener;
    tracked = null;
    listener = null;
    answeredAt = -1;
    ready = false;
    if (previous != null) previous.removeListener(previousListener);
  }
}
