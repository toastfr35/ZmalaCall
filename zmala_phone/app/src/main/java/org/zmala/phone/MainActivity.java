package org.zmala.phone;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.hardware.display.DisplayManager;
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
      BLUE = Color.rgb(33, 91, 164),
      GREEN = Color.rgb(33, 122, 80),
      RED = Color.rgb(183, 47, 63);
  private final Handler main = new Handler(Looper.getMainLooper());
  private final ExecutorService network = Executors.newSingleThreadExecutor();
  private final PortraitLoader portraits = new PortraitLoader();
  private CallSession session;
  private CallEngine engine;
  private Enrollment enrollment;
  private JSONObject config;
  private LinearLayout page;
  private int generation;
  private boolean visible, fetching, muted;
  private boolean reconnecting;
  private TextView updateLink;
  private final Runnable videoProgress = new Runnable() {
    public void run() {
      if (visible && engine.call != null && callScreen != null) {
        updateCallProgress();
        if (!engine.remoteVideoReady()) main.postDelayed(this, 1000);
      }
    }
  };
  private CallEngine.Output output = CallEngine.Output.SPEAKER;
  private Call displayedCall;
  private String selectedContact;
  private String callbackContact;
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
  private String message = "";
  private static java.lang.ref.WeakReference<MainActivity> foreground =
      new java.lang.ref.WeakReference<>(null);
  private String answerCallId;
  private long answerExpires;
  private boolean pushReady, pushPreparing;
  private boolean restartRequested;
  // @llr LLR-AND-HISTORY-002
  private boolean callbackSending;
  private String displayedNotices = "";
  private AlertDialog contactDialog;
  private final Runnable poll = () -> refresh(false);

  @Override
  public void onCreate(Bundle state) {
    super.onCreate(state);
    session = CallSession.get(this); engine = session.engine;
    config = session.configuration;
    selectedContact = state == null ? null : state.getString("selected_contact");
    callbackContact = state == null ? null : state.getString("callback_contact");
    message = getString(R.string.welcome);
    if (android.os.Build.VERSION.SDK_INT >= 33)
      getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::navigateBack);
    handlePushIntent(getIntent());
    handleCallbackIntent(getIntent());
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
    session.attach(this);
    muted = session.muted; output = session.output; reconnecting = session.reconnecting;
    if (session.configuration != null) config = session.configuration;
    foreground = new java.lang.ref.WeakReference<>(this);
    ((DisplayManager) getSystemService(DISPLAY_SERVICE))
        .registerDisplayListener(displayListener, main);
    if (enrollment == null && enrollmentFile().isFile()) {
      try {
        enrollment =
            new Enrollment(
                new String(Files.readAllBytes(enrollmentFile().toPath()), StandardCharsets.UTF_8));
      } catch (Exception e) {
        message = getString(R.string.scan_new_qr);
      }
    }
    if (enrollment != null && permissions()) {
      if (engine.call != null) callChanged(session.status);
      refresh(engine.call == null);
    } else directory();
  }

  @Override
  public void onStop() {
    visible = false;
    if (foreground.get() == this) foreground.clear();
    ((DisplayManager) getSystemService(DISPLAY_SERVICE)).unregisterDisplayListener(displayListener);
    generation++;
    portraits.begin();
    fetching = false;
    main.removeCallbacks(poll);
    main.removeCallbacks(videoProgress);
    session.detach(this, isChangingConfigurations());
    silence();
    if (!session.ongoing()) releaseAudio();
    else setVolumeControlStream(AudioManager.USE_DEFAULT_STREAM_TYPE);
    displayedCall = null;
    if (callScreen != null) callScreen.dispose();
    callScreen = null;
    getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    super.onStop();
  }

  @Override
  public void onDestroy() {
    network.shutdownNow();
    portraits.close();
    super.onDestroy();
  }

  // @llr LLR-AND-UPDATE-002
  @Override public void onResume() {
    super.onResume();
    AppUpdates.get(this).attach(this);
  }

  // @llr LLR-AND-UPDATE-002
  @Override public void onPause() {
    AppUpdates.get(this).detach();
    super.onPause();
  }

  // @llr LLR-AND-UPDATE-002
  boolean updatesAllowed() {
    return visible && enrollment != null && config != null && selectedContact == null && engine.call == null;
  }

  @Override public void onUserInteraction() { super.onUserInteraction(); AppUpdates.get(this).interaction(); }

  void updateAvailabilityChanged() {
    if (updateLink != null) updateLink.setText(AppUpdates.get(this).hasUpdate() ? getString(R.string.update_available) : getString(R.string.updates));
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
            getString(R.string.media_permissions);
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
        .setPrompt(getString(R.string.scanner_prompt))
        .setBeepEnabled(false)
        .setOrientationLocked(false)
        .initiateScan();
  }

  @Override
  protected void onActivityResult(int request, int result, Intent data) {
    super.onActivityResult(request, result, data);
    if (request == 9) {
      if (result != RESULT_OK || data == null || data.getData() == null) return;
      android.net.Uri uri = data.getData();
      int ticket = generation;
      network.execute(() -> {
        try {
          String text = QrImage.read(getContentResolver().openInputStream(uri));
          main.post(() -> { if (visible && generation == ticket) confirmEnrollment(text); });
        } catch (Exception error) {
          main.post(() -> { if (visible && generation == ticket)
            showError(getString(R.string.qr_image_error)); });
        }
      });
      return;
    }
    IntentResult scan = IntentIntegrator.parseActivityResult(request, result, data);
    if (scan == null || scan.getContents() == null) return;
    confirmEnrollment(scan.getContents());
  }

  // @llr LLR-AND-ENROLL-002
  private void openQrImage() {
    Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("image/*")
        .addCategory(Intent.CATEGORY_OPENABLE).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
    try { startActivityForResult(pick, 9); }
    catch (android.content.ActivityNotFoundException error) { showError(getString(R.string.no_picker)); }
  }

  private void confirmEnrollment(String text) {
    try {
      Enrollment candidate = new Enrollment(text);
      new AlertDialog.Builder(this)
          .setTitle(getString(R.string.connect_title))
          .setMessage(
              candidate.server.toString()
                  + (candidate.server.getScheme().equals("http")
                      ? getString(R.string.lan_warning)
                      : getString(R.string.secure_confirm)))
          .setPositiveButton(
              getString(R.string.connect),
              (dialog, which) -> {
                generation++;
                enrollment = candidate;
                config = null;
                session.stop();
                refresh(true);
              })
          .setNegativeButton(getString(R.string.cancel), null)
          .show();
    } catch (Exception e) {
      showError(getString(R.string.setup_invalid));
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
    // @llr LLR-AND-HISTORY-003
    long callbackTicket = CallbackAlerts.beginRefresh();
    if (config == null) {
      message = getString(R.string.connecting_server);
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
                    if (callbackContact != null) { selectedContact = callbackContact; callbackContact = null; }
                    session.configuration = next;
                    reconnecting = false; session.reconnecting = false;
                    if (callScreen != null) callScreen.connectionNotice(null);
                    PushAlerts.remember(this, next);
                    // @llr LLR-AND-HISTORY-003
                    CallbackAlerts.synchronize(this,target,next,callbackTicket);
                    boolean restart = restartRequested;
                    restartRequested = false;
                    if ((restart || credentialsChanged) && engine.call == null)
                      engine.start(this, next);
                    else engine.refresh(next);
                    if (engine.call == null) registerPush();
                    // @llr LLR-AND-HISTORY-002
                    boolean noticesChanged = !CallNotices.snapshot(this, next.getJSONArray("contacts"))
                        .toString().equals(displayedNotices);
                    if ((changed || noticesChanged) && engine.call == null) directory();
                  } catch (Exception e) {
                    session.stop();
                    showError(getString(R.string.calling_setup_failed));
                  }
                  main.removeCallbacks(poll);
                  main.postDelayed(poll, 10000);
                });
          } catch (Exception e) {
            main.post(
                () -> {
                  if (!visible || ticket != generation) return;
                  fetching = false;
                  boolean temporary = ServerApi.temporaryFailure(e);
                  if (e instanceof ServerApi.AccessRevoked) CallbackAlerts.revoked(this,target);
                  reconnecting = temporary; session.reconnecting = temporary;
                  // An HTTP polling outage must not tear down an established media call.
                  // Revocation or malformed security/configuration data still stop it immediately.
                  if (!temporary || engine.call == null) session.stop();
                  if (!temporary) config = null;
                  if (engine.call == null) { silence(); releaseAudio(); }
                  message =
                      temporary ? getString(R.string.reconnect_help)
                      : e instanceof IllegalArgumentException || e instanceof IllegalStateException
                          ? getString(R.string.access_revoked)
                          : getString(R.string.cannot_reach);
                  if (engine.call == null) directory();
                  else if (callScreen != null) callScreen.connectionNotice(getString(R.string.reconnecting_server));
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
    if (!message.equals(getString(R.string.ready))) page.addView(label(message, 16, MUTED));
    if (config == null) {
      ScrollView setup = new ScrollView(this); setup.setFillViewport(true);
      setup.addView(page); setContentView(setup);
    } else setContentView(page);
  }

  private void directory() {
    long portraitTicket = portraits.begin();
    setRequestedOrientation(enrollment != null && config != null
        ? android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
        : android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
    displayedCall = null;
    callScreen = null;
    if (selectedContact != null && config != null) {
      JSONObject selected = findContact(selectedContact);
      if (selected != null && selected.optBoolean("can_call")) { contactPage(selected, portraitTicket); return; }
      selectedContact = null;
    }
    shell();
    if (enrollment == null) {
      page.addView(label(getString(R.string.tagline), 26, FG));
      page.addView(label(getString(R.string.setup_intro), 18, MUTED));
      page.addView(button(getString(R.string.scan_qr), GREEN, this::scan));
      page.addView(button(getString(R.string.open_qr_image), PANEL, this::openQrImage));
      page.addView(label(getString(R.string.qr_image_hint), 16, MUTED));
    } else if (config == null) page.addView(button(getString(R.string.retry_connection), GREEN, () -> refresh(true)));
    else {
      ScrollView scroll = new ScrollView(this);
      scroll.setFillViewport(true);
      LinearLayout contacts = new LinearLayout(this);
      contacts.setOrientation(LinearLayout.VERTICAL);
      contacts.setGravity(Gravity.CENTER_VERTICAL);
      scroll.addView(contacts);
      page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
      JSONArray entries = config.optJSONArray("contacts");
      // @llr LLR-AND-HISTORY-002
      NoticeBook notices = CallNotices.snapshot(this, entries == null ? new JSONArray() : entries);
      displayedNotices = notices.toString();
      int count = 0;
      if (entries != null)
        for (int i = 0; i < entries.length(); i++) {
          JSONObject contact = entries.optJSONObject(i);
          if (!contact.optBoolean("can_call")) continue;
          count++;
          int missed = notices.count(contact.optString("id"));
          int callbacks = NoticeBook.callbacks(config.optJSONArray("callbacks"),
              config.optJSONObject("sip").optString("username"), contact.optString("id"));
          boolean online = contact.optBoolean("online");
          boolean pushOnly = online && "push".equals(contact.optString("presence"));
          ContactCard card = new ContactCard(this, contact.optString("name"), presence(contact),
              ContactNotice.summary(this, missed, callbacks), !online ? RED : pushOnly ? BLUE : GREEN,
              () -> { selectedContact = contact.optString("id"); directory(); });
          LinearLayout.LayoutParams margins = new LinearLayout.LayoutParams(-1, -2);
          margins.setMargins(0, dp(4), 0, dp(4)); contacts.addView(card, margins);
          loadPortrait(card.portrait, contact.optString("photo"), portraitTicket);
        }
      if (count == 0)
        contacts.addView(
            label(
                getString(R.string.no_contacts),
                20,
                MUTED));
    }
    if (enrollment != null && config != null) footer();
  }

  // @llr LLR-AND-CALL-004, LLR-AND-UPDATE-002, LLR-AND-UI-002
  private void footer() {
    AlertStatus state = AlertStatus.of(config.optBoolean("push_enabled"), PushAlerts.allowed(this), pushPreparing, pushReady);
    String text = switch (state) {
      case READY -> getString(R.string.incoming_enabled);
      case NOTIFICATIONS_OFF -> getString(R.string.notifications_off);
      case SERVER_OFF -> getString(R.string.alerts_server_off);
      case PREPARING -> getString(R.string.alerts_preparing);
      case UNAVAILABLE -> getString(R.string.alerts_retry);
    };
    LinearLayout footer = new LinearLayout(this); footer.setGravity(Gravity.CENTER_VERTICAL);
    LinearLayout status = new LinearLayout(this); status.setOrientation(LinearLayout.VERTICAL);
    TextView alerts = label(text, 13, MUTED);
    if (state != AlertStatus.READY && state != AlertStatus.PREPARING) {
      alerts.setMinHeight(dp(48)); alerts.setBackground(rounded(PANEL));
      alerts.setOnClickListener(v -> {
        if (state == AlertStatus.NOTIFICATIONS_OFF) notificationSettings();
        else if (state == AlertStatus.UNAVAILABLE) registerPush();
        else new AlertDialog.Builder(this).setTitle(getString(R.string.incoming_calls))
            .setMessage(getString(R.string.alerts_server_help))
            .setPositiveButton(getString(R.string.ok), null).show();
      });
    }
    status.addView(alerts);
    status.addView(label("v" + AppUpdates.get(this).version(), 12, MUTED));
    footer.addView(status, new LinearLayout.LayoutParams(0, -2, 1));
    TextView updates = label(getString(R.string.updates), 13, MUTED); updates.setGravity(Gravity.CENTER);
    updateLink = updates; updateAvailabilityChanged();
    updates.setMinHeight(dp(60)); updates.setMinWidth(dp(80));
    updates.setContentDescription(getString(R.string.check_updates_description));
    updates.setOnClickListener(v -> AppUpdates.get(this).show()); footer.addView(updates); page.addView(footer);
  }

  private void notificationSettings() {
    android.app.NotificationChannel channel = getSystemService(android.app.NotificationManager.class)
        .getNotificationChannel(PushAlerts.CHANNEL);
    Intent settings = new Intent(channel != null && channel.getImportance() < android.app.NotificationManager.IMPORTANCE_DEFAULT
        ? android.provider.Settings.ACTION_CHANNEL_NOTIFICATION_SETTINGS : android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS);
    settings.putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, getPackageName());
    settings.putExtra(android.provider.Settings.EXTRA_CHANNEL_ID, PushAlerts.CHANNEL);
    try { startActivity(settings); } catch (Exception error) {
      showError(getString(R.string.notification_settings_help));
    }
  }

  private void loadPortrait(ImageView photo, String path, long ticket) {
    portraits.load(photo, enrollment, path, ticket);
  }

  // @llr LLR-AND-CALL-002, LLR-AND-UI-002
  void callChanged(String text) {
    // @llr LLR-AND-UPDATE-002
    AppUpdates.get(this).callChanged();
    // @llr LLR-AND-HISTORY-002
    if (engine.call != null && contactDialog != null) { contactDialog.dismiss(); contactDialog = null; }
    if (!visible) return;
    message = UiText.status(this, text);
    if (engine.call == null) {
      silence();
      releaseAudio();
      getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
      directory();
      // @llr LLR-AND-HISTORY-002
      String unanswered = engine.takeUnansweredPeer();
      if (unanswered != null && config != null && config.optBoolean("callbacks_enabled")) {
        JSONArray contacts = config.optJSONArray("contacts");
        if (contacts != null) for (int i = 0; i < contacts.length(); i++) {
          JSONObject peer = contacts.optJSONObject(i);
          if (unanswered.equals(peer.optString("id")) && peer.optBoolean("can_call")) {
            contactDialog = new AlertDialog.Builder(this).setTitle(getString(R.string.call_not_answered))
                .setMessage(getString(R.string.callback_prompt, peer.optString("name")))
                .setPositiveButton(getString(R.string.request_callback), (d, which) -> requestCallback(peer))
                .setNegativeButton(getString(R.string.not_now), null).show();
            break;
          }
        }
      }
      return;
    }
    portraits.begin();
    setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
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
              if (session.prepare()) engine.answer();
            });
        return;
      }
      String user = engine.call.getRemoteAddress().getUsername();
      String name = user;
      String photo = "";
      JSONArray contacts = config.optJSONArray("contacts");
      if (contacts != null)
        for (int i = 0; i < contacts.length(); i++)
          if (user.equals(contacts.optJSONObject(i).optString("id"))) {
            name = contacts.optJSONObject(i).optString("name");
            photo = contacts.optJSONObject(i).optString("photo");
          }
      IncomingCallScreen incoming = new IncomingCallScreen(this, name,
          () -> { if (session.prepare()) { silence(); displayedCall = null; acquireAudio(); engine.answer(); } }, engine::hangup);
      setContentView(incoming);
      loadPortrait(incoming.portrait, photo, portraits.begin());
      if (ringtone == null) {
        ringtone =
            RingtoneManager.getRingtone(
                this, RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE));
        if (ringtone != null) ringtone.play();
      }
      return;
    }
    silence();
    acquireAudio();
    callScreen =
        new CallScreen(
            this,
            muted,
            output,
            new CallScreen.Actions() {
              public void mute(boolean value) {
                muted = value; session.muted = value;
                engine.mute(value);
              }

              public CallEngine.Output output(CallEngine.Output value) {
                output = engine.output(value); session.output = output;
                return output;
              }

              public int volume(int steps) {
                AudioManager audio = (AudioManager) getSystemService(AUDIO_SERVICE);
                int maximum = audio.getStreamMaxVolume(AudioManager.STREAM_VOICE_CALL);
                int minimum = audio.getStreamMinVolume(AudioManager.STREAM_VOICE_CALL);
                int next = Math.max(minimum, Math.min(maximum,
                    audio.getStreamVolume(AudioManager.STREAM_VOICE_CALL) + steps));
                audio.setStreamVolume(AudioManager.STREAM_VOICE_CALL, next, 0);
                return Math.round(100f * next / Math.max(1, maximum));
              }

              public void camera() {
                engine.flipCamera();
              }

              public void end() {
                engine.hangup();
              }
            });
    setContentView(callScreen);
    if (reconnecting) callScreen.connectionNotice(getString(R.string.reconnecting_server));
    main.removeCallbacks(videoProgress); main.postDelayed(videoProgress, 1000);
    if (!getSharedPreferences("ui", 0).getBoolean("call_hint_seen", false)) {
      callScreen.firstCallHint();
      getSharedPreferences("ui", 0).edit().putBoolean("call_hint_seen", true).apply();
    }
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
        callScreen.progress(CallScreen.Progress.CALLING);
        break;
      case OutgoingRinging:
        callScreen.progress(CallScreen.Progress.RINGING);
        break;
      case OutgoingEarlyMedia:
        callScreen.progress(CallScreen.Progress.RINGING);
        break;
      case Connected:
      case StreamsRunning:
      case Updating:
      case UpdatedByRemote:
        callScreen.progress(engine.remoteVideoReady() ? CallScreen.Progress.NONE
            : engine.remoteVideoDelayed() ? CallScreen.Progress.DELAYED : CallScreen.Progress.CONNECTING);
        break;
      default:
        callScreen.progress(CallScreen.Progress.NONE);
        break;
    }
  }

  private JSONObject findContact(String id) {
    JSONArray contacts = config == null ? null : config.optJSONArray("contacts");
    if (contacts != null) for (int i = 0; i < contacts.length(); i++) {
      JSONObject peer = contacts.optJSONObject(i);
      if (peer != null && id.equals(peer.optString("id"))) return peer;
    }
    return null;
  }

  private String presence(JSONObject contact) {
    return !contact.optBoolean("online") ? getString(R.string.offline)
        : "push".equals(contact.optString("presence")) ? getString(R.string.try_calling) : getString(R.string.available);
  }

  // @llr LLR-AND-HISTORY-002, LLR-AND-UI-002
  private void contactPage(JSONObject contact, long ticket) {
    int missed = CallNotices.snapshot(this, config.optJSONArray("contacts")).count(contact.optString("id"));
    int callbacks = NoticeBook.callbacks(config.optJSONArray("callbacks"),
        config.optJSONObject("sip").optString("username"), contact.optString("id"));
    ContactScreen detail = new ContactScreen(this, contact.optString("name"), presence(contact),
        ContactNotice.summary(this, missed, callbacks), engine.registered && contact.optBoolean("online"),
        config.optBoolean("callbacks_enabled"), (callbacks & 2) != 0, callbackSending, missed,
        () -> { selectedContact = null; directory(); },
        () -> { try { if (session.prepare()) engine.dial(contact); } catch (Exception error) { showError(getString(R.string.start_call_failed)); } },
        () -> { if ((callbacks & 2) != 0) cancelCallback(contact); else requestCallback(contact); },
        () -> { CallNotices.clear(this, contact.optString("id")); directory(); });
    setContentView(detail); loadPortrait(detail.portrait, contact.optString("photo"), ticket);
  }

  // Android 9–12 fallback; newer phones use the predictive-back callback registered in onCreate.
  @android.annotation.SuppressLint("GestureBackNavigation")
  @Override public void onBackPressed() { navigateBack(); }

  private void navigateBack() {
    if (engine.call == null && selectedContact != null) { selectedContact = null; directory(); }
    else moveTaskToBack(true);
  }

  // @llr LLR-AND-HISTORY-002
  private void requestCallback(JSONObject contact) {
    updateCallback(contact, null);
  }

  // @llr LLR-AND-HISTORY-002
  private void cancelCallback(JSONObject contact) {
    if (config == null) return;
    JSONArray requests = config.optJSONArray("callbacks");
    String self = config.optJSONObject("sip").optString("username");
    if (requests != null) for (int i = 0; i < requests.length(); i++) {
      JSONObject request = requests.optJSONObject(i);
      if (request != null && "pending".equals(request.optString("status"))
          && self.equals(request.optString("from")) && contact.optString("id").equals(request.optString("to"))) {
        updateCallback(contact, request.optString("id")); return;
      }
    }
    refresh(false);
  }

  // @llr LLR-AND-HISTORY-002
  private void updateCallback(JSONObject contact, String cancelId) {
    if (callbackSending || enrollment == null || !contact.optBoolean("can_call")) return;
    callbackSending = true;
    if (selectedContact != null) directory();
    Enrollment target = enrollment;
    network.execute(() -> {
      boolean success;
      try {
        if (cancelId == null) ServerApi.requestCallback(target, contact.optString("id"));
        else ServerApi.cancelCallback(target, cancelId);
        success = true;
      }
      catch (Exception error) { success = false; }
      boolean sent = success;
      main.post(() -> {
        callbackSending = false;
        if (!visible || target != enrollment || engine.call != null) return;
        if (selectedContact != null) directory();
        if (sent) {
          Toast.makeText(this, cancelId == null ? getString(R.string.callback_requested) : getString(R.string.callback_cancelled), Toast.LENGTH_SHORT).show();
          refresh(false);
        } else showError(getString(R.string.callback_failed));
      });
    });
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
    session.acquireAudio();
    setVolumeControlStream(AudioManager.STREAM_VOICE_CALL);
  }

  private void releaseAudio() {
    session.releaseAudio(); muted = false; output = CallEngine.Output.SPEAKER;
    setVolumeControlStream(AudioManager.USE_DEFAULT_STREAM_TYPE);
  }

  @Override protected void onSaveInstanceState(Bundle state) {
    super.onSaveInstanceState(state);
    state.putString("selected_contact", selectedContact);
    state.putString("callback_contact", callbackContact);
  }

  private void silence() {
    if (ringtone != null) {
      ringtone.stop();
      ringtone = null;
    }
  }

  void callServiceUnavailable() {
    if (visible) { directory(); showError(getString(R.string.start_call_failed)); }
  }

  private void showError(String text) {
    message = text;
    new AlertDialog.Builder(this)
        .setTitle("ZmalaPhone")
        .setMessage(text)
        .setPositiveButton(getString(R.string.ok), null)
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
          .setTitle(getString(R.string.notification_explanation_title))
          .setMessage(
              getString(R.string.notification_explanation))
          .setPositiveButton(
              getString(R.string.continue_action),
              (dialog, which) ->
                  requestPermissions(new String[] {Manifest.permission.POST_NOTIFICATIONS}, 8))
          .setNegativeButton(getString(R.string.not_now), (dialog, which) -> registerPush())
          .show();
      return;
    }
    Enrollment target = enrollment;
    pushPreparing = !pushReady;
    PushAlerts.register(
        this,
        target,
        ready -> {
          if (enrollment != target) return;
          boolean changed = pushReady != ready || pushPreparing;
          pushPreparing = false; pushReady = ready;
          if (!visible || !changed) return;
          if (engine.call == null) directory();
        });
  }

  // @llr LLR-AND-CALL-004
  @Override
  protected void onNewIntent(Intent intent) {
    super.onNewIntent(intent);
    setIntent(intent);
    handlePushIntent(intent);
    handleCallbackIntent(intent);
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

  // @llr LLR-AND-HISTORY-003
  private void handleCallbackIntent(Intent intent) {
    String peer = intent.getStringExtra(CallbackAlerts.PEER);
    if (peer != null && peer.matches("[a-z][a-z0-9_-]{0,30}")) callbackContact = peer;
    // Wait for refresh; directory() then checks the newly authenticated contact list.
    intent.removeExtra(CallbackAlerts.PEER);
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
