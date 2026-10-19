package org.zmala.phone;

import android.app.*;
import android.app.job.*;
import android.content.*;
import android.content.pm.*;
import android.net.*;
import android.os.*;
import android.provider.Settings;
import android.widget.*;
import java.io.*;
import java.lang.ref.WeakReference;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.concurrent.Executors;

// @llr LLR-AND-UPDATE-002
/** No enrollment data, server bearer tokens or GitHub credentials enter this update channel. */
final class AppUpdates {
  private static AppUpdates instance;
  static synchronized AppUpdates get(Context context) {
    if (instance == null) instance = new AppUpdates(context.getApplicationContext());
    return instance;
  }

  private final Context context;
  private final SharedPreferences prefs;
  private final Handler main = new Handler(Looper.getMainLooper());
  private final java.util.concurrent.ExecutorService worker = Executors.newSingleThreadExecutor();
  private final PackageInstaller installer;
  private WeakReference<MainActivity> screen = new WeakReference<>(null);
  private volatile boolean foreground, downloading;
  private boolean checking, requested, manual;
  private UpdatePolicy available;
  private String status = "Check for a newer version.";
  private AlertDialog dialog;
  private TextView statusView;
  private Button updateButton;
  private String offered = "";
  private long idleSince;
  private final Runnable tick = this::tick;

  private AppUpdates(Context context) {
    this.context = context;
    prefs = context.getSharedPreferences("updates", 0);
    installer = context.getPackageManager().getPackageInstaller();
    recoverSession();
    String cached = prefs.getString("release", "");
    try { if (!cached.isEmpty()) available = UpdatePolicy.parse(cached, version()); }
    catch (Exception ignored) { prefs.edit().remove("release").apply(); }
    UpdateGate.INSTANCE.ring(prefs.getLong("ring_until", 0));
  }

  String version() {
    try { return context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName; }
    catch (Exception error) { return "unknown"; }
  }

  void attach(MainActivity activity) {
    screen = new WeakReference<>(activity);
    foreground = true;
    recoverSession();
    idleSince = SystemClock.elapsedRealtime();
    JobScheduler jobs = context.getSystemService(JobScheduler.class);
    if (jobs.getPendingJob(9037) == null)
      jobs.schedule(new JobInfo.Builder(9037, new ComponentName(context, UpdateJob.class))
          .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPersisted(true)
          .setPeriodic(24 * 60 * 60 * 1000L).build());
    check(false, () -> {});
    main.removeCallbacks(tick);
    main.postDelayed(tick, 1000);
  }

  void detach() {
    foreground = false;
    main.removeCallbacks(tick);
    dismiss();
    screen.clear();
  }

  void callChanged() {
    idleSince = SystemClock.elapsedRealtime();
    if (!UpdateGate.INSTANCE.idle(System.currentTimeMillis())) dismiss();
  }

  boolean ring(long expires) {
    if (!UpdateGate.INSTANCE.ring(expires)) return false;
    prefs.edit().putLong("ring_until", expires).apply();
    main.post(this::callChanged);
    return true;
  }

  private boolean idle() {
    return foreground && screen.get() != null && screen.get().updatesAllowed()
        && UpdateGate.INSTANCE.idle(System.currentTimeMillis());
  }

  private boolean automatic() {
    return Build.VERSION.SDK_INT >= 31 && prefs.getBoolean("automatic", false);
  }

  private void tick() {
    if (!foreground) return;
    if (!idle()) idleSince = SystemClock.elapsedRealtime();
    if (idle() && available != null && !downloading) {
      long now = System.currentTimeMillis();
      boolean later = prefs.getLong("later_until", 0) > now;
      boolean fallback = available.version.equals(prefs.getString("manual_required", ""));
      if (automatic() && !fallback && !later && installerAllowed()
          && !context.getSystemService(ConnectivityManager.class).isActiveNetworkMetered()
          && SystemClock.elapsedRealtime() - idleSince >= 30000) {
        requested = true; manual = false;
      }
      if (requested) startDownload();
      else if (!later && !available.version.equals(offered) && dialog == null) {
        offered = available.version;
        show();
      }
    }
    main.postDelayed(tick, 1000);
  }

