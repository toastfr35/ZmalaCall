package org.zmala.phone;

import android.content.Context;
import androidx.concurrent.futures.CallbackToFutureAdapter;
import androidx.core.app.NotificationCompat;
import androidx.work.*;
import com.google.common.util.concurrent.ListenableFuture;
import java.util.*;
import org.json.JSONObject;

// @llr LLR-AND-HISTORY-003
/** Short authenticated refresh; never starts SIP, microphone or camera. */
public final class CallbackWorker extends Worker {
  public CallbackWorker(Context context, WorkerParameters parameters) { super(context,parameters); }

  @Override public Result doWork() {
    Context context = getApplicationContext();
    Enrollment target = PushAlerts.enrollment(context);
    try {
      JSONObject json = new JSONObject(getInputData().getString("message"));
      Map<String,String> data = new HashMap<>();
      for (Iterator<String> keys = json.keys(); keys.hasNext();) {
        String key = keys.next(); data.put(key,json.getString(key));
      }
      Enrollment enrollment = target;
      PushMessage message = enrollment == null ? null : PushMessage.verify(enrollment,data,System.currentTimeMillis());
      if (message == null || !"callback".equals(message.event)) return Result.success();
      long ticket = CallbackAlerts.beginRefresh();
      JSONObject config = ServerApi.configuration(enrollment);
      if (!isStopped()) CallbackAlerts.synchronize(context,enrollment,config,ticket);
      return Result.success();
    } catch (ServerApi.AccessRevoked revoked) {
      if (target != null) CallbackAlerts.revoked(context,target);
      return Result.success();
    } catch (java.io.IOException temporary) {
      return getRunAttemptCount() < 2 ? Result.retry() : Result.success();
    } catch (Exception rejected) { return Result.success(); }
  }

  // Android 9–11 use a short foreground worker for expedited work. Android 12+
  // uses an expedited JobScheduler job and needs no progress notification.
  @Override public ListenableFuture<ForegroundInfo> getForegroundInfoAsync() {
    return CallbackToFutureAdapter.getFuture(completer -> {
      Context context = getApplicationContext(); CallbackAlerts.channel(context);
      completer.set(new ForegroundInfo(211,new NotificationCompat.Builder(context,CallbackAlerts.CHANNEL)
          .setSmallIcon(R.drawable.ic_call_notification).setContentTitle(context.getString(R.string.checking_callbacks))
          .setSilent(true).setOngoing(true).build()));
      return "callback-refresh";
    });
  }
}
