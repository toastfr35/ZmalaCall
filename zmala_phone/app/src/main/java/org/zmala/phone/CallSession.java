package org.zmala.phone;

import android.content.*;
import android.media.*;
import android.os.*;
import java.lang.ref.WeakReference;
import java.util.concurrent.Executors;
import org.json.JSONObject;
import org.linphone.core.Call;

// @llr LLR-AND-CALL-002, LLR-AND-CALL-006
/** Application-owned live call, never an Activity or a permanent idle SIP connection. Main thread only. */
final class CallSession {
  @android.annotation.SuppressLint("StaticFieldLeak") // Application context; the screen is weakly held.
  private static CallSession instance;
  static CallSession get(Context context) {
    if (instance == null) instance = new CallSession(context.getApplicationContext());
    return instance;
  }
  static CallSession peek() { return instance; }

  final CallEngine engine;
  JSONObject configuration;
  String status = "Connecting…";
  boolean muted, reconnecting, visible, serviceRequested;
  CallEngine.Output output = CallEngine.Output.SPEAKER;
  private final Context context;
  private final Handler main = new Handler(Looper.getMainLooper());
  private final java.util.concurrent.ExecutorService network = Executors.newSingleThreadExecutor();
  private WeakReference<MainActivity> screen = new WeakReference<>(null);
  private AudioFocusRequest audioFocus;
  private long epoch, focusEpoch;
  private boolean fetching;
  private final Runnable poll = this::poll;

  private CallSession(Context context) {
    this.context = context;
    engine = new CallEngine(this::changed);
  }

  boolean ongoing() { return engine.call != null && engine.call.getState() != Call.State.IncomingReceived; }
  String callId() { return engine.call == null ? null : engine.call.getCallLog().getCallId(); }

  void attach(MainActivity activity) {
    screen = new WeakReference<>(activity); visible = true; epoch++;
    main.removeCallbacks(poll);
    engine.background(false);
  }

  void detach(MainActivity activity, boolean recreating) {
    if (screen.get() != activity) return;
    screen.clear(); visible = false; epoch++;
    if (ongoing() && serviceRequested) {
      engine.background(true);
      main.removeCallbacks(poll); main.postDelayed(poll, 10000);
      CallService.refresh();
    } else if (recreating) {
      main.postDelayed(() -> { if (!visible && !ongoing()) stop(); }, 1000);
    } else stop();
  }

  /** Called from the visible user's Call/Answer action, before any background transition. */
  boolean prepare() {
    if (serviceRequested) return true;
    if (!visible) return false;
    try {
      serviceRequested = true;
      context.startForegroundService(new Intent(context, CallService.class));
      return true;
    } catch (RuntimeException denied) {
      serviceFailed();
      return false;
    }
  }

  private void changed(String value) {
    status = value;
    if (engine.call == null) {
      closeService(); releaseAudio();
      // Native callbacks must finish before a stopped screen releases the core.
      if (!visible) main.post(() -> { if (!visible && engine.call == null) { engine.stop(); configuration = null; } });
    } else if (!visible && ongoing()) engine.background(true);
    MainActivity activity = screen.get();
    if (activity != null) activity.callChanged(value);
    CallService.refresh();
  }

  void acquireAudio() {
    if (audioFocus != null) return;
    AudioManager audio = context.getSystemService(AudioManager.class);
    long owner = ++focusEpoch;
    audioFocus = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
        .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
        .setOnAudioFocusChangeListener(change -> {
          if (owner == focusEpoch && change == AudioManager.AUDIOFOCUS_LOSS) engine.hangup();
        }).build();
    audio.requestAudioFocus(audioFocus); audio.setMode(AudioManager.MODE_IN_COMMUNICATION);
  }

  void releaseAudio() {
    focusEpoch++;
    if (audioFocus != null) {
      AudioManager audio = context.getSystemService(AudioManager.class);
      audio.abandonAudioFocusRequest(audioFocus); audio.setMode(AudioManager.MODE_NORMAL); audioFocus = null;
    }
    muted = false; output = CallEngine.Output.SPEAKER;
  }

  void stop() {
    epoch++; main.removeCallbacks(poll);
    engine.stop(); configuration = null; closeService(); releaseAudio();
  }

  void serviceDestroyed() {
    if (serviceRequested && ongoing()) { stop(); changed("Call ended"); }
    serviceRequested = false;
  }

  void serviceFailed() {
    stop();
    MainActivity activity = screen.get();
    if (activity != null) activity.callServiceUnavailable();
  }

  private void closeService() {
    serviceRequested = false;
    context.stopService(new Intent(context, CallService.class));
  }

  // Active background calls still observe revocation. There is no poll or SIP core while idle/closed.
  private void poll() {
    if (visible || !ongoing()) return;
    if (fetching) { main.postDelayed(poll, 1000); return; }
    fetching = true; long ticket = epoch;
    network.execute(() -> {
      JSONObject next = null; Exception failure = null;
      try {
        Enrollment enrollment = PushAlerts.enrollment(context);
        if (enrollment == null) throw new ServerApi.AccessRevoked();
        next = ServerApi.configuration(enrollment);
      } catch (Exception error) { failure = error; }
      JSONObject result = next; Exception error = failure;
      main.post(() -> {
        fetching = false;
        if (ticket != epoch || visible || !ongoing()) return;
        if (error == null) { configuration = result; engine.refresh(result); reconnecting = false; }
        else if (ServerApi.temporaryFailure(error)) reconnecting = true;
        else { stop(); changed("Call ended"); return; }
        CallService.refresh(); main.postDelayed(poll, 10000);
      });
    });
  }
}
