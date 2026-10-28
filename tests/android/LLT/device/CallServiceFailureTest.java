// @test A-LLT-025
// @requirements LLR-AND-CALL-002
// @environment native-sdk
// @plan Use an application-context double that rejects foreground service startup. Attempt preparation
// from hidden and visible states with an idle call session, and inspect ownership after denial.
// Repeatedly acquire service wake ownership, then release it; check the same Android lock is reused.
// @pass Hidden preparation never starts a service; denied visible startup fails without retained
// foreground ownership, call, registration or configuration. No actual Android service is started.
package org.zmala.phone;
import static org.junit.Assert.*;
import android.content.*;
import org.junit.Test;
public class CallServiceFailureTest {
  @Test public void deniedForegroundStartupCannotStrandOwnership() {
    PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
      int[] starts = {0};
      Context context = new ContextWrapper(PhoneFixture.INSTRUMENTATION.getTargetContext()) {
        @Override public ComponentName startForegroundService(Intent intent) { starts[0]++; throw new SecurityException("Fixture denial"); }
        @Override public boolean stopService(Intent intent) { return true; }
      };
      try {
        var constructor = CallSession.class.getDeclaredConstructor(Context.class); constructor.setAccessible(true);
        CallSession session = constructor.newInstance(context);
        assertFalse(session.prepare()); assertEquals(0, starts[0]);
        session.visible = true;
        assertFalse(session.prepare()); assertEquals(1, starts[0]);
        assertFalse(session.serviceRequested); assertNull(session.engine.call);
        assertFalse(session.engine.registered); assertNull(session.configuration);
      } catch (ReflectiveOperationException error) { throw new AssertionError(error); }
    });
  }
  @Test public void repeatedStartsReleaseTheOnlyWakeLock() {
    PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
      CallService service = new CallService();
      try {
        android.os.PowerManager power = PhoneFixture.INSTRUMENTATION.getTargetContext().getSystemService(android.os.PowerManager.class);
        var field = CallService.class.getDeclaredField("wake"); field.setAccessible(true);
        service.keepAwake(power);
        android.os.PowerManager.WakeLock first = (android.os.PowerManager.WakeLock) field.get(service);
        assertTrue(first.isHeld());
        service.keepAwake(power); service.keepAwake(power);
        assertSame(first, field.get(service));
        service.releaseWake();
        assertFalse(first.isHeld()); assertNull(field.get(service));
        service.releaseWake();
      } catch (ReflectiveOperationException error) { throw new AssertionError(error); }
      finally { service.releaseWake(); }
    });
  }
}
