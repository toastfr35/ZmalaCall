// @test A-LLT-027
// @requirements LLR-AND-HISTORY-003, LLR-AND-UPDATE-002
// @environment native-sdk
// @plan On a disposable Android emulator, deliver a signed callback hint with a local authenticated
// configuration server. Inspect ordinary notification text/category/timeout, duplicate/dismissed
// delivery, cancellation, stale snapshots, deadline changes and enrollment isolation. Tap the alert to the permitted
// contact page without dialing. No Google transport or personal enrollment is used.
// Inspect the actual initialized WorkManager configuration for a job range excluding update job 9037.
// Signed background delivery needs a validated network (the production WorkManager constraint);
// report that case skipped if the emulator has no validated network, rather than weakening it.
// @pass Only a valid current incoming request produces a single named reminder, stale or forbidden
// state cannot create one, cancellation removes it and tapping opens the contact without a call.
// WorkManager uses the configured disjoint range, so callback refresh cannot replace the update job.
package org.zmala.phone;

import static org.junit.Assert.*;
import android.app.*;
import android.content.*;
import androidx.test.rule.GrantPermissionRule;
import java.util.*;
import org.json.*;
import org.junit.*;

public class CallbackAlertsTest {
  @Test public void callbackJobsCannotReplaceUpdateChecks() {
    Context c = PhoneFixture.INSTRUMENTATION.getTargetContext();
    androidx.work.Configuration config = androidx.work.WorkManager.getInstance(c).getConfiguration();
    assertTrue(config.getMinJobSchedulerId() > 9037);
    assertTrue(config.getMaxJobSchedulerId() >= config.getMinJobSchedulerId() + 1000);
  }
  @Rule public GrantPermissionRule permission=GrantPermissionRule.grant(android.Manifest.permission.POST_NOTIFICATIONS);
  static final String ID="12345678-0000-0000-0000-000000000000";
  static android.service.notification.StatusBarNotification[] alerts(Context c) {
    return Arrays.stream(c.getSystemService(NotificationManager.class).getActiveNotifications())
        .filter(n->n.getTag()!=null&&n.getTag().startsWith("callback:")).toArray(android.service.notification.StatusBarNotification[]::new);
  }
  @Test public void signedWakeupReconcilesAndOpensTheContactWithoutCalling() throws Exception {
    Context c=PhoneFixture.INSTRUMENTATION.getTargetContext();PhoneFixture.endSession();
    android.net.ConnectivityManager connectivity = c.getSystemService(android.net.ConnectivityManager.class);
    android.net.NetworkCapabilities capabilities = connectivity.getNetworkCapabilities(connectivity.getActiveNetwork());
    Assume.assumeTrue("Background callback delivery needs an Android-validated network",
        capabilities != null && capabilities.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_VALIDATED));
    NotificationManager manager=c.getSystemService(NotificationManager.class);
    manager.cancelAll();c.getSharedPreferences("callback-notices",0).edit().clear().commit();
    manager.deleteNotificationChannel(CallbackAlerts.CHANNEL);
    JSONObject config=PhoneFixture.config(5060).put("callbacks_enabled",true)
        .put("callbacks",new JSONArray().put(new JSONObject().put("id",ID).put("from","term1").put("to","phone1")
            .put("status","pending").put("expires_at",java.time.Instant.ofEpochMilli(System.currentTimeMillis()+600000).toString())));
    try(PhoneFixture.Http http=new PhoneFixture.Http(config)) {
      PushFixture.enroll(c,http.port());Enrollment enrollment=PushAlerts.enrollment(c);
      Map<String,String> message=PushFixture.message(ID,"callback",System.currentTimeMillis()+60000);
      Map<String,String> forged=new HashMap<>(message);forged.put("caller","other");
      PushAlerts.receive(c,forged);assertEquals(0,alerts(c).length);assertEquals(0,http.configurationRequests);
      PushAlerts.receive(c,message);PhoneFixture.waitFor(()->alerts(c).length==1);
      assertTrue(CallSession.peek()==null||CallSession.peek().engine.call==null);
      assertTrue(http.authorized);
      Notification notice=alerts(c)[0].getNotification();
      assertEquals(Notification.CATEGORY_REMINDER,notice.category);
      assertTrue(notice.extras.getCharSequence(Notification.EXTRA_TEXT).toString().contains("Living room"));
      assertNull(notice.fullScreenIntent);assertNotNull(notice.contentIntent);
      assertTrue(notice.getTimeoutAfter()>0&&notice.getTimeoutAfter()<=600000);
      config.getJSONArray("callbacks").getJSONObject(0).put("expires_at",java.time.Instant.ofEpochMilli(System.currentTimeMillis()+1200000).toString());
      CallbackAlerts.synchronize(c,enrollment,config,CallbackAlerts.beginRefresh());
      assertTrue(alerts(c)[0].getNotification().getTimeoutAfter()>600000);
      PushAlerts.receive(c,message);PhoneFixture.waitFor(()->http.configurationRequests>=2);
      assertEquals(1,alerts(c).length);
      manager.cancel("callback:"+ID,2);
      CallbackAlerts.synchronize(c,enrollment,config,CallbackAlerts.beginRefresh());
      assertEquals(0,alerts(c).length); // Dismissal is not permission to repeat the alert.

      c.getSharedPreferences("callback-notices",0).edit().clear().commit();
      long old=CallbackAlerts.beginRefresh(),current=CallbackAlerts.beginRefresh();
      CallbackAlerts.synchronize(c,enrollment,config,old);assertEquals(0,alerts(c).length);
      CallbackAlerts.synchronize(c,enrollment,config,current);assertEquals(1,alerts(c).length);
      Instrumentation.ActivityMonitor monitor=PhoneFixture.INSTRUMENTATION.addMonitor(MainActivity.class.getName(),null,false);
      try {
        alerts(c)[0].getNotification().contentIntent.send();
        MainActivity screen=(MainActivity)monitor.waitForActivityWithTimeout(10000);assertNotNull(screen);
        PhoneFixture.waitFor(()->CallSession.peek()!=null&&CallSession.peek().engine.call==null
            &&PhoneFixture.text(screen.getWindow().getDecorView(),c.getString(R.string.request_callback))!=null);
        PhoneFixture.INSTRUMENTATION.runOnMainSync(()->{
          assertNotNull(PhoneFixture.text(screen.getWindow().getDecorView(),"Living room"));
          assertNotNull(PhoneFixture.text(screen.getWindow().getDecorView(),c.getString(R.string.request_callback)));
          assertNull(CallSession.peek().engine.call);screen.finish();
        });
      } finally {PhoneFixture.INSTRUMENTATION.removeMonitor(monitor);PhoneFixture.endSession();}
      JSONObject pending=config.getJSONArray("callbacks").getJSONObject(0);
      config.put("callbacks",new JSONArray());
      PushAlerts.receive(c,PushFixture.message(ID,"callback",System.currentTimeMillis()+60000));
      PhoneFixture.waitFor(()->alerts(c).length==0);
      PushAlerts.receive(c,PushFixture.message(ID,"callback",System.currentTimeMillis()-1));
      assertEquals(0,alerts(c).length);
      PushFixture.enroll(c,http.port()+1);
      config.put("callbacks",new JSONArray().put(pending));
      CallbackAlerts.synchronize(c,enrollment,config,CallbackAlerts.beginRefresh());assertEquals(0,alerts(c).length);
      Enrollment replacement=PushAlerts.enrollment(c);
      CallbackAlerts.synchronize(c,replacement,config,CallbackAlerts.beginRefresh());assertEquals(1,alerts(c).length);
      CallbackAlerts.revoked(c,enrollment);assertEquals(1,alerts(c).length);
      CallbackAlerts.revoked(c,replacement);assertEquals(0,alerts(c).length);
    } finally {
      androidx.work.WorkManager.getInstance(c).cancelAllWork();manager.cancelAll();
      new java.io.File(c.getNoBackupFilesDir(),"enrollment.json").delete();
      c.getSharedPreferences("callback-notices",0).edit().clear().commit();
    }
  }
}
