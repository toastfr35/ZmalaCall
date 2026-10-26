package org.zmala.phone;

// @llr LLR-AND-HISTORY-002
/** Visible words explain callback direction; colour and arrows are supplementary. */
final class ContactNotice {
  static String summary(android.content.Context context, int missed, int callbacks) {
    return summary(missed, callbacks,
        n -> context.getResources().getQuantityString(R.plurals.missed_calls, n, n),
        context.getString(R.string.please_call_back), context.getString(R.string.callback_requested));
  }
  static String summary(int missed, int callbacks, java.util.function.IntFunction<String> missedText,
      String incoming, String sent) {
    java.util.List<String> parts = new java.util.ArrayList<>();
    if (missed > 0) parts.add(missedText.apply(missed));
    if ((callbacks & 1) != 0) parts.add(incoming);
    if ((callbacks & 2) != 0) parts.add(sent);
    return String.join(" · ", parts);
  }
}