  void show() {
    MainActivity activity = screen.get();
    if (activity == null || !idle() || dialog != null) return;
    LinearLayout body = new LinearLayout(activity);
    body.setOrientation(LinearLayout.VERTICAL);
    int pad = (int) (20 * activity.getResources().getDisplayMetrics().density);
    body.setPadding(pad, pad / 2, pad, pad / 2);
    statusView = new TextView(activity);
    statusView.setTextSize(16);
    body.addView(statusView);
    if (Build.VERSION.SDK_INT >= 31) {
      Switch toggle = new Switch(activity);
      toggle.setText("Automatic updates on Wi-Fi");
      toggle.setMinHeight(pad * 3);
      toggle.setChecked(automatic());
      toggle.setOnCheckedChangeListener((button, enabled) -> {
        prefs.edit().putBoolean("automatic", enabled).apply();
        if (!enabled && !manual) requested = false;
        if (enabled && !installerAllowed()) installPermission(activity);
      });
      body.addView(toggle);
    }
    TextView explanation = new TextView(activity);
    explanation.setText("Updates wait while calls ring or are connected. Automatic installation runs only"
        + " while ZmalaPhone is open and idle; Android may still ask you to confirm. Your setup is kept.");
    body.addView(explanation);
    dialog = new AlertDialog.Builder(activity).setTitle("ZmalaPhone updates").setView(body)
        .setPositiveButton("Update", null).setNeutralButton("Check now", null)
        .setNegativeButton("Later", (d, which) -> {
          requested = false;
          prefs.edit().putLong("later_until", System.currentTimeMillis() + 86400000L).apply();
        }).create();
    dialog.setOnDismissListener(d -> { dialog = null; statusView = null; updateButton = null; });
    dialog.show();
    updateButton = dialog.getButton(AlertDialog.BUTTON_POSITIVE);
    updateButton.setOnClickListener(v -> {
      if (!idle()) return;
      requested = true; manual = true;
      prefs.edit().remove("later_until").apply();
      if (!installerAllowed()) installPermission(activity);
      else startDownload();
    });
    dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v -> check(true, () -> {}));
    render();
  }

  private void render() {
    if (statusView != null) statusView.setText(
        (available == null ? "" : "Version " + available.version + " is available.\n\n") + status);
    if (updateButton != null) updateButton.setEnabled(available != null && !downloading);
  }

  private void dismiss() { if (dialog != null) dialog.dismiss(); }
  private boolean installerAllowed() { return context.getPackageManager().canRequestPackageInstalls(); }
  private void installPermission(Activity activity) {
    try {
      activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
          Uri.parse("package:" + context.getPackageName())));
    } catch (Exception error) { status = "Allow app installation in Android Settings, then try again."; render(); }
  }

  synchronized void check(boolean forced, Runnable finished) {
    long now = System.currentTimeMillis(), last = prefs.getLong("checked", 0);
    if (checking || !UpdateGate.INSTANCE.idle(now) || (!forced && now >= last && now - last < 21600000L)) {
      main.post(finished); return;
    }
    checking = true;
    prefs.edit().putLong("checked", now).apply();
    status = "Checking for updates…"; render();
    worker.execute(() -> {
      UpdatePolicy candidate = null;
      String json = null, message;
      try {
        HttpURLConnection connection = connect(new URI(UpdatePolicy.API), false);
        try (InputStream in = connection.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
          byte[] buffer = new byte[8192]; int count;
          while ((count = in.read(buffer)) != -1) {
            if (out.size() + count > 1048576) throw new IOException("Metadata limit");
            out.write(buffer, 0, count);
          }
          String received = out.toString(StandardCharsets.UTF_8.name());
          candidate = UpdatePolicy.parse(received, version());
          json = received;
        } finally { connection.disconnect(); }
        message = candidate == null ? "You have the latest available version." : "Ready to download.";
      } catch (Exception error) { message = "Could not check for updates. Try again later."; }
      UpdatePolicy result = candidate; String cached = json, text = message;
      main.post(() -> {
        checking = false; status = text;
        if (cached != null) { available = result; prefs.edit().putString("release", cached).apply(); }
        render(); finished.run();
      });
    });
  }

  static HttpURLConnection connect(URI start, boolean download) throws Exception {
    URI uri = start;
    for (int hop = 0; hop < 6; hop++) {
      if (download ? !UpdatePolicy.allowedDownload(uri) : !UpdatePolicy.API.equals(uri.toString()))
        throw new IOException("Untrusted update address");
      HttpURLConnection connection = (HttpURLConnection) uri.toURL().openConnection();
      connection.setConnectTimeout(10000); connection.setReadTimeout(10000);
      connection.setInstanceFollowRedirects(false);
      connection.setRequestProperty("User-Agent", "ZmalaPhone-updater");
      connection.setRequestProperty("Accept", download ? "application/octet-stream" : "application/vnd.github+json");
      int code;
      try { code = connection.getResponseCode(); }
      catch (Exception error) { connection.disconnect(); throw error; }
      if (code == 200) return connection;
      String location = connection.getHeaderField("Location");
      connection.disconnect();
      if (!download || !java.util.Arrays.asList(301, 302, 303, 307, 308).contains(code) || location == null)
        throw new IOException("Update server unavailable");
      uri = uri.resolve(location);
    }
    throw new IOException("Too many redirects");
  }

  private boolean continueDownload() {
    return foreground && UpdateGate.INSTANCE.idle(System.currentTimeMillis());
  }

  private void startDownload() {
    if (!idle() || downloading || available == null || !installerAllowed()) return;
    downloading = true; requested = false;
    UpdatePolicy release = available;
    boolean userRequested = manual;
    status = "Downloading update…"; render();
    worker.execute(() -> {
      File apk = new File(context.getCacheDir(), "zmalaphone-update.apk");
      try {
        if (!continueDownload()) throw new InterruptedException();
        HttpURLConnection connection = connect(new URI(release.url), true);
        try (InputStream in = connection.getInputStream(); OutputStream out = new FileOutputStream(apk)) {
          MessageDigest hash = MessageDigest.getInstance("SHA-256");
          byte[] buffer = new byte[65536]; long size = 0, start = SystemClock.elapsedRealtime(); int count;
          while ((count = in.read(buffer)) != -1) {
            if (!continueDownload()) throw new InterruptedException();
            if (size + count > release.size || SystemClock.elapsedRealtime() - start > 600000)
              throw new IOException("Download limit");
            out.write(buffer, 0, count); hash.update(buffer, 0, count); size += count;
          }
          if (size != release.size || !hex(hash.digest()).equals(release.digest))
            throw new IOException("Download verification failed");
        } finally { connection.disconnect(); }
        verify(apk, release);
        if (!continueDownload()) throw new InterruptedException();
        // Stage without committing; incoming calls still take priority while bytes are copied.
        PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(context.getPackageName()); params.setSize(apk.length());
        if (Build.VERSION.SDK_INT >= 31) params.setRequireUserAction(userRequested
            ? PackageInstaller.SessionParams.USER_ACTION_REQUIRED : PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED);
        int id = installer.createSession(params);
        try (PackageInstaller.Session session = installer.openSession(id)) {
          try (InputStream in = new FileInputStream(apk); OutputStream out = session.openWrite("base.apk", 0, apk.length())) {
            byte[] bytes = new byte[65536]; int count;
            while ((count = in.read(bytes)) != -1) {
              if (!continueDownload()) throw new InterruptedException();
              out.write(bytes, 0, count);
            }
            session.fsync(out);
          }
        } catch (Exception error) { installer.abandonSession(id); throw error; }
        Files.deleteIfExists(apk.toPath());
        main.post(() -> commit(id, release, userRequested));
      } catch (Exception error) {
        try { Files.deleteIfExists(apk.toPath()); } catch (Exception ignored) {}
        boolean paused = error instanceof InterruptedException;
        main.post(() -> {
          downloading = false;
          requested = paused && userRequested;
          status = paused ? "Update paused until the app is open and calls have ended."
              : "Update could not be downloaded or verified. Try again later.";
          // Never retry a broken download in a tight automatic loop.
          if (!paused) prefs.edit().putLong("later_until", System.currentTimeMillis() + 21600000L).apply();
          render();
        });
      }
    });
  }

  static String hex(byte[] bytes) {
    StringBuilder value = new StringBuilder();
    for (byte b : bytes) value.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
    return value.toString();
  }

  private void verify(File apk, UpdatePolicy release) throws Exception {
    PackageManager pm = context.getPackageManager();
    PackageInfo candidate = pm.getPackageArchiveInfo(apk.getAbsolutePath(), PackageManager.GET_SIGNING_CERTIFICATES);
    PackageInfo installed = pm.getPackageInfo(context.getPackageName(), PackageManager.GET_SIGNING_CERTIFICATES);
    if (candidate == null || candidate.applicationInfo == null || !UpdatePolicy.validPackage(
        candidate.packageName, candidate.versionName, candidate.getLongVersionCode(), installed.getLongVersionCode(),
        (candidate.applicationInfo.flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0,
        signers(candidate), signers(installed), release.version)) throw new IOException("Wrong signed package");
    // Android's installer performs the final cryptographic APK signature verification.
  }

  private static byte[][] signers(PackageInfo info) {
    if (info.signingInfo == null) return null;
    Signature[] signatures = info.signingInfo.getApkContentsSigners();
    byte[][] bytes = new byte[signatures.length][];
    for (int i = 0; i < bytes.length; i++) bytes[i] = signatures[i].toByteArray();
    return bytes;
  }

  private void commit(int id, UpdatePolicy release, boolean userRequested) {
    downloading = false;
    if (!idle() || !installerAllowed() || (!userRequested && (!automatic()
        || context.getSystemService(ConnectivityManager.class).isActiveNetworkMetered()))
        || !UpdateGate.INSTANCE.beginInstall(System.currentTimeMillis())) {
      installer.abandonSession(id); requested = userRequested; return;
    }
    prefs.edit().putInt("session", id).putString("install_version", release.version)
        .putBoolean("manual_install", userRequested).commit();
    try (PackageInstaller.Session session = installer.openSession(id)) {
      Intent result = new Intent(context, UpdateResult.class).setAction("org.zmala.phone.UPDATE_RESULT");
      int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
      session.commit(PendingIntent.getBroadcast(context, id, result, flags).getIntentSender());
      status = "Installing update…"; dismiss();
    } catch (Exception error) {
      installer.abandonSession(id); finish("Installation failed. Try again later.");
    }
  }

  void result(Intent intent) {
    int id = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1);
    if (id < 0 || id != prefs.getInt("session", -1)) return;
    int result = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
    if (result == PackageInstaller.STATUS_PENDING_USER_ACTION) {
      Intent approval = intent.getParcelableExtra(Intent.EXTRA_INTENT);
      MainActivity activity = screen.get();
      if (prefs.getBoolean("manual_install", false) && foreground && activity != null && approval != null) {
        try { activity.startActivity(approval); return; } catch (Exception ignored) {}
      }
      prefs.edit().putString("manual_required", prefs.getString("install_version", "")).apply();
      installer.abandonSession(id);
      finish("Android needs your confirmation. Tap Update to continue.");
    } else finish(result == PackageInstaller.STATUS_SUCCESS ? "Update installed." : "Update was not installed. You can try again.");
  }

  private void finish(String text) {
    prefs.edit().remove("session").remove("install_version").apply();
    UpdateGate.INSTANCE.restoreInstall(false);
    status = text; idleSince = SystemClock.elapsedRealtime(); render();
  }

  private void recoverSession() {
    int id = prefs.getInt("session", -1);
    PackageInstaller.SessionInfo session = id < 0 ? null : installer.getSessionInfo(id);
    if (session == null) prefs.edit().remove("session").apply();
    UpdateGate.INSTANCE.restoreInstall(session != null);
    // Clean unfinished staging sessions left by process death. Never abandon a committed install.
    for (PackageInstaller.SessionInfo other : installer.getMySessions())
      if (other.getSessionId() != id) installer.abandonSession(other.getSessionId());
  }
}
