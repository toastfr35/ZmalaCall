package org.zmala.phone;

import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.*;

// @llr LLR-AND-UI-002
/** The person calling is the visual focus; scrolling preserves actions with enlarged text. */
final class IncomingCallScreen extends ScrollView {
  final ImageView portrait;

  IncomingCallScreen(Context context, String name, Runnable answer, Runnable decline) {
    super(context);
    setFillViewport(true);
    setBackgroundColor(MainActivity.BG);
    LinearLayout body = new LinearLayout(context);
    body.setOrientation(LinearLayout.VERTICAL);
    body.setGravity(Gravity.CENTER);
    body.setPadding(dp(24), dp(24), dp(24), dp(24));
    addView(body);
    setOnApplyWindowInsetsListener((view, insets) -> {
      setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
          insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
      return insets;
    });
    portrait = new ImageView(context);
    portrait.setImageResource(R.drawable.zmala_logo);
    portrait.setScaleType(ImageView.ScaleType.CENTER_CROP);
    portrait.setContentDescription(getContext().getString(R.string.photo_of, name));
    GradientDrawable shape = new GradientDrawable();
    shape.setColor(MainActivity.PANEL); shape.setCornerRadius(dp(24));
    portrait.setBackground(shape); portrait.setClipToOutline(true);
    body.addView(portrait, new LinearLayout.LayoutParams(dp(132), dp(132)));
    TextView who = new TextView(context);
    who.setText(name); who.setTextColor(MainActivity.FG); who.setTextSize(30);
    who.setGravity(Gravity.CENTER); who.setPadding(0, dp(20), 0, dp(8));
    body.addView(who, new LinearLayout.LayoutParams(-1, -2));
    TextView reason = new TextView(context);
    reason.setText(getContext().getString(R.string.incoming_video)); reason.setTextColor(MainActivity.MUTED);
    reason.setTextSize(18); reason.setGravity(Gravity.CENTER);
    reason.setPadding(0, 0, 0, dp(24)); body.addView(reason);
    body.addView(action(getContext().getString(R.string.answer_video), MainActivity.GREEN, answer));
    body.addView(action(getContext().getString(R.string.decline), MainActivity.RED, decline));
  }

  private Button action(String text, int color, Runnable action) {
    Button button = new Button(getContext());
    button.setText(text); button.setTextSize(20); button.setAllCaps(false);
    button.setTextColor(MainActivity.FG); button.setMinHeight(dp(64));
    GradientDrawable shape = new GradientDrawable(); shape.setColor(color); shape.setCornerRadius(dp(16));
    button.setBackground(shape); button.setOnClickListener(v -> action.run());
    LinearLayout.LayoutParams slot = new LinearLayout.LayoutParams(-1, -2);
    slot.setMargins(0, dp(8), 0, dp(8)); button.setLayoutParams(slot);
    return button;
  }
  private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
