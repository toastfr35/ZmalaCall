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
import android.view.MotionEvent;
import android.view.TextureView;
import android.view.View;
import android.widget.*;
import org.linphone.mediastream.video.capture.CaptureTextureView;

// @llr LLR-AND-UI-002
/** Video surfaces remain attached while controls, call progress and display size change. */
final class CallScreen extends FrameLayout {
  enum Progress { NONE, CALLING, RINGING, CONNECTING, DELAYED }
  interface Actions {
    void mute(boolean muted);

    CallEngine.Output output(CallEngine.Output output);

    int volume(int steps);

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
  private final TextView muteStatus;
  private final TextView connectionStatus;
  private boolean muted;
  private CallEngine.Output output;
  private final TextView feedback;
  private final Runnable hideFeedback = this::hideFeedback;
  private final Runnable hideControls = this::hideControls;

  private void hideControls() {
    android.view.accessibility.AccessibilityManager accessibility = getContext().getSystemService(android.view.accessibility.AccessibilityManager.class);
    if (controls.hasFocus() || (accessibility != null && accessibility.isTouchExplorationEnabled())) {
      postDelayed(hideControls, controlTimeout());
      return;
    }
    controls.setVisibility(INVISIBLE);
    positionOverlays();
  }

  private void hideFeedback() { feedback.setVisibility(INVISIBLE); }

