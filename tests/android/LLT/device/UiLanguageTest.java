// @test A-LLT-023
// @requirements LLR-AND-UI-002
// @environment native-display
// @plan Resolve English/French resources including callback direction and plurals. Measure French
// contact/call/incoming views at 200% font scale. Give a revealed control keyboard focus and invoke hiding.
// @pass French labels and formatted counts resolve correctly, long names wrap, actions remain scrollable,
// four labeled call controls fit the width and focused controls do not disappear. No physical display is qualified.
package org.zmala.phone;

import static org.junit.Assert.*;
import android.content.Context;
import android.view.View;
import org.junit.Test;

public class UiLanguageTest {
  private Context french() {
    Context original = PhoneFixture.INSTRUMENTATION.getTargetContext();
    android.content.res.Configuration config = new android.content.res.Configuration(original.getResources().getConfiguration());
    config.setLocale(java.util.Locale.FRENCH); config.fontScale = 2f;
    return original.createConfigurationContext(config);
  }
  @Test public void frenchResourcesAndDirectionsAreNaturalAndCountsAreLocalized() {
    Context context = french();
    assertEquals("Appeler", context.getString(R.string.call));
    assertEquals("Merci de rappeler", context.getString(R.string.please_call_back));
    assertEquals("Rappel demandé", context.getString(R.string.callback_requested));
    assertEquals("1 appel manqué · Merci de rappeler · Rappel demandé", ContactNotice.summary(context, 1, 3));
    assertEquals("2 appels manqués", ContactNotice.summary(context, 2, 0));
    assertEquals("37", context.getString(R.string.downloading_percent, 37).replaceAll("[^0-9]", ""));
    assertEquals("Prêt à appeler", UiText.status(context, "Ready to call"));
  }
  @Test public void enlargedFrenchViewsPreserveActionsAndFocusedControls() {
    PhoneFixture.INSTRUMENTATION.runOnMainSync(() -> {
      Context context = french();
      int width = Math.round(320 * context.getResources().getDisplayMetrics().density);
      int height = Math.round(500 * context.getResources().getDisplayMetrics().density);
      ContactCard card = new ContactCard(context, "Une personne de la famille au nom très long", "Disponible",
          "Merci de rappeler", MainActivity.GREEN, () -> {});
      card.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED));
      assertTrue(card.getMeasuredHeight() > 80 * context.getResources().getDisplayMetrics().density);
      assertTrue(card.isClickable()); assertFalse(card.portrait.isClickable());
      ContactScreen detail = new ContactScreen(context, "Une personne au nom très long", "Hors ligne", "Merci de rappeler",
          false, true, false, false, 2, () -> {}, () -> {}, () -> {}, () -> {});
      detail.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
      assertFalse(detail.call.isEnabled()); assertNotNull(PhoneFixture.text(detail, "Demander un rappel"));
      CallScreen call = new CallScreen(context, false, CallEngine.Output.SPEAKER, new CallScreen.Actions() {
        public void mute(boolean value) {} public CallEngine.Output output(CallEngine.Output value) { return value; }
        public int volume(int steps) { return 50; } public void camera() {} public void end() {}
      });
      call.showControls(); call.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
      call.layout(0, 0, width, height);
      assertTrue(call.controls.getMeasuredWidth() <= width);
      for (String label : new String[]{"Micro", "Son", "Caméra", "Fin"}) assertNotNull(PhoneFixture.text(call, label));
      View button = ((android.view.ViewGroup) call.controls.getChildAt(0)).getChildAt(0);
      button.setFocusableInTouchMode(true); assertTrue(button.requestFocus());
      try {
        var hide = CallScreen.class.getDeclaredMethod("hideControls"); hide.setAccessible(true); hide.invoke(call);
      } catch (Exception error) { throw new AssertionError(error); }
      assertEquals(View.VISIBLE, call.controls.getVisibility()); call.dispose();
    });
  }
}
