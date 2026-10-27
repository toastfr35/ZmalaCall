package org.zmala.phone;

import android.app.*;
import android.content.*;
import android.media.*;
import android.net.Uri;
import android.os.*;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.app.Person;
import com.google.firebase.FirebaseApp;
import com.google.firebase.messaging.FirebaseMessaging;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Consumer;
import org.json.*;

// @llr LLR-AND-CALL-004
/** Short-lived call notifications; no background camera, microphone or permanent SIP connection. */
public final class PushAlerts {
  static final String CHANNEL = "incoming_calls", EXTRA = "zmala_push", ANSWER = "zmala_answer";
  private static final ExecutorService NETWORK = Executors.newSingleThreadExecutor();
  private static String registeredKey = "";
  private static long registeredAt;

  static Enrollment enrollment(Context context) {
    try {
      return new Enrollment(
          new String(
              Files.readAllBytes(
                  new File(context.getNoBackupFilesDir(), "enrollment.json").toPath()),
              StandardCharsets.UTF_8));
    } catch (Exception e) {
      return null;
    }
  }

  static boolean allowed(Context context) {
    NotificationManager manager = context.getSystemService(NotificationManager.class);
    NotificationChannel channel = manager.getNotificationChannel(CHANNEL);
    return NotificationManagerCompat.from(context).areNotificationsEnabled()
        && (channel == null || channel.getImportance() >= NotificationManager.IMPORTANCE_DEFAULT);
  }

  // @llr LLR-AND-HISTORY-003
  static boolean anyAllowed(Context context) {
    return allowed(context) || CallbackAlerts.allowed(context);
  }

