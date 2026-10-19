// @test A-LLT-011
// @requirements LLR-AND-CALL-006
// @environment native-sdk
// @plan Load the packaged native correction and a test-only JNI helper using the real pinned SDK. Feed padded ChannelData and a coalesced STUN frame at every one of 3804 chunk sizes, including incomplete headers and padding; compare every output byte and length. Call the original SDK parser directly with four-byte reads as a negative control. Assert the corrected reader invocation counter increases. Inject short writes, alternating WANT_READ/WANT_WRITE, a stalled socket, peer closure and poll failure; assert exact output bytes, unchanged retry buffer/length and the three-second deadline.
// @pass All corrected frame boundaries and bytes match, the original parser reproduces the framing defect, and the correction processes the input on the device ABI. Write retries preserve every byte and buffer identity; error/timeout paths fail within the bound.
package org.zmala.phone;

import static org.junit.Assert.*;

import org.junit.Test;

public class TurnParserTest {
  private static native String verifyFrames();

  @Test
  public void fragmentedTlsFrames() {
    System.loadLibrary("turn_test");
    long before = TurnTransport.readCount();
    assertEquals("3804 chunk sizes passed; original defect reproduced", verifyFrames());
    assertTrue(TurnTransport.readCount() > before);
  }
}
