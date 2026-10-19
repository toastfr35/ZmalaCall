package org.zmala.phone;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.hardware.display.DisplayManager;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.WindowManager;
import android.widget.*;
import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;
import org.linphone.core.Call;

// @llr LLR-AND-UI-002
public final class MainActivity extends Activity {
  static final int BG = Color.rgb(13, 18, 28),
      FG = Color.rgb(237, 241, 251),
      MUTED = Color.rgb(144, 160, 185),
      PANEL = Color.rgb(25, 34, 48),
      OFFLINE = Color.rgb(57, 64, 76),
      GREEN = Color.rgb(33, 122, 80),
      RED = Color.rgb(183, 47, 63);
  private final Handler main = new Handler(Looper.getMainLooper());
  private final ExecutorService network = Executors.newSingleThreadExecutor();
  private final CallEngine engine = new CallEngine(this::callChanged);
  private Enrollment enrollment;
  private JSONObject config;
  private LinearLayout page;
  private int generation;
  private boolean visible, fetching, muted, loud = true;
  private Call displayedCall;
  private CallScreen callScreen;
  private final DisplayManager.DisplayListener displayListener =
      new DisplayManager.DisplayListener() {
        public void onDisplayAdded(int id) {}

        public void onDisplayRemoved(int id) {}

        public void onDisplayChanged(int id) {
          updateVideoRotation();
        }
      };
  private Ringtone ringtone;
  private AudioFocusRequest audioFocus;
  private String message = "Welcome";
  private static java.lang.ref.WeakReference<MainActivity> foreground =
      new java.lang.ref.WeakReference<>(null);
  private String answerCallId;
  private long answerExpires;
  private boolean pushReady;
  private boolean restartRequested;
  private final Runnable poll = () -> refresh(false);

  @Override
  public void onCreate(Bundle state) {
    super.onCreate(state);
    handlePushIntent(getIntent());
    directory();
  }

  // @llr LLR-AND-ENROLL-002
  private File enrollmentFile() {
    return new File(getNoBackupFilesDir(), "enrollment.json");
  }

  @Override
  public void onStart() {
    super.onStart();
    visible = true;
    foreground = new java.lang.ref.WeakReference<>(this);
    ((DisplayManager) getSystemService(DISPLAY_SERVICE))
        .registerDisplayListener(displayListener, main);
    if (enrollment == null && enrollmentFile().isFile()) {
      try {
        enrollment =
            new Enrollment(
                new String(Files.readAllBytes(enrollmentFile().toPath()), StandardCharsets.UTF_8));
      } catch (Exception e) {
        message = "Scan a new setup QR code.";
      }
    }
    if (enrollment != null && permissions()) refresh(true);
    else directory();
  }

  @Override
  public void onStop() {
    visible = false;
    if (foreground.get() == this) foreground.clear();
    ((DisplayManager) getSystemService(DISPLAY_SERVICE)).unregisterDisplayListener(displayListener);
    generation++;
    fetching = false;
    main.removeCallbacks(poll);
    engine.stop();
    silence();
    releaseAudio();
    displayedCall = null;
    if (callScreen != null) callScreen.dispose();
    callScreen = null;
    getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    super.onStop();
  }

  @Override
  public void onDestroy() {
    network.shutdownNow();
    super.onDestroy();
  }

  private boolean permissions() {
    return checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        && checkSelfPermission(Manifest.permission.RECORD_AUDIO)
            == PackageManager.PERMISSION_GRANTED
        && (android.os.Build.VERSION.SDK_INT < 37
            || checkSelfPermission("android.permission.ACCESS_LOCAL_NETWORK")
                == PackageManager.PERMISSION_GRANTED);
  }

  private void requestMedia() {
    requestPermissions(
        (android.os.Build.VERSION.SDK_INT >= 37
            ? new String[] {
              Manifest.permission.CAMERA,
              Manifest.permission.RECORD_AUDIO,
              "android.permission.ACCESS_LOCAL_NETWORK"
            }
            : new String[] {Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO}),
        7);
  }

  @Override
  public void onRequestPermissionsResult(int request, String[] names, int[] results) {
    super.onRequestPermissionsResult(request, names, results);
    if (request == 8 && enrollment != null) {
      registerPush();
      return;
    }
    if (request == 7) {
      if (permissions()) {
        if (enrollment == null) scan();
        else refresh(true);
      } else {
        message =
            "Camera, microphone and local network access are needed for video calls. Enable them in"
                + " Android Settings.";
        directory();
      }
    }
  }

