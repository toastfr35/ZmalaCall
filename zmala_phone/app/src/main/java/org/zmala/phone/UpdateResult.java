package org.zmala.phone;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

// @llr LLR-AND-UPDATE-002
public final class UpdateResult extends BroadcastReceiver {
  @Override public void onReceive(Context context, Intent intent) {
    AppUpdates.get(context).result(intent);
  }
}