  // The shared gesture listener calls the touched view's performClick for ordinary taps.
  @android.annotation.SuppressLint("ClickableViewAccessibility")
  CallScreen(Context context, boolean initiallyMuted, CallEngine.Output initiallyOutput, Actions actions) {
    super(context);
    muted = initiallyMuted;
    output = initiallyOutput;
    setBackgroundColor(Color.BLACK);
    setContentDescription(getContext().getString(R.string.video_call_description));
    setOnClickListener(v -> showControls());
    remote = new TextureView(context);
    remote.setContentDescription(getContext().getString(R.string.remote_video_description));
    remote.setOnClickListener(v -> showControls());
    addView(remote, new LayoutParams(-1, -1));
    View.OnTouchListener volumeGesture = new View.OnTouchListener() {
      float x, y;
      int applied;
      boolean dragging, cancelled;

      public boolean onTouch(View source, MotionEvent event) {
        switch (event.getActionMasked()) {
          case MotionEvent.ACTION_DOWN:
            x = event.getX(); y = event.getY(); applied = 0;
            dragging = false; cancelled = false;
            return true;
          case MotionEvent.ACTION_POINTER_DOWN:
          case MotionEvent.ACTION_CANCEL:
            cancelled = true;
            return true;
          case MotionEvent.ACTION_MOVE:
            if (cancelled) return true;
            float vertical = y - event.getY(), horizontal = event.getX() - x;
            if (!dragging && Math.abs(horizontal) > dp(16)
                && Math.abs(horizontal) > Math.abs(vertical)) cancelled = true;
            if (cancelled) return true;
            if (Math.abs(vertical) >= dp(24) && Math.abs(vertical) > Math.abs(horizontal)) {
              dragging = true;
              int steps = (int) (vertical / dp(32));
              if (steps != applied) {
                int percent = actions.volume(steps - applied);
                applied = steps;
                notice(getContext().getString(output == CallEngine.Output.MUTED ? R.string.muted_volume : R.string.call_volume, percent));
              }
            }
            return true;
          case MotionEvent.ACTION_UP:
            if (!dragging && !cancelled) source.performClick();
            return true;
          default:
            return true;
        }
      }
    };
    remote.setOnTouchListener(volumeGesture);
    setOnTouchListener(volumeGesture);

    progress = new LinearLayout(context);
    progress.setOrientation(LinearLayout.VERTICAL);
    progress.setGravity(Gravity.CENTER);
    progress.setClipChildren(false);
    progress.setClipToPadding(false);
    progress.setOnClickListener(v -> showControls());
    progress.setOnTouchListener(volumeGesture);
    ringing = new RingingView(context);
    progress.addView(ringing, new LinearLayout.LayoutParams(dp(108), dp(108)));
    connecting = new ProgressBar(context);
    connecting.setIndeterminateTintList(ColorStateList.valueOf(MainActivity.GREEN));
    connecting.setContentDescription(getContext().getString(R.string.connecting_video_description));
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
    preview = new CameraPreview(context);
    preview.setContentDescription(getContext().getString(R.string.preview_description));
    preview.setOnClickListener(v -> showControls());
    preview.setOnTouchListener(volumeGesture);
    addView(preview, new LayoutParams(dp(96), dp(128), Gravity.BOTTOM | Gravity.RIGHT));

    controls = new LinearLayout(context);
    controls.setGravity(Gravity.CENTER);
    controls.setContentDescription(getContext().getString(R.string.controls_description));
    mute = icon(Kind.MIC, muted, muted ? getContext().getString(R.string.unmute_microphone) : getContext().getString(R.string.mute_microphone), MainActivity.PANEL);
    speaker = icon(outputKind(), false, outputLabel(), MainActivity.PANEL);
    ImageButton camera = icon(Kind.CAMERA, false, getContext().getString(R.string.switch_camera), MainActivity.PANEL);
    ImageButton end = icon(Kind.END, false, getContext().getString(R.string.end_call), MainActivity.RED);
    ImageButton[] buttons = {mute, speaker, camera, end};
    String[] names = {getContext().getString(R.string.mic_label), getContext().getString(R.string.sound_label), getContext().getString(R.string.camera_label), getContext().getString(R.string.end_label)};
    for (int i = 0; i < buttons.length; i++) {
      LinearLayout slot = new LinearLayout(context); slot.setOrientation(LinearLayout.VERTICAL);
      slot.setGravity(Gravity.CENTER_HORIZONTAL);
      slot.addView(buttons[i], new LinearLayout.LayoutParams(dp(60), dp(60)));
      TextView name = new TextView(context); name.setText(names[i]); name.setTextColor(MainActivity.FG);
      name.setTextSize(12); name.setGravity(Gravity.CENTER); name.setMaxLines(2);
      name.setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
      slot.addView(name, new LinearLayout.LayoutParams(-1, -2));
      controls.addView(slot, new LinearLayout.LayoutParams(dp(68), -2));
    }
    mute.setOnClickListener(
        v -> {
          muted = !muted;
          actions.mute(muted);
          mute.setImageDrawable(new Glyph(Kind.MIC, muted));
          mute.setContentDescription(muted ? getContext().getString(R.string.unmute_microphone) : getContext().getString(R.string.mute_microphone));
          mute.setSelected(muted);
          updateMuteStatus();
          notice(muted ? getContext().getString(R.string.microphone_muted) : getContext().getString(R.string.microphone_on));
          showControls();
        });
    speaker.setOnClickListener(
        v -> {
          output = actions.output(output.next());
          speaker.setImageDrawable(new Glyph(outputKind(), false));
          speaker.setContentDescription(outputLabel());
          speaker.setSelected(output == CallEngine.Output.MUTED);
          updateMuteStatus();
          notice(output == CallEngine.Output.SPEAKER ? getContext().getString(R.string.loudspeaker)
              : output == CallEngine.Output.EARPIECE ? getContext().getString(R.string.earpiece) : getContext().getString(R.string.call_sound_muted));
          showControls();
        });
    camera.setOnClickListener(
        v -> {
          actions.camera();
          showControls();
        });
    end.setOnClickListener(v -> actions.end());
    addView(controls, new LayoutParams(-2, -2, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL));
    controls.setVisibility(INVISIBLE);
    feedback = new TextView(context);
    feedback.setTextColor(MainActivity.FG);
    feedback.setTextSize(16);
    feedback.setGravity(Gravity.CENTER);
    feedback.setPadding(dp(16), dp(10), dp(16), dp(10));
    GradientDrawable feedbackBackground = new GradientDrawable();
    feedbackBackground.setColor(0xe6192230);
    feedbackBackground.setCornerRadius(dp(12));
    feedback.setBackground(feedbackBackground);
    feedback.setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_POLITE);
    feedback.setVisibility(INVISIBLE);
    LayoutParams feedbackSlot = new LayoutParams(-2, -2, Gravity.TOP | Gravity.CENTER_HORIZONTAL);
    feedbackSlot.topMargin = dp(24);
    addView(feedback, feedbackSlot);
    muteStatus = new TextView(context); muteStatus.setTextColor(MainActivity.FG);
    muteStatus.setTextSize(14); muteStatus.setPadding(dp(10), dp(6), dp(10), dp(6));
    muteStatus.setBackgroundColor(0xe6192230);
    muteStatus.setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_POLITE);
    LayoutParams statusSlot = new LayoutParams(-2, -2, Gravity.TOP | Gravity.LEFT);
    statusSlot.setMargins(dp(12), dp(12), dp(12), 0); addView(muteStatus, statusSlot);
    updateMuteStatus();
    connectionStatus = new TextView(context); connectionStatus.setTextColor(MainActivity.FG);
    connectionStatus.setTextSize(14); connectionStatus.setGravity(Gravity.CENTER);
    connectionStatus.setPadding(dp(12), dp(6), dp(12), dp(6)); connectionStatus.setBackgroundColor(0xe6192230);
    connectionStatus.setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_POLITE);
    LayoutParams connectionSlot = new LayoutParams(-1, -2, Gravity.TOP);
    connectionSlot.setMargins(dp(12), dp(54), dp(12), 0); addView(connectionStatus, connectionSlot);
    connectionStatus.setVisibility(GONE);
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

  private Kind outputKind() {
    return output == CallEngine.Output.EARPIECE ? Kind.EARPIECE
        : output == CallEngine.Output.MUTED ? Kind.SILENT : Kind.SPEAKER;
  }

  private void updateMuteStatus() {
    String text = muted ? getContext().getString(R.string.microphone_muted) : "";
    if (output == CallEngine.Output.MUTED) text += (text.isEmpty() ? "" : " · ") + getContext().getString(R.string.sound_muted);
    muteStatus.setText(text); muteStatus.setContentDescription(getContext().getString(R.string.audio_status, text));
    muteStatus.setVisibility(text.isEmpty() ? GONE : VISIBLE);
  }

  void firstCallHint() {
    notice(getContext().getString(R.string.call_hint));
    removeCallbacks(hideFeedback); postDelayed(hideFeedback, 5000);
  }

  private String outputLabel() {
    return output == CallEngine.Output.SPEAKER ? getContext().getString(R.string.output_to_earpiece)
        : output == CallEngine.Output.EARPIECE ? getContext().getString(R.string.output_to_muted)
        : getContext().getString(R.string.output_to_speaker);
  }

  private void notice(String text) {
    feedback.setText(text);
    feedback.setVisibility(VISIBLE);
    removeCallbacks(hideFeedback);
    postDelayed(hideFeedback, 1800);
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
    postDelayed(hideControls, controlTimeout());
    positionOverlays();
  }

  private int controlTimeout() {
    if (android.os.Build.VERSION.SDK_INT < 29) return 5000;
    android.view.accessibility.AccessibilityManager accessibility = getContext().getSystemService(android.view.accessibility.AccessibilityManager.class);
    return accessibility == null ? 5000 : accessibility.getRecommendedTimeoutMillis(5000,
        android.view.accessibility.AccessibilityManager.FLAG_CONTENT_CONTROLS
        | android.view.accessibility.AccessibilityManager.FLAG_CONTENT_TEXT
        | android.view.accessibility.AccessibilityManager.FLAG_CONTENT_ICONS);
  }

  void connectionNotice(String text) {
    connectionStatus.setText(text);
    connectionStatus.setVisibility(text == null ? GONE : VISIBLE);
  }

  void progress(Progress state) {
    if (state == Progress.NONE) {
      progress.setVisibility(GONE);
      pulse.cancel();
    } else {
      boolean waitingForVideo = state == Progress.CONNECTING || state == Progress.DELAYED;
      ringing.setVisibility(waitingForVideo ? GONE : VISIBLE);
      connecting.setVisibility(state == Progress.CONNECTING ? VISIBLE : GONE);
      String text = switch (state) {
        case CALLING -> getContext().getString(R.string.calling); case RINGING -> getContext().getString(R.string.ringing);
        case CONNECTING -> getContext().getString(R.string.connecting_video);
        case DELAYED -> getContext().getString(R.string.video_delayed);
        default -> "";
      };
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
    android.util.Size capture = preview.getPreviewVideoSize();
    float ratio = capture.getWidth() > 0 && capture.getHeight() > 0
        ? (float) capture.getWidth() / capture.getHeight() : landscape ? 4f / 3 : 3f / 4;
    int maximumWidth = dp(landscape ? 128 : 96), maximumHeight = dp(landscape ? 96 : 128);
    local.width = Math.min(maximumWidth, Math.round(maximumHeight * ratio));
    local.height = Math.min(maximumHeight, Math.round(maximumWidth / ratio));
    super.onMeasure(widthSpec, heightSpec);
    int bottom = controls.getVisibility() == VISIBLE ? controls.getMeasuredHeight() + dp(24) : dp(12);
    if (local.bottomMargin != bottom) {
      local.bottomMargin = bottom;
      super.onMeasure(widthSpec, heightSpec);
    }
  }

  private void positionOverlays() {
    if (controls == null || preview == null) return;
    LayoutParams local = (LayoutParams) preview.getLayoutParams();
    local.setMargins(dp(12), dp(12), dp(12), controls.getVisibility() == VISIBLE
        ? Math.max(dp(88), controls.getMeasuredHeight()) + dp(24) : dp(12));
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
    removeCallbacks(hideFeedback);
    pulse.cancel();
  }

  private enum Kind {
    MIC,
    SPEAKER,
    EARPIECE,
    SILENT,
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
          {
            canvas.drawArc(10, 7, 20, 17, -60, 120, false, paint);
            canvas.drawArc(8, 3, 24, 21, -55, 110, false, paint);
          }
          break;
        case EARPIECE:
          canvas.drawRoundRect(7, 2, 17, 22, 2, 2, paint);
          canvas.drawLine(10, 5, 14, 5, paint);
          canvas.drawCircle(12, 19, .6f, paint);
          break;
        case SILENT:
          path.moveTo(3, 9); path.lineTo(7, 9); path.lineTo(12, 5);
          path.lineTo(12, 19); path.lineTo(7, 15); path.lineTo(3, 15); path.close();
          canvas.drawPath(path, paint);
          canvas.drawLine(17, 10, 21, 14, paint);
          canvas.drawLine(17, 14, 21, 10, paint);
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