  private void scan() {
    if (!permissions()) {
      requestMedia();
      return;
    }
    new IntentIntegrator(this)
        .setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
        .setPrompt("Scan your setup QR code")
        .setBeepEnabled(false)
        .setOrientationLocked(false)
        .initiateScan();
  }

  @Override
  protected void onActivityResult(int request, int result, Intent data) {
    super.onActivityResult(request, result, data);
    IntentResult scan = IntentIntegrator.parseActivityResult(request, result, data);
    if (scan == null || scan.getContents() == null) return;
    try {
      Enrollment candidate = new Enrollment(scan.getContents());
      new AlertDialog.Builder(this)
          .setTitle("Connect to ZmalaCall")
          .setMessage(
              candidate.server.toString()
                  + (candidate.server.getScheme().equals("http")
                      ? "\n\n"
                          + "LAN mode: setup and calls are not encrypted. Use your trusted home"
                          + " network."
                      : "\n\nUse this server for your app account?"))
          .setPositiveButton(
              "Connect",
              (dialog, which) -> {
                generation++;
                enrollment = candidate;
                config = null;
                engine.stop();
                refresh(true);
              })
          .setNegativeButton("Cancel", null)
          .show();
    } catch (Exception e) {
      showError(e.getMessage());
    }
  }

  // @llr LLR-AND-CALL-006
  private void refresh(boolean start) {
    if (!visible || enrollment == null) return;
    restartRequested |= start;
    if (fetching) return;
    if (!permissions()) {
      requestMedia();
      return;
    }
    fetching = true;
    int ticket = generation;
    Enrollment target = enrollment;
    if (config == null) {
      message = "Connecting to your server…";
      directory();
    }
    network.execute(
        () -> {
          try {
            JSONObject next = ServerApi.configuration(target);
            main.post(
                () -> {
                  if (!visible || ticket != generation) return;
                  fetching = false;
                  try {
                    boolean changed = config == null || !next.toString().equals(config.toString());
                    boolean credentialsChanged = engine.requiresRestart(next);
                    if (start || !enrollmentFile().isFile())
                      Files.write(
                          enrollmentFile().toPath(),
                          target.serialized().getBytes(StandardCharsets.UTF_8));
                    config = next;
                    PushAlerts.remember(this, next);
                    boolean restart = restartRequested;
                    restartRequested = false;
                    if ((restart || credentialsChanged) && engine.call == null)
                      engine.start(this, next);
                    else engine.refresh(next);
                    if (engine.call == null) registerPush();
                    if (changed && engine.call == null) directory();
                  } catch (Exception e) {
                    engine.stop();
                    showError("Unable to start calling. Check app permissions and setup.");
                  }
                  main.removeCallbacks(poll);
                  main.postDelayed(poll, 10000);
                });
          } catch (Exception e) {
            main.post(
                () -> {
                  if (!visible || ticket != generation) return;
                  fetching = false;
                  engine.stop();
                  config = null;
                  silence();
                  releaseAudio();
                  message =
                      e instanceof IllegalArgumentException || e instanceof IllegalStateException
                          ? e.getMessage()
                          : "Cannot reach your server. Check your connection, then retry.";
                  directory();
                  // Re-register after a failed refresh instead of leaving a silent stopped core.
                  main.removeCallbacks(poll);
                  main.postDelayed(
                      () -> {
                        if (ticket == generation) refresh(true);
                      },
                      10000);
                });
          }
        });
  }

  // @llr LLR-AND-UI-002
  private int dp(int value) {
    return (int) Math.ceil(value * getResources().getDisplayMetrics().density);
  }

  private GradientDrawable rounded(int color) {
    GradientDrawable shape = new GradientDrawable();
    shape.setColor(color);
    shape.setCornerRadius(dp(22));
    return shape;
  }

  private TextView label(String text, int size, int color) {
    TextView view = new TextView(this);
    view.setText(text);
    view.setTextSize(size);
    view.setTextColor(color);
    view.setPadding(dp(8), dp(6), dp(8), dp(6));
    return view;
  }

