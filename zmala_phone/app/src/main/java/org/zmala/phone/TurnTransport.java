package org.zmala.phone;

import android.app.Application;
import android.content.Context;

// @llr LLR-AND-CALL-006
/** Load the pinned TURN framing correction before any SDK library is resolved. */
public final class TurnTransport extends Application {
  @Override
  protected void attachBaseContext(Context base) {
    super.attachBaseContext(base);
    System.loadLibrary("zmala_turn");
  }

  static native long readCount();
  static native long writeCount();
}
