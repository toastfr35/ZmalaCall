// @test A-LLT-029
// @requirements LLR-AND-CALL-007
// @environment portable
// @plan Deliver upload/renewal results after stop, a replacement photo, and a new call. Compare unchanged-call completion with late generations, including reusing the same call ID.
// @pass Only the live share generation and exact current call can accept results; cancellation cannot resurrect an old photo.
package org.zmala.phone;
import org.junit.Test;
import static org.junit.Assert.*;
public class PhotoShareEpochTest {
  @Test public void onlyCurrentShareCanComplete() {
    PhotoShareEpoch gate=new PhotoShareEpoch();
    long a=gate.begin("call"); assertTrue(gate.accepts(a,"call","call"));
    assertFalse(gate.accepts(a,"call","next")); assertFalse(gate.accepts(a,"call",null));
    gate.clear(); assertFalse(gate.accepts(a,"call","call"));
    long b=gate.begin("call"); assertTrue(gate.accepts(b,"call","call"));
    assertFalse(gate.accepts(a,"call","call"));
    gate.begin("next"); assertFalse(gate.accepts(b,"call","next"));
  }
}
