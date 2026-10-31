package org.zmala.phone;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Handler;
import java.util.concurrent.Executors;
import java.util.function.Supplier;

// @llr LLR-AND-CALL-007
/** Session-owned sharing survives Activity recreation; epochs discard late picker/upload work. */
final class CallPhotoShare {
  private final Context context;
  private final Supplier<String> currentCall;
  private final Runnable changed;
  private final Handler main = new Handler(android.os.Looper.getMainLooper());
  private final java.util.concurrent.ExecutorService network = Executors.newSingleThreadExecutor();
  private String owner;
  private final PhotoShareEpoch gate = new PhotoShareEpoch();
  private long epoch, revision;
  boolean busy;
  Bitmap image;
  int error;
  private final Runnable renew = this::renew;

  CallPhotoShare(Context context, Supplier<String> currentCall, Runnable changed) {
    this.context=context; this.currentCall=currentCall; this.changed=changed;
  }
  boolean active() { return busy || image != null; }
  private boolean current(long ticket, String call) {
    return gate.accepts(ticket, call, currentCall.get());
  }
  void choose(Uri uri, String call) {
    if (call == null || !call.equals(currentCall.get())) return;
    stop(); owner=call; busy=true; error=0; long ticket=epoch=gate.begin(call); changed.run();
    network.execute(() -> {
      try {
        Enrollment enrollment=PushAlerts.enrollment(context);
        byte[] bytes=CallPhotoImage.read(context.getContentResolver().openInputStream(uri));
        org.json.JSONObject result=CallPhotoHttp.request(enrollment, call, "PUT", 0, bytes);
        Bitmap photo=BitmapFactory.decodeByteArray(bytes,0,bytes.length);
        main.post(() -> {
          if (!current(ticket,call)) { if (photo != null) photo.recycle(); return; }
          busy=false; image=photo; revision=result.optLong("revision");
          changed.run(); main.postDelayed(renew,3000);
        });
      } catch (Exception failure) {
        main.post(() -> { if (current(ticket,call)) { stop(); error=R.string.photo_share_failed; changed.run(); } });
      }
    });
  }
  void reconcile() { if (owner != null && !owner.equals(currentCall.get())) stop(); }
  void stop() {
    String previous=owner; owner=null; gate.clear(); busy=false; image=null; error=0;
    main.removeCallbacks(renew); changed.run();
    if (previous != null) network.execute(() -> {
      try { CallPhotoHttp.request(PushAlerts.enrollment(context),previous,"DELETE",0,null); }
      catch (Exception ignored) { /* The sender lease expires without further renewal. */ }
    });
  }
  private void renew() {
    if (image == null || owner == null) return;
    String call=owner; long ticket=epoch, version=revision;
    network.execute(() -> {
      boolean alive=false;
      try {
        org.json.JSONObject status=CallPhotoHttp.request(PushAlerts.enrollment(context),call,"POST",version,null);
        alive=status.optBoolean("sharing") && status.optLong("revision")==version;
      } catch (Exception ignored) { }
      boolean accepted=alive;
      main.post(() -> {
        if (!current(ticket,call)) return;
        if (accepted) main.postDelayed(renew,3000);
        else { stop(); error=R.string.photo_share_failed; changed.run(); }
      });
    });
  }
}
