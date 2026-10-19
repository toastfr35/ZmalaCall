package org.zmala.phone;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

// @llr LLR-AND-CALL-004
public final class PushService extends FirebaseMessagingService {
  @Override
  public void onMessageReceived(RemoteMessage message) {
    PushAlerts.receive(this, message.getData());
  }

  @Override
  public void onNewToken(String token) {
    Enrollment enrollment = PushAlerts.enrollment(this);
    if (enrollment != null)
      PushAlerts.upload(this, enrollment, PushAlerts.allowed(this) ? token : null, ready -> {});
  }
}