  private Button button(String text, int color, Runnable action) {
    Button view = new Button(this);
    view.setText(text);
    view.setTextColor(FG);
    view.setTextSize(18);
    view.setAllCaps(false);
    view.setMinHeight(dp(60));
    view.setMinimumHeight(dp(60));
    view.setBackground(rounded(color));
    view.setOnClickListener(v -> action.run());
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
    params.setMargins(0, dp(8), 0, dp(4));
    view.setLayoutParams(params);
    return view;
  }

  private void shell() {
    page = new LinearLayout(this);
    page.setOrientation(LinearLayout.VERTICAL);
    page.setBackgroundColor(BG);
    page.setPadding(dp(20), dp(12), dp(20), dp(12));
    page.setOnApplyWindowInsetsListener(
        (v, insets) -> {
          v.setPadding(
              dp(20) + insets.getSystemWindowInsetLeft(),
              dp(12) + insets.getSystemWindowInsetTop(),
              dp(20) + insets.getSystemWindowInsetRight(),
              dp(12) + insets.getSystemWindowInsetBottom());
          return insets;
        });
    LinearLayout header = new LinearLayout(this);
    header.setGravity(Gravity.CENTER_VERTICAL);
    ImageView logo = new ImageView(this);
    logo.setImageResource(R.drawable.zmala_logo);
    logo.setContentDescription("ZmalaCall logo");
    header.addView(logo, new LinearLayout.LayoutParams(dp(52), dp(52)));
    TextView title = label("ZmalaPhone", 28, FG);
    title.setTypeface(null, Typeface.BOLD);
    header.addView(title);
    page.addView(header);
    if (!message.equals("Ready to call")) page.addView(label(message, 16, MUTED));
    setContentView(page);
  }

  private void directory() {
    displayedCall = null;
    callScreen = null;
    shell();
    if (enrollment == null) {
      page.addView(label("Together, wherever you are", 26, FG));
      page.addView(label("Scan the setup QR code you received by email or on paper.", 18, MUTED));
      page.addView(button("Scan setup QR", GREEN, this::scan));
    } else if (config == null) page.addView(button("Retry connection", GREEN, () -> refresh(true)));
    else {
      ScrollView scroll = new ScrollView(this);
      scroll.setFillViewport(true);
      LinearLayout contacts = new LinearLayout(this);
      contacts.setOrientation(LinearLayout.VERTICAL);
      contacts.setGravity(Gravity.CENTER_VERTICAL);
      scroll.addView(contacts);
      page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
      JSONArray entries = config.optJSONArray("contacts");
      int count = 0;
      if (entries != null)
        for (int i = 0; i < entries.length(); i++) {
          JSONObject contact = entries.optJSONObject(i);
          if (!contact.optBoolean("can_call")) continue;
          count++;
          LinearLayout card = new LinearLayout(this);
          card.setGravity(Gravity.CENTER_VERTICAL);
          LinearLayout.LayoutParams margins = new LinearLayout.LayoutParams(-1, -2);
          margins.setMargins(0, dp(4), 0, dp(4));
          contacts.addView(card, margins);
          ImageView photo = new ImageView(this);
          photo.setImageResource(R.drawable.zmala_logo);
          photo.setScaleType(ImageView.ScaleType.CENTER_CROP);
          photo.setContentDescription("Photo of " + contact.optString("name"));
          photo.setBackground(rounded(PANEL));
          photo.setClipToOutline(true);
          card.addView(photo, new LinearLayout.LayoutParams(dp(72), dp(72)));
          boolean online = contact.optBoolean("online");
          Button call =
              button(
                  contact.optString("name"),
                  online ? GREEN : OFFLINE,
                  () -> {
                    try {
                      engine.dial(contact);
                    } catch (Exception e) {
                      showError("Call could not start.");
                    }
                  });
          call.setTextSize(20);
          call.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
          call.setPadding(dp(18), dp(10), dp(14), dp(10));
          call.setMinHeight(dp(72));
          call.setMinimumHeight(dp(72));
          call.setContentDescription(
              contact.optString("name") + (online ? ", online. Tap to call." : ", offline."));
          call.setEnabled(engine.registered && online);
          LinearLayout.LayoutParams nameArea = new LinearLayout.LayoutParams(0, -2, 1);
          nameArea.setMargins(dp(10), 0, 0, 0);
          card.addView(call, nameArea);
          String path = contact.optString("photo");
          int ticket = generation;
          Enrollment target = enrollment;
          if (!path.isEmpty())
            network.execute(
                () -> {
                  try {
                    byte[] bytes = ServerApi.photo(target, path);
                    BitmapFactory.Options options = new BitmapFactory.Options();
                    options.inJustDecodeBounds = true;
                    BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
                    options.inSampleSize =
                        Math.max(1, Math.max(options.outWidth, options.outHeight) / 256);
                    options.inJustDecodeBounds = false;
                    android.graphics.Bitmap bitmap =
                        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
                    main.post(
                        () -> {
                          if (visible && ticket == generation && bitmap != null)
                            photo.setImageBitmap(bitmap);
                        });
                  } catch (Exception ignored) {
                    /* Keep the common logo when a portrait is unavailable. */
                  }
                });
        }
      if (count == 0)
        contacts.addView(
            label(
                "No contacts yet. Ask your administrator to add you to a calling group.",
                20,
                MUTED));
    }
    page.addView(
        label(
            pushReady
                ? "Incoming call alerts enabled"
                : "Keep this screen open to receive calls",
            13,
            MUTED));
  }

