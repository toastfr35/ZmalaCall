package org.zmala.phone;

import android.app.Application;
import android.content.Context;

// @llr LLR-AND-CALL-006
/** Load the pinned TURN framing correction before any SDK library is resolved. */
public final class TurnTransport extends Application implements androidx.work.Configuration.Provider {
  // @llr LLR-AND-HISTORY-003, LLR-AND-UPDATE-002
  @Override public androidx.work.Configuration getWorkManagerConfiguration() {
    // Callback refresh work shares JobScheduler with our fixed update job (9037).
    return new androidx.work.Configuration.Builder().setJobSchedulerJobIdRange(10000, 19999).build();
  }

  @Override
  protected void attachBaseContext(Context base) {
    super.attachBaseContext(base);
    System.loadLibrary("zmala_turn");
  }

  static native long readCount();
  static native long writeCount();
}
