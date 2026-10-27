package org.zmala.phone;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import com.google.zxing.*;
import com.google.zxing.common.HybridBinarizer;
import java.io.*;
import java.util.Map;

// @llr LLR-AND-ENROLL-002
/** Decode a bounded local image without saving or uploading its enrollment credentials. */
final class QrImage {
  static String read(InputStream input) throws Exception {
    if (input == null) throw new IOException("Could not open this image.");
    byte[] bytes;
    try (InputStream in = input; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      byte[] buffer = new byte[8192]; int count;
      while ((count = in.read(buffer)) != -1) {
        if (out.size() + count > 20 * 1024 * 1024) throw new IOException("Image is too large.");
        out.write(buffer, 0, count);
      }
      bytes = out.toByteArray();
    }
    BitmapFactory.Options options = new BitmapFactory.Options();
    options.inJustDecodeBounds = true;
    BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
    if (options.outWidth <= 0 || options.outHeight <= 0
        || (long) options.outWidth * options.outHeight > 64000000)
      throw new IOException("Choose a picture containing your setup QR code.");
    options.inSampleSize = 1;
    while (Math.max(options.outWidth, options.outHeight) / options.inSampleSize > 1800) options.inSampleSize *= 2;
    options.inJustDecodeBounds = false;
    Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
    if (bitmap == null) throw new IOException("Could not read this image.");
    try {
      int width = bitmap.getWidth(), height = bitmap.getHeight();
      int[] pixels = new int[width * height];
      bitmap.getPixels(pixels, 0, width, 0, 0, width, height);
      BinaryBitmap qr = new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(width, height, pixels)));
      String text = new MultiFormatReader().decode(qr, Map.of(
          DecodeHintType.POSSIBLE_FORMATS, java.util.List.of(BarcodeFormat.QR_CODE),
          DecodeHintType.TRY_HARDER, true)).getText();
      if (text.length() > 8192) throw new IOException("QR code is too large.");
      return text;
    } finally { bitmap.recycle(); }
  }
}
