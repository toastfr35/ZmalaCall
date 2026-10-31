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
  boolean busy, receiving;
  private String receivingCall;
  private long receiveEpoch, receiveRevision = -1, receiveDeadline;
  private final Runnable poll = this::poll;
  private final Runnable expireReceive = this::expireReceivedPhoto;
  private void expireReceivedPhoto() {
    if (receiving && android.os.SystemClock.elapsedRealtime() >= receiveDeadline) {
      receiving=false; image=null; receiveRevision=-1; changed.run();
    }
  }
  Bitmap image;
  int error;
  private final Runnable renew = this::renew;

  CallPhotoShare(Context context, Supplier<String> currentCall, Runnable changed) {
    this.context=context; this.currentCall=currentCall; this.changed=changed;
  }
  boolean active() { return owner != null || busy; }
  private boolean current(long ticket, String call) {
    return gate.accepts(ticket, call, currentCall.get());
  }
  void choose(Uri uri, String call) {
    if (call == null || !call.equals(currentCall.get())) return;
    if (receiving) return;
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
  void reconcile() {
    String call = currentCall.get();
    if (owner != null && !owner.equals(call)) stop();
    if (!java.util.Objects.equals(call, receivingCall)) {
      receivingCall = call; receiveEpoch++; receiveRevision = -1;
      if (receiving) { receiving=false; image=null; changed.run(); }
      main.removeCallbacks(poll);
      if (call != null) main.post(poll);
    }
  }
  private void poll() {
    String call=receivingCall; long ticket=receiveEpoch;
    if (call == null) return;
    if (active()) { main.postDelayed(poll,1000); return; }
    long started=android.os.SystemClock.elapsedRealtime(), previous=receiveRevision;
    network.execute(() -> {
      Bitmap photo=null; long version=-1, deadline=0; boolean valid=false, sharing=false;
      try {
        Enrollment enrollment=PushAlerts.enrollment(context);
        org.json.JSONObject status=CallPhotoHttp.request(enrollment,call,"GET",0,null);
        version=status.getLong("revision"); sharing=status.optBoolean("sharing");
        deadline=started+Math.min(12000,Math.max(0,status.optLong("remaining_ms")));
        if (sharing && version != previous) {
          byte[] bytes=CallPhotoHttp.exchange(enrollment,call,"GET",version,null,true);
          if (bytes.length<2 || (bytes[0]&255)!=255 || (bytes[1]&255)!=216) throw new java.io.IOException("Invalid shared photo");
          BitmapFactory.Options bounds=new BitmapFactory.Options(); bounds.inJustDecodeBounds=true;
          BitmapFactory.decodeByteArray(bytes,0,bytes.length,bounds);
          if (bounds.outWidth<1 || bounds.outHeight<1 || bounds.outWidth>1600 || bounds.outHeight>1600)
            throw new java.io.IOException("Invalid shared photo");
          photo=BitmapFactory.decodeByteArray(bytes,0,bytes.length);
          if (photo == null) throw new java.io.IOException("Invalid shared photo");
        }
        valid=true;
      } catch (Exception ignored) { }
      Bitmap result=photo; long revision=version, expires=deadline;
      boolean ok=valid, visible=sharing;
      main.post(() -> {
        if (ticket != receiveEpoch || !call.equals(currentCall.get()) || active()) {
          if (result != null) result.recycle();
          if (ticket == receiveEpoch && call.equals(receivingCall)) main.postDelayed(poll,1000);
          return;
        }
        if (ok) {
          receiveDeadline=expires;
          if (visible) { if (result != null) image=result; receiving=image!=null; receiveRevision=receiving ? revision : -1; }
          else { receiving=false; image=null; receiveRevision=-1; }
        }
        if (android.os.SystemClock.elapsedRealtime() >= receiveDeadline) {
          receiving=false; image=null; receiveRevision=-1;
        }
        main.removeCallbacks(expireReceive);
        if (receiving) main.postDelayed(expireReceive, Math.max(0,receiveDeadline-android.os.SystemClock.elapsedRealtime()));
        changed.run(); main.postDelayed(poll,1000);
      });
    });
  }
  void stop() {
    String previous=owner; owner=null; receiving=false; receivingCall=null; receiveEpoch++; receiveRevision=-1; main.removeCallbacks(poll); gate.clear(); busy=false; image=null; error=0;
    main.removeCallbacks(renew); main.removeCallbacks(expireReceive); changed.run();
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
