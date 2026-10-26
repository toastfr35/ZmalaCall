// @test A-LLT-022
// @requirements LLR-AND-CALL-004, LLR-AND-UI-002
// @environment portable
// @plan Combine server capability, notification access, registration progress and upload state.
// @pass Disabled server/notifications take precedence over a cached successful registration;
// preparing, failed/unavailable and ready states remain distinct.
package org.zmala.phone;
import static org.junit.Assert.*;
import org.junit.Test;
public class AlertStatusTest {
  @Test public void readinessAlwaysReflectsCurrentPermissionAndServerSupport() {
    assertEquals(AlertStatus.SERVER_OFF, AlertStatus.of(false, true, false, true));
    assertEquals(AlertStatus.NOTIFICATIONS_OFF, AlertStatus.of(true, false, false, true));
    assertEquals(AlertStatus.PREPARING, AlertStatus.of(true, true, true, false));
    assertEquals(AlertStatus.UNAVAILABLE, AlertStatus.of(true, true, false, false));
    assertEquals(AlertStatus.READY, AlertStatus.of(true, true, false, true));
  }
}
