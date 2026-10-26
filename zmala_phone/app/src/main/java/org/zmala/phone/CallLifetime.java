package org.zmala.phone;

// @llr LLR-AND-CALL-002
/** Notification actions are bound to a call identity, not whichever call happens to be current. */
final class CallLifetime {
  static boolean mayEnd(String requested, String current) {
    return requested != null && !requested.isEmpty() && requested.equals(current);
  }
}
