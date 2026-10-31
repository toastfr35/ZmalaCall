package org.zmala.phone;

import android.graphics.Bitmap;
import android.graphics.ImageDecoder;
import java.io.*;
import java.nio.ByteBuffer;

// @llr LLR-AND-CALL-007
/** Downsample before allocating pixels; ImageDecoder applies the source orientation. */
final class CallPhotoImage {
  static byte[] read(InputStream input) throws Exception {
    if (input == null) throw new IOException("Photo unavailable");
    byte[] bytes;
    try (InputStream in = input; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      byte[] buffer = new byte[8192]; int n;
      while ((n = in.read(buffer)) != -1) {
        if (out.size()+n > 20*1024*1024) throw new IOException("Photo too large");
        out.write(buffer, 0, n);
      }
      bytes = out.toByteArray();
    }
    Bitmap bitmap = ImageDecoder.decodeBitmap(ImageDecoder.createSource(ByteBuffer.wrap(bytes)), (decoder, info, source) -> {
      int w = info.getSize().getWidth(), h = info.getSize().getHeight();
      if (w <= 0 || h <= 0 || (long)w*h > 64000000) throw new IllegalArgumentException("Photo too large");
      double scale = Math.min(1, 1600.0/Math.max(w,h));
      decoder.setTargetSize(Math.max(1,(int)(w*scale)), Math.max(1,(int)(h*scale)));
      decoder.setAllocator(ImageDecoder.ALLOCATOR_SOFTWARE);
    });
    try (ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      if (!bitmap.compress(Bitmap.CompressFormat.JPEG, 85, out) || out.size() > 2097152)
        throw new IOException("Photo too large");
      return out.toByteArray();
    } finally { bitmap.recycle(); }
  }
}
