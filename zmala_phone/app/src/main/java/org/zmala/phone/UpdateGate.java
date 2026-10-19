package org.zmala.phone;

// @llr LLR-AND-UPDATE-002
/** One shared exclusion gate for native calls, push rings and installation commit. */
final class UpdateGate {
  static final UpdateGate INSTANCE = new UpdateGate();
  private boolean call, installing;
  private long ringUntil;

  synchronized boolean beginCall() {
    if (installing) return false;
    call = true;
    return true;
  }

  synchronized void endCall() { call = false; }
  synchronized boolean ring(long until) {
    if (installing) return false;
    ringUntil = Math.max(ringUntil, until);
    return true;
  }
  synchronized boolean idle(long now) { return !call && !installing && now >= ringUntil; }
  synchronized boolean beginInstall(long now) {
    if (!idle(now)) return false;
    installing = true;
    return true;
  }
  synchronized void restoreInstall(boolean pending) { installing = pending; }
  synchronized boolean installing() { return installing; }
}
