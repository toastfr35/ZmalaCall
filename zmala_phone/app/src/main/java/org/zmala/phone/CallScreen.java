package org.zmala.phone;

import android.animation.ObjectAnimator;
import android.animation.ValueAnimator;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.*;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.util.Property;
import android.view.Gravity;
import android.view.TextureView;
import android.view.View;
import android.widget.*;
import org.linphone.mediastream.video.capture.CaptureTextureView;

// @llr LLR-AND-UI-002
/** Video surfaces remain attached while controls, call progress and display size change. */
final class CallScreen extends FrameLayout {
  interface Actions {
    void mute(boolean muted);

    void speaker(boolean loud);

    void camera();

    void end();
  }

  final TextureView remote;
  final CaptureTextureView preview;
  final LinearLayout controls;
  private final LinearLayout progress;
  private final TextView progressLabel;
  private final ObjectAnimator pulse;
  private final RingingView ringing;
  private final ProgressBar connecting;
  private final ImageButton mute, speaker;
  private boolean muted, loud;
  private final Runnable hideControls = this::hideControls;

  private void hideControls() {
    controls.setVisibility(INVISIBLE);
    positionOverlays();
  }

  CallScreen(Context context, boolean initiallyMuted, boolean initiallyLoud, Actions actions) {
    super(context);
    muted = initiallyMuted;
    loud = initiallyLoud;
    setBackgroundColor(Color.BLACK);
    setContentDescription("Video call. Tap to show call controls.");
    setOnClickListener(v -> showControls());
    remote = new TextureView(context);
    remote.setContentDescription("Remote video. Tap to show call controls.");
    remote.setOnClickListener(v -> showControls());
    addView(remote, new LayoutParams(-1, -1));

    progress = new LinearLayout(context);
    progress.setOrientation(LinearLayout.VERTICAL);
    progress.setGravity(Gravity.CENTER);
    progress.setClipChildren(false);
    progress.setClipToPadding(false);
    progress.setOnClickListener(v -> showControls());
    ringing = new RingingView(context);
    progress.addView(ringing, new LinearLayout.LayoutParams(dp(108), dp(108)));
    connecting = new ProgressBar(context);
    connecting.setIndeterminateTintList(ColorStateList.valueOf(MainActivity.GREEN));
    connecting.setContentDescription("Connecting video");
    connecting.setVisibility(GONE);
    progress.addView(connecting, new LinearLayout.LayoutParams(dp(60), dp(60)));
    progressLabel = new TextView(context);
    progressLabel.setTextColor(MainActivity.FG);
    progressLabel.setTextSize(20);
    progressLabel.setGravity(Gravity.CENTER);
    progressLabel.setPadding(0, dp(20), 0, 0);
    progressLabel.setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_POLITE);
    progress.addView(progressLabel);
    // Keep the label independent of the narrower spinner/ringing illustration.
    LayoutParams progressSlot = new LayoutParams(-1, -2, Gravity.CENTER);
    progressSlot.setMargins(dp(24), 0, dp(24), 0);
    addView(progress, progressSlot);
    pulse =
        ObjectAnimator.ofFloat(
            ringing,
            new Property<RingingView, Float>(Float.class, "phase") {
              public Float get(RingingView view) {
                return view.phase;
              }

              public void set(RingingView view, Float phase) {
                view.phase = phase;
                view.invalidate();
              }
            },
            0f,
            1f,
            0f);
    pulse.setDuration(1200);
    pulse.setRepeatCount(ValueAnimator.INFINITE);
    progress.setVisibility(GONE);

    // The SDK supplies camera dimensions and sensor/display rotation to this view.
    // A plain TextureView stretches the buffer and cannot consume those updates.
    preview = new CaptureTextureView(context);
    preview.setContentDescription("Your camera. Tap to show call controls.");
    preview.setOnClickListener(v -> showControls());
    addView(preview, new LayoutParams(dp(96), dp(128), Gravity.BOTTOM | Gravity.RIGHT));

