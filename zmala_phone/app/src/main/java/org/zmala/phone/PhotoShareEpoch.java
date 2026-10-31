package org.zmala.phone;

// @llr LLR-AND-CALL-007
/** Generation fence shared by picker, upload and renewal completions. Main thread only. */
final class PhotoShareEpoch {
  private long epoch;
  private String owner;
  long begin(String call) { owner=call; return ++epoch; }
  void clear() { owner=null; epoch++; }
  boolean accepts(long ticket, String call, String current) {
    return call != null && ticket == epoch && call.equals(owner) && call.equals(current);
  }
}
