// @test A-LLT-028
// @requirements LLR-AND-UI-002
// @environment native-sdk
// @plan Load a generated portrait twice across view generations using a counted fetch double.
// Load forty distinct bitmaps to exceed the decoded-memory budget and require a refetch of the oldest.
// Change enrollment with the same photo path, then retire a view while its fetch is blocked.
// @pass Refresh reuses the decoded bitmap without another fetch; another enrollment fetches anew;
// an obsolete result never updates its view or fills the cache. Closing rejects later work.
package org.zmala.phone;

import static org.junit.Assert.*;
import android.graphics.Bitmap;
import android.widget.ImageView;
import java.io.ByteArrayOutputStream;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.Test;

public class PortraitLoaderTest {
  private void main(Runnable task) { PhoneFixture.INSTRUMENTATION.runOnMainSync(task); }
  private void loaded(ImageView view) throws Exception {
    PhoneFixture.waitFor(() -> {
      boolean[] ready = {false}; main(() -> ready[0] = view.getDrawable() != null); return ready[0];
    });
  }
  @Test public void cacheIsReusedAndEnrollmentIsIsolated() throws Exception {
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    Bitmap.createBitmap(480, 480, Bitmap.Config.ARGB_8888).compress(Bitmap.CompressFormat.PNG, 100, bytes);
    Enrollment first = new Enrollment(PhoneFixture.qr(8080, "app"));
    Enrollment second = new Enrollment(PhoneFixture.qr(8081, "app"));
    AtomicInteger fetches = new AtomicInteger();
    PortraitLoader[] loader = {null}; ImageView[] view = new ImageView[3];
    main(() -> {
      loader[0] = new PortraitLoader((enrollment, path) -> { fetches.incrementAndGet(); return bytes.toByteArray(); });
      for (int i = 0; i < view.length; i++) view[i] = new ImageView(PhoneFixture.INSTRUMENTATION.getTargetContext());
      loader[0].load(view[0], first, "/photos/abc.png", loader[0].begin());
    });
    try {
      loaded(view[0]);
      main(() -> {
        Bitmap bitmap = ((android.graphics.drawable.BitmapDrawable) view[0].getDrawable()).getBitmap();
        assertTrue(bitmap.getWidth() <= 256); assertTrue(bitmap.getHeight() <= 256);
      });
      main(() -> loader[0].load(view[1], first, "/photos/abc.png", loader[0].begin()));
      loaded(view[1]); assertEquals(1, fetches.get());
      main(() -> loader[0].load(view[2], second, "/photos/abc.png", loader[0].begin()));
      loaded(view[2]); assertEquals(2, fetches.get());
    } finally { main(() -> loader[0].close()); }
  }
  @Test public void obsoleteFetchCannotFillCacheOrChangeView() throws Exception {
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    Bitmap.createBitmap(480, 480, Bitmap.Config.ARGB_8888).compress(Bitmap.CompressFormat.PNG, 100, bytes);
    Enrollment enrollment = new Enrollment(PhoneFixture.qr(8080, "app"));
    CountDownLatch started = new CountDownLatch(1), release = new CountDownLatch(1);
    AtomicInteger fetches = new AtomicInteger();
    PortraitLoader[] loader = {null}; ImageView[] view = new ImageView[2];
    main(() -> {
      loader[0] = new PortraitLoader((target, path) -> {
        if (fetches.incrementAndGet() == 1) { started.countDown(); assertTrue(release.await(5, TimeUnit.SECONDS)); }
        return bytes.toByteArray();
      });
      for (int i = 0; i < view.length; i++) view[i] = new ImageView(PhoneFixture.INSTRUMENTATION.getTargetContext());
      loader[0].load(view[0], enrollment, "/photos/abc.png", loader[0].begin());
    });
    try {
      assertTrue(started.await(5, TimeUnit.SECONDS));
      main(() -> loader[0].load(view[1], enrollment, "/photos/abc.png", loader[0].begin()));
      release.countDown(); loaded(view[1]);
      assertEquals(2, fetches.get());
      main(() -> {
        assertNull(view[0].getDrawable()); loader[0].close();
        loader[0].load(view[0], enrollment, "/photos/abc.png", loader[0].begin());
      });
      assertEquals(2, fetches.get());
    } finally { release.countDown(); main(() -> loader[0].close()); }
  }
  @Test public void decodedMemoryBudgetEvictsOlderPortraits() throws Exception {
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    Bitmap.createBitmap(480, 480, Bitmap.Config.ARGB_8888).compress(Bitmap.CompressFormat.PNG, 100, bytes);
    Enrollment enrollment = new Enrollment(PhoneFixture.qr(8080, "app"));
    AtomicInteger fetches = new AtomicInteger();
    PortraitLoader[] loader = {null};
    main(() -> loader[0] = new PortraitLoader((target, path) -> { fetches.incrementAndGet(); return bytes.toByteArray(); }));
    try {
      // Forty 480px bitmaps exceed the budget even after any decoder sampling.
      for (int i = 0; i < 40; i++) {
        String path = "/photos/" + Integer.toHexString(i) + ".png";
        ImageView[] view = {null};
        main(() -> { view[0] = new ImageView(PhoneFixture.INSTRUMENTATION.getTargetContext());
          loader[0].load(view[0], enrollment, path, loader[0].begin()); });
        loaded(view[0]);
      }
      assertEquals(40, fetches.get());
      ImageView[] view = {null};
      main(() -> { view[0] = new ImageView(PhoneFixture.INSTRUMENTATION.getTargetContext());
        loader[0].load(view[0], enrollment, "/photos/0.png", loader[0].begin()); });
      loaded(view[0]); assertEquals(41, fetches.get());
    } finally { main(() -> loader[0].close()); }
  }
}