  static void channel(Context context) {
    NotificationChannel channel =
        new NotificationChannel(CHANNEL, context.getString(R.string.incoming_calls), NotificationManager.IMPORTANCE_HIGH);
    channel.setDescription(context.getString(R.string.notification_channel_help));
    channel.enableVibration(true);
    channel.setSound(
        RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE),
        new AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
            .build());
    context.getSystemService(NotificationManager.class).createNotificationChannel(channel);
  }

  static void remember(Context context, JSONObject configuration) {
    JSONObject names = new JSONObject();
    JSONArray contacts = configuration.optJSONArray("contacts");
    try {
      if (contacts != null)
        for (int i = 0; i < contacts.length(); i++) {
          JSONObject contact = contacts.getJSONObject(i);
          if (contact.optBoolean("can_receive"))
            names.put(contact.getString("id"), contact.getString("name"));
        }
      context.getSharedPreferences("push", 0).edit().putString("names", names.toString()).apply();
    } catch (Exception ignored) {
    }
  }

  static void register(Context context, Enrollment enrollment, Consumer<Boolean> complete) {
    channel(context);
    CallbackAlerts.channel(context);
    if (!anyAllowed(context)) {
      upload(context, enrollment, null, complete);
      return;
    }
    try {
      if (FirebaseApp.initializeApp(context) == null) {
        complete.accept(false);
        return;
      }
      FirebaseMessaging.getInstance()
          .getToken()
          .addOnSuccessListener(token -> upload(context, enrollment, token, complete))
          .addOnFailureListener(error -> complete.accept(false));
    } catch (Exception error) {
      complete.accept(false);
    }
  }

  static void upload(
      Context context, Enrollment enrollment, String token, Consumer<Boolean> complete) {
    String key =
        enrollment.deviceId + ":" + enrollment.server + ":" + (token == null ? "disabled" : token);
    if (key.equals(registeredKey) && System.currentTimeMillis() - registeredAt < 3600000) {
      complete.accept(token != null);
      return;
    }
    NETWORK.execute(
        () -> {
          boolean ready = false;
          try {
            JSONObject reply =
                ServerApi.push(
                    enrollment,
                    "/api/app/push",
                    new JSONObject().put("token", token == null ? JSONObject.NULL : token));
            ready = token != null && reply.optBoolean("push_enabled");
            if (ready || token == null) {
              registeredKey = key;
              registeredAt = System.currentTimeMillis();
            }
          } catch (Exception ignored) {
          }
          boolean result = ready;
          new Handler(Looper.getMainLooper()).post(() -> complete.accept(result));
        });
  }

  static Map<String, String> unpack(Intent intent) {
    Map<String, String> data = new HashMap<>();
    try {
      JSONObject json = new JSONObject(intent.getStringExtra(EXTRA));
      for (String key :
          new String[] {"event", "call_id", "caller", "expires", "device_id", "proof"})
        data.put(key, json.getString(key));
    } catch (Exception ignored) {
    }
    return data;
  }

  static synchronized boolean closed(Context context, String id, boolean close) {
    SharedPreferences prefs = context.getSharedPreferences("push", 0);
    try {
      JSONObject values = new JSONObject(prefs.getString("closed", "{}"));
      long now = System.currentTimeMillis();
      List<String> remove = new ArrayList<>();
      for (Iterator<String> keys = values.keys(); keys.hasNext(); ) {
        String key = keys.next();
        if (values.optLong(key) < now) remove.add(key);
      }
      for (String key : remove) values.remove(key);
      boolean found = values.has(id);
      if (close) {
        if (values.length() >= 32) values = new JSONObject();
        values.put(id, now + 120000);
      }
      prefs.edit().putString("closed", values.toString()).apply();
      return found;
    } catch (Exception error) {
      return true;
    }
  }

  static void dismiss(Context context, String id) {
    if (id == null) return;
    context.getSystemService(NotificationManager.class).cancel(id, 1);
    closed(context, id, true);
  }

  static void receive(Context context, Map<String, String> data) {
    // @llr LLR-AND-HISTORY-003
    if ("callback".equals(data.get("event"))) { CallbackAlerts.receive(context,data); return; }
    Enrollment enrollment = enrollment(context);
    PushMessage message =
        enrollment == null
            ? null
            : PushMessage.verify(enrollment, data, System.currentTimeMillis());
    if (message == null) return;
    if (message.event.equals("cancel")) {
      // @llr LLR-AND-HISTORY-002
      CallNotices.finish(context, message.callId, true);
      dismiss(context, message.callId);
      return;
    }
    if (closed(context, message.callId, false)) return;
    // @llr LLR-AND-UPDATE-002
    if (!AppUpdates.get(context).ring(message.expires)) return;
    // @llr LLR-AND-HISTORY-002
    CallNotices.ring(context, message.callId, message.caller, message.expires);
    if (MainActivity.pushIncoming(data)) return;
    show(context, message, data);
  }

  static void show(Context context, PushMessage message, Map<String, String> data) {
    channel(context);
    if (!allowed(context)) return;
    NotificationManager manager = context.getSystemService(NotificationManager.class);
    for (android.service.notification.StatusBarNotification existing :
        manager.getActiveNotifications()) if (message.callId.equals(existing.getTag())) return;
    String serialized = new JSONObject(data).toString();
    Intent open =
        new Intent(context, MainActivity.class)
            .setData(Uri.parse("zmalaphone:call/" + Uri.encode(message.callId)))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .putExtra(EXTRA, serialized);
    PendingIntent view =
        PendingIntent.getActivity(
            context, 0, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    PendingIntent answer =
        PendingIntent.getActivity(
            context,
            1,
            new Intent(open).putExtra(ANSWER, true),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    Intent decline =
        new Intent(context, DeclineReceiver.class)
            .setData(open.getData())
            .putExtra(EXTRA, serialized);
    PendingIntent reject =
        PendingIntent.getBroadcast(
            context, 2, decline, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    String name = message.caller;
    try {
      name =
          new JSONObject(context.getSharedPreferences("push", 0).getString("names", "{}"))
              .optString(message.caller, message.caller);
    } catch (Exception ignored) {
    }
    NotificationCompat.Builder builder =
        new NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(android.R.drawable.sym_call_incoming)
            .setContentTitle(context.getString(R.string.incoming_video))
            .setContentText(name)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setContentIntent(view)
            .setFullScreenIntent(view, true)
            .setOngoing(true)
            .setTimeoutAfter(Math.max(1, message.expires - System.currentTimeMillis()))
            .setStyle(
                NotificationCompat.CallStyle.forIncomingCall(
                        new Person.Builder().setName(name).setImportant(true).build(),
                        reject,
                        answer)
                    .setIsVideo(true));
    Notification notification = builder.build();
    notification.flags |= Notification.FLAG_INSISTENT;
    manager.notify(message.callId, 1, notification);
  }

  public static final class DeclineReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
      Enrollment enrollment = enrollment(context);
      PushMessage message =
          enrollment == null
              ? null
              : PushMessage.verify(enrollment, unpack(intent), System.currentTimeMillis());
      if (message == null) return;
      // @llr LLR-AND-HISTORY-002
      CallNotices.finish(context, message.callId, false);
      dismiss(context, message.callId);
      PendingResult result = goAsync();
      NETWORK.execute(
          () -> {
            try {
              ServerApi.push(
                  enrollment,
                  "/api/app/call/decline",
                  new JSONObject().put("call_id", message.callId));
            } catch (Exception ignored) {
            } finally {
              result.finish();
            }
          });
    }
  }
}
