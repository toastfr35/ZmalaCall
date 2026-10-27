package org.zmala.phone;

import android.content.Context;

// @llr LLR-AND-UI-002
/** Engine status keys stay stable; translated display text never drives call policy. */
final class UiText {
  static String status(Context context, String key) {
    int id = switch (key) {
      case "Ready to call" -> R.string.ready;
      case "Cannot connect to the call server" -> R.string.cannot_connect;
      case "Connecting…" -> R.string.connecting;
      case "Incoming video call" -> R.string.incoming_video;
      case "In a video call" -> R.string.in_call;
      case "Call could not connect" -> R.string.call_failed;
      case "Call ended" -> R.string.call_ended;
      case "Call could not start" -> R.string.start_call_failed;
      case "An update is being installed. Try again shortly." -> R.string.update_busy;
      default -> R.string.calling;
    };
    return context.getString(id);
  }
}
