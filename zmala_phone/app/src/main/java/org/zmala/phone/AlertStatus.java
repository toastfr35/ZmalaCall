package org.zmala.phone;

// @llr LLR-AND-CALL-004, LLR-AND-UI-002
/** Successful token upload cannot override disabled notifications or missing server support. */
enum AlertStatus {
  SERVER_OFF, NOTIFICATIONS_OFF, PREPARING, UNAVAILABLE, READY;
  static AlertStatus of(boolean serverEnabled, boolean notificationsAllowed, boolean preparing, boolean registered) {
    if (!serverEnabled) return SERVER_OFF;
    if (!notificationsAllowed) return NOTIFICATIONS_OFF;
    if (preparing) return PREPARING;
    return registered ? READY : UNAVAILABLE;
  }
}
