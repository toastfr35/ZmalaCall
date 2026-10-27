package org.zmala.phone;

import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.*;

// @llr LLR-AND-UI-002, LLR-AND-HISTORY-002
/** Exactly one focusable/clickable target per contact, including offline contacts. */
final class ContactCard extends LinearLayout {
  final ImageView portrait;
  final int color;
  ContactCard(Context context, String name, String availability, String notices, int color, Runnable open) {
    super(context);
    this.color = color;
    setGravity(Gravity.CENTER_VERTICAL); setPadding(dp(8), dp(8), dp(14), dp(8));
    GradientDrawable shape = new GradientDrawable(); shape.setColor(color); shape.setCornerRadius(dp(18));
    setBackground(shape); setMinimumHeight(dp(80)); setFocusable(true);
    setContentDescription(name + ", " + availability.toLowerCase(java.util.Locale.ROOT)
        + (notices.isEmpty() ? "" : ". " + notices) + getContext().getString(R.string.open_contact_suffix));
    setOnClickListener(v -> open.run());
    setAccessibilityDelegate(new AccessibilityDelegate() {
      @Override public void onInitializeAccessibilityNodeInfo(View host, AccessibilityNodeInfo info) {
        super.onInitializeAccessibilityNodeInfo(host, info); info.setClassName(Button.class.getName());
      }
    });
    portrait = new ImageView(context); portrait.setImageResource(R.drawable.zmala_logo);
    portrait.setScaleType(ImageView.ScaleType.CENTER_CROP);
    GradientDrawable photoShape = new GradientDrawable(); photoShape.setColor(MainActivity.PANEL); photoShape.setCornerRadius(dp(12));
    portrait.setBackground(photoShape); portrait.setClipToOutline(true);
    portrait.setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
    addView(portrait, new LayoutParams(dp(64), dp(64)));
    LinearLayout words = new LinearLayout(context); words.setOrientation(VERTICAL);
    LayoutParams area = new LayoutParams(0, -2, 1); area.setMargins(dp(14), 0, 0, 0); addView(words, area);
    String[] lines = {name, availability, notices};
    for (int i = 0; i < lines.length; i++) {
      String line = lines[i];
      if (line.isEmpty()) continue;
      TextView text = new TextView(context); text.setText(line); text.setTextColor(MainActivity.FG);
      text.setTextSize(i == 0 ? 20 : 14);
      text.setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
      words.addView(text);
    }
  }
  private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
