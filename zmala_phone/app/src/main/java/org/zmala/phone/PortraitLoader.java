package org.zmala.phone;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Handler;
import android.os.Looper;
import android.util.LruCache;
import android.widget.ImageView;

// @llr LLR-AND-UI-002
/** Activity-owned static portraits: bounded decoded memory, no private disk cache.
 * Hash-named photos are immutable; enrollment changes and disposal clear ownership. */
final class PortraitLoader implements AutoCloseable {
  interface Fetch { byte[] read(Enrollment enrollment, String path) throws Exception; }
  private final PortraitQueue queue = new PortraitQueue();
  private final Handler main = new Handler(Looper.getMainLooper());
  private final Fetch fetch;
  private final LruCache<String, Bitmap> cache = new LruCache<>(8 * 1024 * 1024) {
    @Override protected int sizeOf(String key, Bitmap bitmap) { return bitmap.getAllocationByteCount(); }
  };
  private String identity = "";
  PortraitLoader() { this(ServerApi::photo); }
  PortraitLoader(Fetch fetch) { this.fetch = fetch; }

  long begin() { return queue.begin(); }

  /** Called on the main thread; network and decoding never block contact controls. */
  void load(ImageView view, Enrollment enrollment, String path, long ticket) {
    if (enrollment == null || path.isEmpty() || !queue.current(ticket)) return;
    String owner = enrollment.serialized();
    if (!owner.equals(identity)) { identity = owner; cache.evictAll(); }
    queue.execute(ticket, () -> {
      try {
        Bitmap bitmap = cache.get(path);
        if (bitmap == null) {
          byte[] bytes = fetch.read(enrollment, path);
          BitmapFactory.Options options = new BitmapFactory.Options();
          options.inJustDecodeBounds = true;
          BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
          // BitmapFactory samples in powers of two. Round up so 480px input
          // becomes 240px instead of retaining a full-size bitmap for every card.
          options.inSampleSize = 1;
          while (Math.max(options.outWidth, options.outHeight) / options.inSampleSize > 256)
            options.inSampleSize *= 2;
          options.inJustDecodeBounds = false;
          bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
        }
        Bitmap result = bitmap;
        main.post(() -> {
          // Late downloads must not repopulate a different enrollment's cache.
          if (queue.current(ticket) && owner.equals(identity) && result != null) {
            cache.put(path, result);
            view.setImageBitmap(result);
          }
        });
      } catch (Exception ignored) {
        // Failed portraits retain the placeholder and can be retried on the next view.
      }
    });
  }

  @Override public void close() { queue.close(); cache.evictAll(); identity = ""; }
}
