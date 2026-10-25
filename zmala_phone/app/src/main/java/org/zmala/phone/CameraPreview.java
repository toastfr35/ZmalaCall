package org.zmala.phone;

import android.content.Context;
import android.os.Looper;
import org.linphone.mediastream.video.capture.CaptureTextureView;

// @llr LLR-AND-UI-002
/** Keep the corner surface itself at the camera's reported, display-oriented ratio. */
final class CameraPreview extends CaptureTextureView {
  CameraPreview(Context context) { super(context); }

  @Override public void setAspectRatio(int width, int height) {
    super.setAspectRatio(width, height);
    // Native capture invokes this off the UI thread, including after a camera switch.
    if (Looper.myLooper() == Looper.getMainLooper()) requestLayout();
    else post(this::requestLayout);
  }
}
