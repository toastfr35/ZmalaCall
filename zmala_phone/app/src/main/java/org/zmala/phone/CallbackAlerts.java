package org.zmala.phone;

import android.app.*;
import android.content.*;
import android.net.Uri;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import androidx.work.*;
import org.json.JSONObject;

// @llr LLR-AND-HISTORY-003
/** A signed push is only a wakeup hint; current authenticated callback state decides. */
final class CallbackAlerts {
  static final String CHANNEL = "callback_requests", PEER = "zmala_callback_peer";
  private static final String PREFIX = "callback:";
  private static long revision;

  static synchronized long beginRefresh() { return ++revision; }

  static void channel(Context context) {
    NotificationChannel channel = new NotificationChannel(CHANNEL,
        context.getString(R.string.callback_notifications), NotificationManager.IMPORTANCE_DEFAULT);
    channel.setDescription(context.getString(R.string.callback_notifications_help));
    context.getSystemService(NotificationManager.class).createNotificationChannel(channel);
  }

  static boolean allowed(Context context) {
    NotificationChannel channel = context.getSystemService(NotificationManager.class).getNotificationChannel(CHANNEL);
    return NotificationManagerCompat.from(context).areNotificationsEnabled()
        && (channel == null || channel.getImportance() >= NotificationManager.IMPORTANCE_DEFAULT);
  }

  static String identity(Enrollment enrollment) {
    try {
      byte[] digest = MessageDigest.getInstance("SHA-256").digest(
          (enrollment.server + ":" + enrollment.deviceId + ":" + enrollment.token).getBytes(StandardCharsets.UTF_8));
      StringBuilder value = new StringBuilder();
      for (byte b : digest) value.append(String.format(java.util.Locale.ROOT,"%02x",b & 255));
      return value.toString();
    } catch (Exception error) { throw new IllegalStateException(error); }
  }

  static synchronized void revoked(Context context, Enrollment enrollment) {
    Enrollment current = PushAlerts.enrollment(context);
    if (current == null || !identity(current).equals(identity(enrollment))) return;
    revision++;
    NotificationManager manager = context.getSystemService(NotificationManager.class);
    for (android.service.notification.StatusBarNotification item : manager.getActiveNotifications())
      if (item.getTag() != null && item.getTag().startsWith(PREFIX)) manager.cancel(item.getTag(),2);
    context.getSharedPreferences("callback-notices",0).edit().clear().apply();
  }

  static void receive(Context context, Map<String,String> data) {
    Enrollment enrollment = PushAlerts.enrollment(context);
    PushMessage message = enrollment == null ? null : PushMessage.verify(enrollment,data,System.currentTimeMillis());
    if (message == null || !"callback".equals(message.event)) return;
    // FCM's callback lifetime is too short for network work on an unowned thread.
    // Expedited WorkManager work retains the process, with a regular-job fallback.
    beginRefresh();
    OneTimeWorkRequest work = new OneTimeWorkRequest.Builder(CallbackWorker.class)
        .setInputData(new Data.Builder().putString("message",new JSONObject(data).toString()).build())
        .setConstraints(new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
        .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
        .setBackoffCriteria(BackoffPolicy.LINEAR,10,java.util.concurrent.TimeUnit.SECONDS).build();
    WorkManager.getInstance(context).enqueueUniqueWork("callback-refresh:"+identity(enrollment),ExistingWorkPolicy.REPLACE,work);
  }

  static synchronized void synchronize(Context context, Enrollment enrollment, JSONObject config, long ticket) {
    Enrollment current = PushAlerts.enrollment(context);
    if (ticket != revision || current == null || !identity(current).equals(identity(enrollment))) return;
    NotificationManager manager = context.getSystemService(NotificationManager.class);
    SharedPreferences prefs = context.getSharedPreferences("callback-notices",0);
    String identity = identity(enrollment);
    if (!identity.equals(prefs.getString("identity",""))) {
      for (android.service.notification.StatusBarNotification item : manager.getActiveNotifications())
        if (item.getTag() != null && item.getTag().startsWith(PREFIX)) manager.cancel(item.getTag(),2);
      prefs.edit().clear().putString("identity",identity).apply();
    }
    CallbackBook book = new CallbackBook(prefs.getString("book","{}"));
    long now = System.currentTimeMillis();
    CallbackBook.Plan plan = book.reconcile(config,now);
    for (String id : plan.removed()) manager.cancel(PREFIX+id,2);
    channel(context);
    if (allowed(context)) {
      Map<String,Notification> existing = new java.util.HashMap<>();
      for (android.service.notification.StatusBarNotification item : manager.getActiveNotifications())
        if (item.getTag() != null) existing.put(item.getTag(),item.getNotification());
      for (CallbackBook.Entry entry : plan.retained()) {
        Notification notice = existing.get(PREFIX+entry.id());
        String body = context.getString(R.string.callback_notification_body,entry.name());
        if (notice != null && (notice.extras.getLong("callback_deadline") != entry.expires()
            || !body.contentEquals(notice.extras.getCharSequence(Notification.EXTRA_TEXT,""))))
          show(context,entry,now,notice.when);
      }
      for (CallbackBook.Entry entry : plan.fresh()) if (show(context,entry,now,now)) book.posted(entry);
    }
    prefs.edit().putString("book",book.toString()).apply();
  }

  private static boolean show(Context context, CallbackBook.Entry entry, long now, long when) {
      Intent open = new Intent(context,MainActivity.class)
          .setData(Uri.parse("zmalaphone:callback/"+entry.id()))
          .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
          .putExtra(PEER,entry.peer());
      PendingIntent view = PendingIntent.getActivity(context,0,open,
          PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
      Notification notice = new NotificationCompat.Builder(context,CHANNEL)
          .setSmallIcon(R.drawable.ic_call_notification).setContentTitle(context.getString(R.string.please_call_back))
          .setContentText(context.getString(R.string.callback_notification_body,entry.name()))
          .setCategory(NotificationCompat.CATEGORY_REMINDER).setContentIntent(view)
          .setWhen(when).addExtras(deadline(entry.expires()))
          .setAutoCancel(true).setOnlyAlertOnce(true).setTimeoutAfter(entry.expires()-now)
          .setVisibility(NotificationCompat.VISIBILITY_PRIVATE).build();
      try { context.getSystemService(NotificationManager.class).notify(PREFIX+entry.id(),2,notice); return true; }
      catch (SecurityException ignored) { return false; /* Permission may have changed since allowed(). */ }
  }
  private static android.os.Bundle deadline(long expires) {
    android.os.Bundle value = new android.os.Bundle();value.putLong("callback_deadline",expires);return value;
  }
}