    controls = new LinearLayout(context);
    controls.setGravity(Gravity.CENTER);
    controls.setContentDescription("Call controls");
    mute = icon(Kind.MIC, muted, muted ? "Unmute" : "Mute", MainActivity.PANEL);
    speaker = icon(Kind.SPEAKER, loud, loud ? "Use earpiece" : "Use speaker", MainActivity.PANEL);
    ImageButton camera = icon(Kind.CAMERA, false, "Switch camera", MainActivity.PANEL);
    ImageButton end = icon(Kind.END, false, "End call", MainActivity.RED);
    for (ImageButton button : new ImageButton[] {mute, speaker, camera, end}) {
      LinearLayout.LayoutParams slot = new LinearLayout.LayoutParams(dp(60), dp(60));
      slot.setMargins(dp(4), 0, dp(4), 0);
      controls.addView(button, slot);
    }
    mute.setOnClickListener(
        v -> {
          muted = !muted;
          actions.mute(muted);
          mute.setImageDrawable(new Glyph(Kind.MIC, muted));
          mute.setContentDescription(muted ? "Unmute" : "Mute");
          mute.setSelected(muted);
          showControls();
        });
    speaker.setOnClickListener(
        v -> {
          loud = !loud;
          actions.speaker(loud);
          speaker.setImageDrawable(new Glyph(Kind.SPEAKER, loud));
          speaker.setContentDescription(loud ? "Use earpiece" : "Use speaker");
          speaker.setSelected(loud);
          showControls();
        });
    camera.setOnClickListener(
        v -> {
          actions.camera();
          showControls();
        });
    end.setOnClickListener(v -> actions.end());
    addView(controls, new LayoutParams(-2, dp(60), Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL));
    controls.setVisibility(INVISIBLE);
    setOnApplyWindowInsetsListener(
        (v, insets) -> {
          setPadding(
              insets.getSystemWindowInsetLeft(),
              insets.getSystemWindowInsetTop(),
              insets.getSystemWindowInsetRight(),
              insets.getSystemWindowInsetBottom());
          positionOverlays();
          return insets;
        });
    positionOverlays();
  }

  private int dp(int value) {
    return Math.round(value * getResources().getDisplayMetrics().density);
  }

  private GradientDrawable circle(int color) {
    GradientDrawable result = new GradientDrawable();
    result.setShape(GradientDrawable.OVAL);
    result.setColor(color);
    return result;
  }

  private ImageButton icon(Kind kind, boolean active, String label, int color) {
    ImageButton button = new ImageButton(getContext());
    button.setImageDrawable(new Glyph(kind, active));
    button.setContentDescription(label);
    button.setSelected(active);
    button.setBackground(
        new RippleDrawable(ColorStateList.valueOf(0x30ffffff), circle(color), circle(Color.WHITE)));
    button.setDefaultFocusHighlightEnabled(false);
    button.setPadding(dp(16), dp(16), dp(16), dp(16));
    button.setMinimumWidth(dp(60));
    button.setMinimumHeight(dp(60));
    button.setScaleType(ImageView.ScaleType.FIT_CENTER);
    return button;
  }

  void showControls() {
    controls.setVisibility(VISIBLE);
    removeCallbacks(hideControls);
    postDelayed(hideControls, 5000);
    positionOverlays();
  }

  void progress(String text) {
    if (text == null) {
      progress.setVisibility(GONE);
      pulse.cancel();
    } else {
      boolean waitingForVideo = "Connecting video…".equals(text);
      ringing.setVisibility(waitingForVideo ? GONE : VISIBLE);
      connecting.setVisibility(waitingForVideo ? VISIBLE : GONE);
      progressLabel.setText(text);
      progress.setVisibility(VISIBLE);
      if (waitingForVideo) pulse.cancel();
      else if (!pulse.isStarted()) pulse.start();
    }
  }

  @Override
  protected void onMeasure(int widthSpec, int heightSpec) {
    // Set the slot before measuring children: onSizeChanged runs after their measurement
    // and leaves the texture at the previous orientation's size for this layout pass.
    boolean landscape = MeasureSpec.getSize(widthSpec) > MeasureSpec.getSize(heightSpec);
    LayoutParams local = (LayoutParams) preview.getLayoutParams();
    local.width = dp(landscape ? 128 : 96);
    local.height = dp(landscape ? 96 : 128);
    super.onMeasure(widthSpec, heightSpec);
  }

  private void positionOverlays() {
    if (controls == null || preview == null) return;
    LayoutParams local = (LayoutParams) preview.getLayoutParams();
    local.setMargins(dp(12), dp(12), dp(12), dp(controls.getVisibility() == VISIBLE ? 88 : 12));
    preview.setLayoutParams(local);
    LayoutParams bar = (LayoutParams) controls.getLayoutParams();
    bar.bottomMargin = dp(12);
    controls.setLayoutParams(bar);
  }

  @Override
  protected void onDetachedFromWindow() {
    dispose();
    super.onDetachedFromWindow();
  }

  void dispose() {
    removeCallbacks(hideControls);
    pulse.cancel();
  }

  private enum Kind {
    MIC,
    SPEAKER,
    CAMERA,
    END,
    PHONE
  }

  // @llr LLR-AND-UI-002
  /** Animate the drawing inside a fixed padded surface, never the surface's scale or alpha. */
  private static final class RingingView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Glyph phone = new Glyph(Kind.PHONE, false);
    private float phase;

    RingingView(Context context) {
      super(context);
      paint.setColor(MainActivity.GREEN);
    }

    @Override
    protected void onDraw(Canvas canvas) {
      super.onDraw(canvas);
      float density = getResources().getDisplayMetrics().density;
      float scale = .88f + .12f * phase;
      float radius = Math.min(42 * density, Math.min(getWidth(), getHeight()) / 2f - 12 * density);
      int alpha = Math.round(255 * (1f - .45f * phase));
      paint.setAlpha(alpha);
      canvas.drawCircle(getWidth() / 2f, getHeight() / 2f, Math.max(0, radius) * scale, paint);
      int halfIcon = Math.round(20 * density * scale);
      phone.setBounds(
          getWidth() / 2 - halfIcon,
          getHeight() / 2 - halfIcon,
          getWidth() / 2 + halfIcon,
          getHeight() / 2 + halfIcon);
      phone.setAlpha(alpha);
      phone.draw(canvas);
    }
  }

  /** Small original line icons, drawn in a consistent 24-unit coordinate system. */
  private static final class Glyph extends Drawable {
    private final Kind kind;
    private final boolean active;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

    Glyph(Kind kind, boolean active) {
      this.kind = kind;
      this.active = active;
      paint.setColor(Color.WHITE);
      paint.setStyle(Paint.Style.STROKE);
      paint.setStrokeWidth(1.8f);
      paint.setStrokeCap(Paint.Cap.ROUND);
      paint.setStrokeJoin(Paint.Join.ROUND);
    }

    @Override
    public void draw(Canvas canvas) {
      canvas.save();
      Rect b = getBounds();
      canvas.translate(b.left, b.top);
      canvas.scale(b.width() / 24f, b.height() / 24f);
      Path path = new Path();
      switch (kind) {
        case MIC:
          canvas.drawRoundRect(9, 2, 15, 14, 3, 3, paint);
          canvas.drawArc(6, 6, 18, 18, 0, 180, false, paint);
          canvas.drawLine(12, 18, 12, 22, paint);
          canvas.drawLine(8, 22, 16, 22, paint);
          if (active) canvas.drawLine(3, 3, 21, 21, paint);
          break;
        case SPEAKER:
          path.moveTo(3, 9);
          path.lineTo(7, 9);
          path.lineTo(12, 5);
          path.lineTo(12, 19);
          path.lineTo(7, 15);
          path.lineTo(3, 15);
          path.close();
          canvas.drawPath(path, paint);
          if (active) {
            canvas.drawArc(10, 7, 20, 17, -60, 120, false, paint);
            canvas.drawArc(8, 3, 24, 21, -55, 110, false, paint);
          } else {
            canvas.drawLine(17, 10, 21, 14, paint);
            canvas.drawLine(17, 14, 21, 10, paint);
          }
          break;
        case CAMERA:
          canvas.drawRoundRect(3, 6, 21, 18, 2, 2, paint);
          canvas.drawArc(8, 8, 16, 16, 35, 280, false, paint);
          path.moveTo(16, 8);
          path.lineTo(16, 11);
          path.lineTo(13, 10);
          canvas.drawPath(path, paint);
          break;
        case END:
        case PHONE:
          if (kind == Kind.PHONE) canvas.rotate(-125, 12, 12);
          path.moveTo(3, 16);
          path.lineTo(3, 12);
          path.cubicTo(7, 7, 17, 7, 21, 12);
          path.lineTo(21, 16);
          path.lineTo(16, 15);
          path.lineTo(16, 12);
          path.quadTo(12, 10, 8, 12);
          path.lineTo(8, 15);
          path.close();
          canvas.drawPath(path, paint);
          break;
      }
      canvas.restore();
    }

    @Override
    public void setAlpha(int alpha) {
      paint.setAlpha(alpha);
      invalidateSelf();
    }

    @Override
    public void setColorFilter(ColorFilter filter) {
      paint.setColorFilter(filter);
      invalidateSelf();
    }

    @Override
    public int getOpacity() {
      return PixelFormat.TRANSLUCENT;
    }

    @Override
    public int getIntrinsicWidth() {
      return 24;
    }

    @Override
    public int getIntrinsicHeight() {
      return 24;
    }
  }
}
