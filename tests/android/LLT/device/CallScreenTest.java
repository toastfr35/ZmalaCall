// @test A-LLT-005
// @requirements LLR-AND-UI-002
// @environment native-display
// @plan Attach the real call view, reveal its four icon actions, check callbacks and state labels, wait five seconds for hiding, tap again, and rotate between portrait and landscape. Inspect bottom-right preview placement, one-row geometry and the ringing indicator lifecycle. Supply a widescreen camera size and all four rotations; verify fitted preview aspect ratio, bounds and matrix rotation in portrait and landscape. Repeat portrait-landscape-portrait transitions and assert the first layout's preview dimensions and transformed pixel aspect ratio without a corrective layout or transform. Render five pulse phases; check clear margins and green pixels around the circular perimeter.
// Replace ringing with Connecting video progress, inspect the visible spinner and stopped
// ring pulse, then clear progress and verify unchanged video surfaces and available controls.
// Measure the connecting label at narrow portrait and landscape sizes and reject clipped text.
// Cycle speaker, earpiece and silent output while microphone mute stays selected. Dispatch
// vertical swipes, taps, horizontal drags, cancellation and a second pointer to the video.
// Supply changing live-stream definitions through SDK doubles; bind the real capture view,
// apply the statistics-refresh path and verify nonzero SDK dimensions and fitted camera ratio.
// @pass Controls start hidden, remain in one row, hide after five seconds and reappear on a tap.
// Vertical swipes adjust only listening volume and show feedback; other gestures do not.
// Preview surfaces survive rotation with correct bounds and aspect ratio on the first layout pass.
// Connecting video shows a spinner without the ringing pulse, and clearing it hides progress.
// Every connecting-label glyph fits the measured text bounds in both orientations.
// This display test does not establish physical video orientation or remote media quality.
package org.zmala.phone;

import static org.junit.Assert.*;

import android.content.pm.ActivityInfo;
import android.view.View;
import android.widget.ImageButton;
import androidx.test.rule.ActivityTestRule;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.*;

