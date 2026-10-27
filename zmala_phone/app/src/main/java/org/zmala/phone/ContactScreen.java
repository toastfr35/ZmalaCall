package org.zmala.phone;

import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.*;

// @llr LLR-AND-UI-002, LLR-AND-HISTORY-002
/** All actions for one person live on this scrollable page, rather than beside every list row. */
final class ContactScreen extends ScrollView {
  final ImageView portrait;
  final Button call, callback;
  ContactScreen(Context context, String name, String availability, String notices, boolean callable,
      boolean callbacksEnabled, boolean requested, boolean busy, int missed,
      Runnable back, Runnable dial, Runnable request, Runnable clear) {
    super(context); setFillViewport(true); setBackgroundColor(MainActivity.BG);
    LinearLayout body = new LinearLayout(context); body.setOrientation(LinearLayout.VERTICAL);
    body.setGravity(Gravity.CENTER_HORIZONTAL); body.setPadding(dp(20), dp(12), dp(20), dp(20)); addView(body);
    setOnApplyWindowInsetsListener((v, insets) -> {
      setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
          insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom()); return insets;
    });
    body.addView(action(getContext().getString(R.string.contacts), MainActivity.PANEL, back));
    portrait = new ImageView(context); portrait.setImageResource(R.drawable.zmala_logo);
    portrait.setScaleType(ImageView.ScaleType.CENTER_CROP); portrait.setContentDescription(getContext().getString(R.string.photo_of, name));
    GradientDrawable shape = new GradientDrawable(); shape.setColor(MainActivity.PANEL); shape.setCornerRadius(dp(20));
    portrait.setBackground(shape); portrait.setClipToOutline(true);
    LinearLayout.LayoutParams picture = new LinearLayout.LayoutParams(dp(112), dp(112));
    picture.setMargins(0, dp(16), 0, dp(12)); body.addView(portrait, picture);
    body.addView(label(name, 28)); body.addView(label(availability, 18));
    if (!notices.isEmpty()) body.addView(label(notices.replace(" · ", "\n"), 18));
    call = action(getContext().getString(R.string.call), callable ? MainActivity.GREEN : MainActivity.OFFLINE, dial);
    call.setEnabled(callable); body.addView(call);
    if (!callable) body.addView(label(callbacksEnabled
        ? getContext().getString(R.string.calling_unavailable_callback)
        : getContext().getString(R.string.calling_unavailable), 16));
    callback = callbacksEnabled ? action(busy ? getContext().getString(R.string.please_wait) : requested ? getContext().getString(R.string.cancel_request) : getContext().getString(R.string.request_callback),
        MainActivity.PANEL, request) : null;
    if (callback != null) { callback.setEnabled(!busy); body.addView(callback); }
    if (missed > 0) body.addView(action(getContext().getString(R.string.clear_missed), MainActivity.PANEL, clear));
  }
  private TextView label(String text, int size) {
    TextView view = new TextView(getContext()); view.setText(text); view.setTextSize(size);
    view.setTextColor(MainActivity.FG); view.setGravity(Gravity.CENTER); view.setPadding(0, dp(6), 0, dp(6)); return view;
  }
  private Button action(String text, int color, Runnable action) {
    Button view = new Button(getContext()); view.setText(text); view.setTextSize(18); view.setAllCaps(false);
    view.setTextColor(MainActivity.FG); view.setMinHeight(dp(60));
    GradientDrawable shape = new GradientDrawable(); shape.setColor(color); shape.setCornerRadius(dp(16));
    view.setBackground(shape); view.setOnClickListener(v -> action.run());
    LinearLayout.LayoutParams slot = new LinearLayout.LayoutParams(-1, -2); slot.setMargins(0, dp(8), 0, 0); view.setLayoutParams(slot); return view;
  }
  private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