  // @llr LLR-AND-CALL-002, LLR-AND-UI-002
  private void callChanged(String text) {
    if (!visible) return;
    message = text;
    if (engine.call == null) {
      silence();
      releaseAudio();
      getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
      directory();
      return;
    }
    if (displayedCall == engine.call && callScreen != null) {
      updateCallProgress();
      return;
    }
    displayedCall = engine.call;
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    if (engine.call.getState() == Call.State.IncomingReceived) {
      // @llr LLR-AND-CALL-004
      String callId = engine.call.getCallLog().getCallId();
      PushAlerts.dismiss(this, callId);
      if (callId.equals(answerCallId) && answerExpires > System.currentTimeMillis()) {
        Call pending = engine.call;
        long expires = answerExpires;
        answerCallId = null;
        // Accept on the next main-loop turn, after Liblinphone finishes its
        // IncomingReceived transition and ICE setup. Recheck after cancellation.
        PushAnswer.enqueue(task -> main.post(task), System::currentTimeMillis, expires,
            () -> visible && engine.call == pending
                && pending.getState() == Call.State.IncomingReceived,
            () -> {
              displayedCall = null;
              acquireAudio();
              engine.answer();
            });
        return;
      }
      shell();
      String user = engine.call.getRemoteAddress().getUsername();
      String name = user;
      JSONArray contacts = config.optJSONArray("contacts");
      if (contacts != null)
        for (int i = 0; i < contacts.length(); i++)
          if (user.equals(contacts.optJSONObject(i).optString("id")))
            name = contacts.optJSONObject(i).optString("name");
      page.addView(label(name, 30, FG));
      if (ringtone == null) {
        ringtone =
            RingtoneManager.getRingtone(
                this, RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE));
        if (ringtone != null) ringtone.play();
      }
      page.addView(
          button(
              "Answer video call",
              GREEN,
              () -> {
                silence();
                displayedCall = null;
                acquireAudio();
                engine.answer();
              }));
      page.addView(button("Decline", RED, engine::hangup));
      return;
    }
    silence();
    acquireAudio();
    callScreen =
        new CallScreen(
            this,
            muted,
            loud,
            new CallScreen.Actions() {
              public void mute(boolean value) {
                muted = value;
                engine.mute(value);
              }

              public void speaker(boolean value) {
                loud = value;
                engine.speaker(value);
              }

              public void camera() {
                engine.flipCamera();
              }

              public void end() {
                engine.hangup();
              }
            });
    setContentView(callScreen);
    engine.video(callScreen.remote, callScreen.preview);
    updateVideoRotation();
    updateCallProgress();
  }

  // @llr LLR-AND-UI-002
  private void updateCallProgress() {
    if (callScreen == null || engine.call == null) return;
    switch (engine.call.getState()) {
      case OutgoingInit:
      case OutgoingProgress:
        callScreen.progress("Calling…");
        break;
      case OutgoingRinging:
        callScreen.progress("Ringing…");
        break;
      case OutgoingEarlyMedia:
        callScreen.progress("Ringing…");
        break;
      case Connected:
      case StreamsRunning:
      case Updating:
      case UpdatedByRemote:
        callScreen.progress(engine.remoteVideoReady() ? null : "Connecting video…");
        break;
      default:
        callScreen.progress(null);
        break;
    }
  }

  @Override
  public void onConfigurationChanged(Configuration configuration) {
    super.onConfigurationChanged(configuration);
    updateVideoRotation();
    if (callScreen != null) callScreen.requestLayout();
  }

  private void updateVideoRotation() {
    if (visible && callScreen != null)
      engine.rotateVideo(getWindowManager().getDefaultDisplay().getRotation() * 90);
  }

  private void acquireAudio() {
    if (audioFocus != null) return;
    AudioManager audio = (AudioManager) getSystemService(AUDIO_SERVICE);
    audioFocus =
        new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
            .setAudioAttributes(
                new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build())
            .setOnAudioFocusChangeListener(
                change -> {
                  if (change == AudioManager.AUDIOFOCUS_LOSS) engine.hangup();
                })
            .build();
    audio.requestAudioFocus(audioFocus);
    audio.setMode(AudioManager.MODE_IN_COMMUNICATION);
  }

  private void releaseAudio() {
    if (audioFocus != null) {
      AudioManager audio = (AudioManager) getSystemService(AUDIO_SERVICE);
      audio.abandonAudioFocusRequest(audioFocus);
      audio.setMode(AudioManager.MODE_NORMAL);
      audioFocus = null;
    }
    muted = false;
  }

  private void silence() {
    if (ringtone != null) {
      ringtone.stop();
      ringtone = null;
    }
  }

  private void showError(String text) {
    message = text;
    new AlertDialog.Builder(this)
        .setTitle("ZmalaPhone")
        .setMessage(text)
        .setPositiveButton("OK", null)
        .show();
  }

  // @llr LLR-AND-CALL-004
  private void registerPush() {
    if (enrollment == null || config == null || !config.optBoolean("push_enabled")) return;
    if (android.os.Build.VERSION.SDK_INT >= 33
        && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        && !getSharedPreferences("push", 0).getBoolean("permission_asked", false)) {
      getSharedPreferences("push", 0).edit().putBoolean("permission_asked", true).apply();
      new AlertDialog.Builder(this)
          .setTitle("Receive calls when ZmalaPhone is closed")
          .setMessage(
              "Allow notifications so incoming calls can ring when you're using another app or the"
                  + " phone is asleep. Internet and access to your call server are needed. If you"
                  + " use Android's Force stop, open ZmalaPhone again to receive calls.")
          .setPositiveButton(
              "Continue",
              (dialog, which) ->
                  requestPermissions(new String[] {Manifest.permission.POST_NOTIFICATIONS}, 8))
          .setNegativeButton("Not now", (dialog, which) -> registerPush())
          .show();
      return;
    }
    Enrollment target = enrollment;
    PushAlerts.register(
        this,
        target,
        ready -> {
          if (!visible || enrollment != target || pushReady == ready) return;
          pushReady = ready;
          if (engine.call == null) directory();
        });
  }

  // @llr LLR-AND-CALL-004
  @Override
  protected void onNewIntent(Intent intent) {
    super.onNewIntent(intent);
    setIntent(intent);
    handlePushIntent(intent);
    if (visible && enrollment != null && engine.call == null) refresh(true);
  }

  private void handlePushIntent(Intent intent) {
    Enrollment stored = PushAlerts.enrollment(this);
    PushMessage push =
        stored == null
            ? null
            : PushMessage.verify(stored, PushAlerts.unpack(intent), System.currentTimeMillis());
    if (push == null || !push.event.equals("ring") || PushAlerts.closed(this, push.callId, false))
      return;
    setShowWhenLocked(true);
    setTurnScreenOn(true);
    if (intent.getBooleanExtra(PushAlerts.ANSWER, false)) {
      answerCallId = push.callId;
      answerExpires = push.expires;
    }
    PushAlerts.dismiss(this, push.callId);
  }

  static boolean pushIncoming(java.util.Map<String, String> data) {
    MainActivity screen = foreground.get();
    if (screen == null || !screen.visible) return false;
    screen.main.post(
        () -> {
          if (!screen.visible) {
            PushAlerts.receive(screen.getApplicationContext(), data);
            return;
          }
          if (screen.engine.call == null) screen.refresh(true);
        });
    return true;
  }
}