public class CallScreenTest {
  @Test public void previewReceivesCurrentStreamDimensionsAndAdaptation() {
    PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
      try {
        CallScreen view = new CallScreen(PhoneFixture.INSTRUMENTATION.getTargetContext(), false,
            CallEngine.Output.SPEAKER, new CallScreen.Actions() {
              public void mute(boolean value) {} public CallEngine.Output output(CallEngine.Output value) { return value; }
              public int volume(int steps) { return 50; } public void camera() {} public void end() {}
            });
        int[] pixels = {480, 640};
        org.linphone.core.VideoDefinition definition = (org.linphone.core.VideoDefinition)
            java.lang.reflect.Proxy.newProxyInstance(getClass().getClassLoader(), new Class<?>[]{org.linphone.core.VideoDefinition.class},
            (p, m, a) -> m.getName().equals("getWidth") ? pixels[0] : pixels[1]);
        org.linphone.core.CallParams params = (org.linphone.core.CallParams)
            java.lang.reflect.Proxy.newProxyInstance(getClass().getClassLoader(), new Class<?>[]{org.linphone.core.CallParams.class},
            (p, m, a) -> { assertEquals("getSentVideoDefinition", m.getName()); return definition; });
        org.linphone.core.Call call = (org.linphone.core.Call)
            java.lang.reflect.Proxy.newProxyInstance(getClass().getClassLoader(), new Class<?>[]{org.linphone.core.Call.class},
            (p, m, a) -> { assertEquals("getCurrentParams", m.getName()); return params; });
        org.linphone.core.Core core = (org.linphone.core.Core)
            java.lang.reflect.Proxy.newProxyInstance(getClass().getClassLoader(), new Class<?>[]{org.linphone.core.Core.class},
            (p, m, a) -> { assertTrue(m.getName().equals("setNativeVideoWindowId") || m.getName().equals("setNativePreviewWindowId")); return null; });
        CallEngine engine = new CallEngine(s -> {});
        var field = CallEngine.class.getDeclaredField("core"); field.setAccessible(true); field.set(engine, core);
        engine.call = call;
        assertEquals(0, view.preview.getPreviewVideoSize().getWidth());
        engine.video(view.remote, view.preview);
        for (int[] size : new int[][]{{480,640}, {720,1280}, {1280,720}, {640,480}, {480,640}}) {
          pixels[0] = size[0]; pixels[1] = size[1]; engine.updatePreviewSize();
          view.measure(View.MeasureSpec.makeMeasureSpec(400, View.MeasureSpec.EXACTLY),
              View.MeasureSpec.makeMeasureSpec(800, View.MeasureSpec.EXACTLY));
          assertEquals(size[0], view.preview.getPreviewVideoSize().getWidth());
          assertEquals(size[1], view.preview.getPreviewVideoSize().getHeight());
          assertEquals((float)size[0] / size[1], (float)view.preview.getMeasuredWidth()
              / view.preview.getMeasuredHeight(), .01f);
        }
        pixels[0] = 0; pixels[1] = 0; engine.updatePreviewSize();
        assertEquals(480, view.preview.getPreviewVideoSize().getWidth());
        engine.call = null; engine.updatePreviewSize(); view.dispose();
      } catch (ReflectiveOperationException e) { throw new AssertionError(e); }
    });
  }
  @Test public void volumeGesturesDoNotBecomeTapsOrChangeMute() {
    PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
      int[] volume = {50}, calls = {0};
      CallScreen view = new CallScreen(PhoneFixture.INSTRUMENTATION.getTargetContext(), true,
          CallEngine.Output.MUTED, new CallScreen.Actions() {
            public void mute(boolean value) { fail("A swipe changed microphone mute"); }
            public CallEngine.Output output(CallEngine.Output value) { fail("A swipe changed routing"); return value; }
            public int volume(int steps) { calls[0]++; volume[0] += steps; return volume[0]; }
            public void camera() { fail(); } public void end() { fail(); }
          });
      float density = view.getResources().getDisplayMetrics().density;
      java.util.function.BiConsumer<Integer, float[]> touch = (action, point) -> {
        android.view.MotionEvent event = android.view.MotionEvent.obtain(0, 10, action,
            point[0] * density, point[1] * density, 0);
        view.remote.dispatchTouchEvent(event); event.recycle();
      };
      touch.accept(0, new float[]{100, 200}); touch.accept(2, new float[]{100, 136});
      touch.accept(1, new float[]{100, 136});
      assertEquals(52, volume[0]); assertEquals(View.INVISIBLE, view.controls.getVisibility());
      assertNotNull(PhoneFixture.text(view, "Sound muted · 52%"));
      touch.accept(0, new float[]{100, 100}); touch.accept(2, new float[]{100, 164});
      touch.accept(1, new float[]{100, 164}); assertEquals(50, volume[0]);
      int prior = calls[0];
      touch.accept(0, new float[]{100, 100}); touch.accept(2, new float[]{200, 104}); touch.accept(1, new float[]{200, 104});
      touch.accept(0, new float[]{100, 200}); touch.accept(3, new float[]{100, 200});
      touch.accept(2, new float[]{100, 100}); touch.accept(1, new float[]{100, 100});
      touch.accept(0, new float[]{100, 200}); touch.accept(5, new float[]{100, 200});
      touch.accept(2, new float[]{100, 100}); touch.accept(1, new float[]{100, 100});
      assertEquals(prior, calls[0]); assertEquals(View.INVISIBLE, view.controls.getVisibility());
      touch.accept(0, new float[]{100, 100}); touch.accept(1, new float[]{100, 100});
      assertEquals(View.VISIBLE, view.controls.getVisibility());
      view.dispose();
    });
  }
  @Test public void connectingLabelFitsBesideNarrowSpinner() {
    org.linphone.core.Factory.instance();
    PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
      CallScreen view = new CallScreen(PhoneFixture.INSTRUMENTATION.getTargetContext(), false, CallEngine.Output.SPEAKER,
          new CallScreen.Actions() {
            public void mute(boolean value) {} public CallEngine.Output output(CallEngine.Output value) { return value; }
            public int volume(int steps) { return 50; }
            public void camera() {} public void end() {}
          });
      float density = view.getResources().getDisplayMetrics().density;
      for (boolean landscape : new boolean[]{false, true}) {
        view.progress("Ringing…");
        view.progress("Connecting video…");
        int width = Math.round((landscape ? 640 : 320) * density);
        int height = Math.round((landscape ? 320 : 640) * density);
        view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
        view.layout(0, 0, width, height);
        android.widget.TextView label = (android.widget.TextView) PhoneFixture.text(view, "Connecting video…");
        android.text.Layout text = label.getLayout();
        assertNotNull(text);
        int available = label.getWidth() - label.getCompoundPaddingLeft() - label.getCompoundPaddingRight();
        assertTrue("All wrapped lines must fit vertically", text.getHeight()
            <= label.getHeight() - label.getCompoundPaddingTop() - label.getCompoundPaddingBottom());
        assertEquals(label.length(), text.getLineEnd(text.getLineCount() - 1));
        for (int line = 0; line < text.getLineCount(); line++) {
          assertEquals(0, text.getEllipsisCount(line));
          assertTrue("Full line must fit instead of clipping to spinner width", text.getLineWidth(line) <= available + 1);
        }
      }
      view.dispose();
    });
  }

  @Test
  public void previewUsesCurrentBoundsOnFirstRotationLayout() {
    org.linphone.core.Factory.instance();
    PhoneFixture.INSTRUMENTATION.runOnMainSync(
        () -> {
          CallScreen call =
              new CallScreen(
                  PhoneFixture.INSTRUMENTATION.getTargetContext(),
                  false,
                  CallEngine.Output.SPEAKER,
                  new CallScreen.Actions() {
                    public void mute(boolean value) {}

                    public CallEngine.Output output(CallEngine.Output value) { return value; }
            public int volume(int steps) { return 50; }

                    public void camera() {}

                    public void end() {}
                  });
          float density = call.getResources().getDisplayMetrics().density;
          for (boolean landscape : new boolean[] {false, true, false, true, false}) {
            int width = landscape ? 800 : 400;
            int height = landscape ? 400 : 800;
            call.preview.setAspectRatio(landscape ? 1280 : 720, landscape ? 720 : 1280);
            call.preview.setRotation(landscape ? 0 : 90);
            call.measure(
                View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
            call.layout(0, 0, width, height);
            assertEquals(
                "Preview width must use this layout, not the previous orientation",
                Math.round((landscape ? 128 : 72) * density),
                call.preview.getWidth());
            assertEquals(Math.round((landscape ? 72 : 128) * density), call.preview.getHeight());
            android.graphics.RectF pixels =
                new android.graphics.RectF(0, 0, call.preview.getWidth(), call.preview.getHeight());
            call.preview.getTransform(new android.graphics.Matrix()).mapRect(pixels);
            assertEquals(
                "Rendered pixels preserve the current camera ratio without another layout",
                landscape ? 1280f / 720 : 720f / 1280,
                pixels.width() / pixels.height(),
                .01f);
          }
          call.dispose();
        });
  }

  @Rule
  public ActivityTestRule<MainActivity> activity =
      new ActivityTestRule<>(MainActivity.class, false, false);

  @Test
  public void immersiveControlsAndRotation() throws Exception {
    org.linphone.core.Factory.instance();
    MainActivity screen = activity.launchActivity(null);
    CallScreen[] holder = new CallScreen[1];
    int[] actions = new int[4];
    PhoneFixture.INSTRUMENTATION.runOnMainSync(
        () -> {
          screen.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);
          holder[0] =
              new CallScreen(
                  screen,
                  false,
                  CallEngine.Output.SPEAKER,
                  new CallScreen.Actions() {
                    public void mute(boolean value) {
                      assertTrue(value);
                      actions[0]++;
                    }

                    public CallEngine.Output output(CallEngine.Output value) {
                      actions[1]++; return value;
                    }
                    public int volume(int steps) { return 50; }

                    public void camera() {
                      actions[2]++;
                    }

                    public void end() {
                      actions[3]++;
                    }
                  });
          screen.setContentView(holder[0]);
        });
    CallScreen call = holder[0];
    PhoneFixture.waitFor(() -> call.getHeight() > call.getWidth());
    PhoneFixture.INSTRUMENTATION.runOnMainSync(
        () -> {
          assertEquals(View.INVISIBLE, call.controls.getVisibility());
          assertNull(PhoneFixture.text(call, "ZmalaPhone"));
          call.remote.performClick();
        });
    PhoneFixture.INSTRUMENTATION.waitForIdleSync();
    PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> checkLayout(call));
    checkPreviewTransform(call);
    checkPulse(call);
    PhoneFixture.click(screen, "Mute microphone");
    assertTrue(PhoneFixture.hasDescription(screen, "Unmute microphone"));
    PhoneFixture.click(screen, "Loudspeaker. Switch to earpiece");
    assertTrue(PhoneFixture.hasDescription(screen, "Earpiece. Mute call sound"));
    PhoneFixture.click(screen, "Earpiece. Mute call sound");
    assertTrue(PhoneFixture.hasDescription(screen, "Call sound muted. Switch to loudspeaker"));
    assertTrue(PhoneFixture.hasDescription(screen, "Unmute microphone"));
    PhoneFixture.click(screen, "Call sound muted. Switch to loudspeaker");
    assertTrue(PhoneFixture.hasDescription(screen, "Loudspeaker. Switch to earpiece"));
    PhoneFixture.click(screen, "Switch camera");
    assertArrayEquals(new int[] {1, 3, 1, 0}, actions);
    PhoneFixture.snapshot("call-controls-portrait");
    // Check before and after the five-second idle deadline, without depending on exact frame
    // timing.
    PhoneFixture.INSTRUMENTATION.runOnMainSync(call::showControls);
    Thread.sleep(4000);
    PhoneFixture.INSTRUMENTATION.runOnMainSync(
        () -> assertEquals(View.VISIBLE, call.controls.getVisibility()));
    PhoneFixture.waitFor(
        () -> {
          AtomicBoolean hidden = new AtomicBoolean();
          PhoneFixture.INSTRUMENTATION.runOnMainSync(
              () -> hidden.set(call.controls.getVisibility() == View.INVISIBLE));
          return hidden.get();
        });
    PhoneFixture.snapshot("call-controls-hidden");
    PhoneFixture.INSTRUMENTATION.runOnMainSync(
        () -> {
          assertTrue(
              call.preview.getBottom()
                  > call.getHeight()
                      - call.getPaddingBottom()
                      - 20 * screen.getResources().getDisplayMetrics().density);
          call.preview.performClick();
          assertEquals(View.VISIBLE, call.controls.getVisibility());
          screen.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);
        });
    PhoneFixture.waitFor(() -> call.getWidth() > call.getHeight());
    PhoneFixture.INSTRUMENTATION.runOnMainSync(
        () -> {
          checkLayout(call);
          call.progress("Ringing…");
        });
    PhoneFixture.snapshot("call-ringing-landscape");
    checkPulse(call);
    assertTrue(PhoneFixture.hasText(screen, "Ringing…"));
    checkPreviewTransform(call);
    PhoneFixture.INSTRUMENTATION.runOnMainSync(
        () -> {
          try {
            java.lang.reflect.Field field = CallScreen.class.getDeclaredField("pulse");
            field.setAccessible(true);
            android.animation.ObjectAnimator pulse =
                (android.animation.ObjectAnimator) field.get(call);
            assertTrue(pulse.isStarted());
            call.progress("Connecting video…");
            assertFalse(pulse.isStarted());
            assertTrue(PhoneFixture.text(call, "Connecting video…").isShown());
            assertTrue(PhoneFixture.description(call, "Connecting video").isShown());
            call.progress(null);
            assertFalse(pulse.isStarted());
          } catch (ReflectiveOperationException error) {
            throw new AssertionError(error);
          }
          assertFalse(PhoneFixture.text(call, "Connecting video…").isShown());
          call.remote.performClick();
        });
    PhoneFixture.click(screen, "End call");
    assertArrayEquals(new int[] {1, 3, 1, 1}, actions);
    PhoneFixture.INSTRUMENTATION.runOnMainSync(
        () -> screen.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT));
  }

  private void checkLayout(CallScreen call) {
    assertEquals(4, call.controls.getChildCount());
    assertEquals(View.VISIBLE, call.controls.getVisibility());
    int[] prior = null;
    for (int i = 0; i < 4; i++) {
      View control = call.controls.getChildAt(i);
      assertTrue(control instanceof ImageButton);
      assertNotNull(control.getContentDescription());
      assertEquals(control.getWidth(), control.getHeight());
      assertTrue(control.getHeight() >= 60 * call.getResources().getDisplayMetrics().density);
      int[] position = new int[2];
      control.getLocationOnScreen(position);
      if (prior != null) {
        assertEquals(prior[1], position[1]);
        assertTrue(position[0] > prior[0]);
      }
      prior = position;
    }
    assertTrue(call.controls.getRight() <= call.getWidth());
    assertTrue(call.controls.getLeft() >= 0);
    assertTrue(call.preview.getRight() <= call.getWidth());
    assertTrue(call.preview.getLeft() > call.getWidth() / 2);
    assertTrue(call.preview.getBottom() <= call.controls.getTop());
  }

  private void checkPreviewTransform(CallScreen call) throws Exception {
    for (int degrees : new int[] {0, 90, 180, 270}) {
      PhoneFixture.INSTRUMENTATION.runOnMainSync(
          () -> {
            call.preview.setAspectRatio(degrees % 180 == 90 ? 360 : 640,
                degrees % 180 == 90 ? 640 : 360);
            call.preview.setRotation(degrees);
          });
      PhoneFixture.INSTRUMENTATION.waitForIdleSync();
      PhoneFixture.INSTRUMENTATION.runOnMainSync(
          () -> {
            call.preview.rotateToMatchDisplayOrientation();
            android.graphics.RectF fitted = call.preview.getPreviewRectF();
            assertNotNull(fitted);
            assertEquals(
                "Captured aspect ratio must survive the preview slot",
                degrees % 180 == 90 ? 360f / 640f : 640f / 360f,
                fitted.width() / fitted.height(),
                .01f);
            assertTrue(fitted.width() <= call.preview.getWidth() + 1);
            assertTrue(fitted.height() <= call.preview.getHeight() + 1);
            float[] matrix = new float[9];
            call.preview.getTransform(new android.graphics.Matrix()).getValues(matrix);
            // TextureView first maps the actual 640x360 buffer into its view. The final
            // transform must give horizontal and vertical camera pixels equal lengths.
            float rawX = call.preview.getWidth() / 640f, rawY = call.preview.getHeight() / 360f;
            double pixelX = Math.hypot(matrix[0] * rawX, matrix[3] * rawX);
            double pixelY = Math.hypot(matrix[1] * rawY, matrix[4] * rawY);
            assertEquals("A camera circle must stay circular", pixelX, pixelY, .015);
            if (degrees == 90 || degrees == 270) {
              assertEquals(0, matrix[android.graphics.Matrix.MSCALE_X], .001f);
              assertTrue(Math.abs(matrix[android.graphics.Matrix.MSKEW_X]) > .1f);
            } else {
              assertEquals(0, matrix[android.graphics.Matrix.MSKEW_X], .001f);
              assertTrue(
                  degrees == 0
                      ? matrix[android.graphics.Matrix.MSCALE_X] > 0
                      : matrix[android.graphics.Matrix.MSCALE_X] < 0);
            }
          });
    }
  }

  private void checkPulse(CallScreen call) {
    PhoneFixture.INSTRUMENTATION.runOnMainSync(
        () -> {
          try {
            call.progress("Ringing…");
            java.lang.reflect.Field field = CallScreen.class.getDeclaredField("pulse");
            field.setAccessible(true);
            android.animation.ObjectAnimator pulse =
                (android.animation.ObjectAnimator) field.get(call);
            pulse.pause();
            View icon = (View) pulse.getTarget();
            // The progress area may have just become visible; give the drawable its fixed surface.
            int size = Math.round(108 * call.getResources().getDisplayMetrics().density);
            icon.layout(0, 0, size, size);
            for (long time : new long[] {0, 300, 600, 900, 1200}) {
              pulse.setCurrentPlayTime(time);
              android.graphics.Bitmap bitmap =
                  android.graphics.Bitmap.createBitmap(
                      size, size, android.graphics.Bitmap.Config.ARGB_8888);
              icon.draw(new android.graphics.Canvas(bitmap));
              int first = size, last = 0;
              for (int x = 0; x < size; x++) {
                if (android.graphics.Color.alpha(bitmap.getPixel(x, size / 2)) > 50) {
                  first = Math.min(first, x);
                  last = Math.max(last, x);
                }
              }
              assertTrue(
                  "Pulse needs clear space at every phase",
                  first >= size / 10 && last < size - size / 10);
              float radius = (last - first) / 2f;
              for (int angle = 0; angle < 360; angle += 15) {
                double radians = Math.toRadians(angle);
                int x = Math.round(size / 2f + .93f * radius * (float) Math.cos(radians));
                int y = Math.round(size / 2f + .93f * radius * (float) Math.sin(radians));
                int color = bitmap.getPixel(x, y);
                assertTrue(
                    "Full green perimeter at phase " + time + " angle " + angle,
                    android.graphics.Color.alpha(color) > 50
                        && android.graphics.Color.green(color) > android.graphics.Color.red(color));
              }
              bitmap.recycle();
            }
            pulse.resume();
          } catch (ReflectiveOperationException error) {
            throw new AssertionError(error);
          }
        });
  }
}
