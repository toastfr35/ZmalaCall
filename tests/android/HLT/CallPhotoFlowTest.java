// @test A-HLT-012
// @requirements HLR-AND-CALL-001
// @environment native-display
// @plan On a disposable emulator answer a signed SIP call, deliver a synthetic picker result, inspect local and remote photos, sender-only renewal, receiver stop/failed-lease expiry, recreate the activity, stop sharing and end the call. Check unchanged native call and audio state and absence of replacement INVITEs.
// @pass Photo sharing survives recreation, renews, clears on Stop/end, preserves call audio/media state and rejects a late result. Physical speech/video quality and the system picker provider are qualified separately.
package org.zmala.phone;

import static org.junit.Assert.*;
import android.Manifest;
import android.content.*;
import android.graphics.*;
import android.net.Uri;
import androidx.test.rule.*;
import java.io.*;
import java.nio.file.Files;
import org.junit.*;

public class CallPhotoFlowTest {
  @Rule public GrantPermissionRule permissions = GrantPermissionRule.grant(Manifest.permission.CAMERA,
      Manifest.permission.RECORD_AUDIO, Manifest.permission.POST_NOTIFICATIONS, "android.permission.ACCESS_LOCAL_NETWORK");
  @Rule public ActivityTestRule<MainActivity> activity = new ActivityTestRule<>(MainActivity.class, false, false);
  @Test public void sharingKeepsNativeCall() throws Exception {
    Assume.assumeTrue("Requires a disposable emulator", android.os.Build.MODEL.contains("sdk_gphone"));
    Context context = PhoneFixture.INSTRUMENTATION.getTargetContext();
    File enrollment = new File(context.getNoBackupFilesDir(), "enrollment.json");
    File photo = new File(context.getCacheDir(), "fixture-photo.png");
    Bitmap bitmap = Bitmap.createBitmap(600, 300, Bitmap.Config.ARGB_8888); bitmap.eraseColor(Color.BLUE);
    try (OutputStream out = new FileOutputStream(photo)) { bitmap.compress(Bitmap.CompressFormat.PNG, 100, out); }
    bitmap.recycle(); PhoneFixture.endSession();
    CallSession session = CallSession.get(context);
    try (PhoneFixture.Sip sip = new PhoneFixture.Sip()) {
      var config = PhoneFixture.config(sip.port()).put("call_photo_sharing", true);
      config.getJSONArray("contacts").getJSONObject(0).put("account_type", "app");
      try (CallPhotoFixture http = new CallPhotoFixture(config)) {
        Files.writeString(enrollment.toPath(), PhoneFixture.qr(http.port(), "app"));
        MainActivity screen = activity.launchActivity(null);
        PhoneFixture.waitFor(() -> sip.authenticated);
        sip.incoming("photo-flow", PhoneFixture.proof("photo-flow"));
        PhoneFixture.waitFor(() -> PhoneFixture.hasText(screen, "Answer video call"));
        PhoneFixture.click(screen, "Answer video call");
        PhoneFixture.waitFor(() -> session.engine.call != null && session.engine.call.getState() == org.linphone.core.Call.State.StreamsRunning);
        var call = session.engine.call;
        boolean audio = call.getCurrentParams().isAudioEnabled(); assertTrue(audio);
        var picker = MainActivity.class.getDeclaredField("photoPickerCall"); picker.setAccessible(true);
        PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
          try { picker.set(screen, session.callId()); } catch (Exception e) { throw new AssertionError(e); }
          screen.onActivityResult(10, android.app.Activity.RESULT_OK, new Intent().setData(Uri.fromFile(photo)));
        });
        PhoneFixture.waitFor(() -> session.photos.image != null);
        assertTrue(http.sharing); assertTrue(http.photo.length > 0);
        assertTrue(PhoneFixture.hasText(screen, "Stop sharing"));
        var view = (android.widget.ImageView) PhoneFixture.description(screen.getWindow().getDecorView(), "Shared photo");
        assertNotNull(view); assertTrue(view.isShown());
        assertEquals(android.widget.ImageView.ScaleType.FIT_CENTER, view.getScaleType());
        assertNotNull(view.getDrawable());
        PhoneFixture.waitFor(() -> http.renewals > 0);
        PhoneFixture.INSTRUMENTATION.runOnMainSync(screen::recreate);
        PhoneFixture.waitFor(() -> session.visible);
        assertSame(call, session.engine.call); assertNotNull(session.photos.image);
        assertEquals(audio, call.getCurrentParams().isAudioEnabled());
        assertNull(sip.invites.poll(300, java.util.concurrent.TimeUnit.MILLISECONDS));
        PhoneFixture.INSTRUMENTATION.runOnMainSync(session.photos::stop);
        PhoneFixture.waitFor(() -> !http.sharing); assertNull(session.photos.image);
        // The other phone now shares; this receiver must neither renew nor delete its share.
        int renewals=http.renewals;
        http.photo=CallPhotoImage.read(new FileInputStream(photo)); http.revision++; http.sharing=true;
        PhoneFixture.waitFor(() -> session.photos.receiving && session.photos.image != null);
        assertFalse(session.photos.active()); assertSame(call,session.engine.call);
        assertTrue(call.getCurrentParams().isAudioEnabled());
        http.sharing=false; http.revision++;
        PhoneFixture.waitFor(() -> !session.photos.receiving && session.photos.image == null);
        assertEquals(renewals,http.renewals);
        // A failed fetch must not extend the last advertised lease.
        http.remaining=1500; http.sharing=true; http.revision++;
        PhoneFixture.waitFor(() -> session.photos.receiving);
        http.failPhotoRequests=true;
        PhoneFixture.waitFor(() -> !session.photos.receiving && session.photos.image == null);
        http.failPhotoRequests=false; http.sharing=false; http.remaining=12000; http.revision++;
        String oldId = session.callId();
        PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> session.photos.choose(Uri.fromFile(photo), oldId));
        PhoneFixture.waitFor(() -> session.photos.image != null);
        PhoneFixture.endSession();
        PhoneFixture.waitFor(() -> session.photos.image == null && !http.sharing);
        PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> session.photos.choose(Uri.fromFile(photo), oldId));
        assertFalse(session.photos.active());
      }
    } finally {
      PhoneFixture.endSession(); activity.finishActivity();
      Files.deleteIfExists(enrollment.toPath()); Files.deleteIfExists(photo.toPath());
    }
  }
}
