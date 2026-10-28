package org.zmala.phone;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.net.Uri;
import android.os.*;
import androidx.core.app.NotificationCompat;
import java.lang.ref.WeakReference;

// @llr LLR-AND-CALL-002
/** Exists only for a user-started/answered call; never recreates one after process death. */
public final class CallService extends Service {
  static final int NOTIFICATION = 9038;
  static final String CHANNEL = "ongoing_calls", END = "org.zmala.phone.END_CALL", CALL_ID = "call_id";
  private static WeakReference<CallService> running = new WeakReference<>(null);
  private CallSession session;
  private PowerManager.WakeLock wake;
  private final Handler main = new Handler(Looper.getMainLooper());
  private final Runnable renew = new Runnable() {
    public void run() {
      if (wake != null) { wake.acquire(2 * 60 * 60 * 1000L); main.postDelayed(this, 30 * 60 * 1000L); }
    }
  };
  static void refresh() { CallService service = running.get(); if (service != null) service.update(); }

  @Override public void onCreate() {
    super.onCreate(); session = CallSession.get(this); running = new WeakReference<>(this);
    NotificationChannel channel = new NotificationChannel(CHANNEL, getString(R.string.ongoing_calls), NotificationManager.IMPORTANCE_LOW);
    channel.setSound(null, null); getSystemService(NotificationManager.class).createNotificationChannel(channel);
  }

  @Override public int onStartCommand(Intent intent, int flags, int startId) {
    if (intent != null && END.equals(intent.getAction())) {
      // A notification left over from a previous call must never hang up its replacement.
      if (CallLifetime.mayEnd(intent.getStringExtra(CALL_ID), session.callId())) session.engine.hangup();
      if (!session.ongoing()) stopSelf();
      return START_NOT_STICKY;
    }
    if (!session.serviceRequested) { stopSelf(); return START_NOT_STICKY; }
    try {
      Notification notification = notification();
      if (Build.VERSION.SDK_INT >= 30) startForeground(NOTIFICATION, notification,
          ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE | ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA);
      else startForeground(NOTIFICATION, notification);
      keepAwake(getSystemService(PowerManager.class));
      // Failed call setup cannot strand a service or wake lock.
      main.postDelayed(() -> { if (!session.ongoing()) { session.serviceRequested = false; stopSelf(); } }, 10000);
    } catch (RuntimeException denied) { session.serviceFailed(); stopSelf(); }
    return START_NOT_STICKY;
  }

  /** Repeated Android start commands renew one lock and one timer, never orphan an old lock. */
  void keepAwake(PowerManager power) {
    if (wake == null) {
      wake = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ZmalaPhone:active-call");
      wake.setReferenceCounted(false);
    }
    main.removeCallbacks(renew);
    renew.run();
  }

  void releaseWake() {
    main.removeCallbacks(renew);
    if (wake != null) { if (wake.isHeld()) wake.release(); wake = null; }
  }

  private Notification notification() {
    String id = session.callId();
    Intent open = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
    PendingIntent view = PendingIntent.getActivity(this, 9038, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL)
        .setSmallIcon(R.drawable.ic_call_notification).setContentTitle(getString(R.string.call_in_progress))
        .setContentText(getString(session.reconnecting ? R.string.reconnecting_server
            : session.visible ? R.string.return_to_call : R.string.background_audio))
        .setContentIntent(view).setOngoing(true).setOnlyAlertOnce(true)
        .setVisibility(NotificationCompat.VISIBILITY_PRIVATE).setCategory(NotificationCompat.CATEGORY_CALL)
        .addAction(0, getString(R.string.return_to_call), view);
    if (id != null && !id.isEmpty()) {
      Intent end = new Intent(this, CallService.class).setAction(END).putExtra(CALL_ID, id)
          .setData(Uri.parse("zmalaphone:ongoing/" + Uri.encode(id)));
      builder.addAction(0, getString(R.string.end_call), PendingIntent.getService(this, 9038, end,
          PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
    }
    return builder.build();
  }

  private void update() {
    if (session.serviceRequested && session.ongoing()) getSystemService(NotificationManager.class).notify(NOTIFICATION, notification());
  }
  @Override public IBinder onBind(Intent intent) { return null; }
  @Override public void onDestroy() {
    main.removeCallbacksAndMessages(null);
    releaseWake();
    if (running.get() == this) running.clear();
    stopForeground(STOP_FOREGROUND_REMOVE); session.serviceDestroyed(); super.onDestroy();
  }
}
