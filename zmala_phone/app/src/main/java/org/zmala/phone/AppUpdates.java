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
import java.net.HttpURLConnection;
import java.net.URI;
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
  private String status;
  private AlertDialog dialog;
  private TextView statusView;
  private Button updateButton;
  private ProgressBar progressView;
  private int downloadPercent = -1;
  private String displayLocales = "";
  private long idleSince;
  private final Runnable tick = this::tick;

  private AppUpdates(Context context) {
    this.context = context;
    status = context.getString(R.string.check_newer);
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
    String locales = activity.getResources().getConfiguration().getLocales().toLanguageTags();
    if (!displayLocales.equals(locales) && !downloading) status = activity.getString(R.string.check_newer);
    displayLocales = locales;
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
    progressView = new ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal);
    progressView.setMax(100); body.addView(progressView, new LinearLayout.LayoutParams(-1, -2));
    if (Build.VERSION.SDK_INT >= 31) {
      Switch toggle = new Switch(activity);
      toggle.setText(context.getString(R.string.automatic_updates));
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
    explanation.setText(context.getString(R.string.update_explanation));
    body.addView(explanation);
    ScrollView scroll = new ScrollView(activity); scroll.addView(body);
    dialog = new AlertDialog.Builder(activity).setTitle(context.getString(R.string.updates_title)).setView(scroll)
        .setPositiveButton(context.getString(R.string.update), null).setNeutralButton(context.getString(R.string.check_now), null)
        .setNegativeButton(context.getString(R.string.later), (d, which) -> {
          requested = false;
          prefs.edit().putLong("later_until", System.currentTimeMillis() + 86400000L).apply();
        }).create();
    dialog.setOnDismissListener(d -> { dialog = null; statusView = null; updateButton = null; progressView = null; });
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
        available == null ? status : context.getString(R.string.version_available, available.version, status));
    if (updateButton != null) updateButton.setEnabled(available != null && !downloading
        && UpdateGate.INSTANCE.idle(System.currentTimeMillis()));
    if (progressView != null) {
      progressView.setVisibility(downloading || checking || UpdateGate.INSTANCE.installing()
          ? android.view.View.VISIBLE : android.view.View.GONE);
      progressView.setIndeterminate(downloadPercent < 0);
      if (downloadPercent >= 0) progressView.setProgress(downloadPercent);
    }
  }

  boolean hasUpdate() { return available != null; }
  void interaction() { idleSince = SystemClock.elapsedRealtime(); }

  private void reportProgress(String text, int percent) {
    main.post(() -> { status = text; downloadPercent = percent; render(); });
  }

  private void dismiss() { if (dialog != null) dialog.dismiss(); }
  private boolean installerAllowed() { return context.getPackageManager().canRequestPackageInstalls(); }
  private void installPermission(Activity activity) {
    try {
      activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
          Uri.parse("package:" + context.getPackageName())));
    } catch (Exception error) { status = context.getString(R.string.install_permission); render(); }
  }

  synchronized void check(boolean forced, Runnable finished) {
    long now = System.currentTimeMillis(), last = prefs.getLong("checked", 0);
    if (checking || !UpdateGate.INSTANCE.idle(now) || (!forced && now >= last && now - last < 21600000L)) {
      main.post(finished); return;
    }
    checking = true;
    prefs.edit().putLong("checked", now).apply();
    status = context.getString(R.string.checking_updates); render();
    worker.execute(() -> {
      UpdatePolicy candidate = null;
      String json = null, message;
      try {
        String received = UpdateHttp.metadata();
        candidate = UpdatePolicy.parse(received, version());
        json = received;
        message = candidate == null ? context.getString(R.string.latest_version) : context.getString(R.string.ready_download);
      } catch (Exception error) { message = context.getString(R.string.check_failed); }
      UpdatePolicy result = candidate; String cached = json, text = message;
      main.post(() -> {
        checking = false; status = text;
        if (cached != null) { available = result; prefs.edit().putString("release", cached).apply(); }
        MainActivity activity = screen.get();
        if (activity != null) activity.updateAvailabilityChanged();
        render(); finished.run();
      });
    });
  }

  private boolean continueDownload() {
    return foreground && UpdateGate.INSTANCE.idle(System.currentTimeMillis());
  }

  private void startDownload() {
    if (!idle() || downloading || available == null || !installerAllowed()) return;
    downloading = true; requested = false;
    UpdatePolicy release = available;
    boolean userRequested = manual;
    status = context.getString(R.string.download_zero); downloadPercent = 0; render();
    worker.execute(() -> {
      File apk = new File(context.getCacheDir(), "zmalaphone-update.apk");
      try {
        if (!continueDownload()) throw new InterruptedException();
        HttpURLConnection connection = UpdateHttp.connect(new URI(release.url), true);
        try (InputStream in = connection.getInputStream(); OutputStream out = new FileOutputStream(apk)) {
          MessageDigest hash = MessageDigest.getInstance("SHA-256");
          byte[] buffer = new byte[65536]; long size = 0, start = SystemClock.elapsedRealtime(), reportedAt = start; int count;
          while ((count = in.read(buffer)) != -1) {
            if (!continueDownload()) throw new InterruptedException();
            if (size + count > release.size || SystemClock.elapsedRealtime() - start > 600000)
              throw new IOException("Download limit");
            out.write(buffer, 0, count); hash.update(buffer, 0, count); size += count;
            long now = SystemClock.elapsedRealtime();
            if (now - reportedAt >= 500 || size == release.size) {
              int percent = (int) (size * 100 / release.size);
              reportProgress(context.getString(R.string.downloading_percent, percent), percent); reportedAt = now;
            }
          }
          if (size != release.size || !hex(hash.digest()).equals(release.digest))
            throw new IOException("Download verification failed");
        } finally { connection.disconnect(); }
        reportProgress(context.getString(R.string.checking_update), -1);
        verify(apk, release);
        if (!continueDownload()) throw new InterruptedException();
        // Stage without committing; incoming calls still take priority while bytes are copied.
        reportProgress(context.getString(R.string.preparing_install), -1);
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
          status = paused ? context.getString(R.string.update_paused)
              : context.getString(R.string.download_failed);
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
      status = context.getString(R.string.installing_update); downloadPercent = -1; render();
    } catch (Exception error) {
      installer.abandonSession(id); finish(context.getString(R.string.installation_failed));
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
      finish(context.getString(R.string.confirmation_needed));
    } else finish(result == PackageInstaller.STATUS_SUCCESS ? context.getString(R.string.update_installed) : context.getString(R.string.update_not_installed));
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
