package org.zmala.phone;

import android.content.Context;
import android.view.TextureView;
import org.json.JSONObject;
import org.linphone.core.*;

// @llr LLR-AND-CALL-002
// The core is owned by the activity's main thread; no SIP credentials are written to disk.
public final class CallEngine {
  public interface Events {
    void changed(String status);
  }

  private Core core;
  private final Events events;
  private JSONObject config;
  private JSONObject transportConfig;
  private String appliedSettings;
  public Call call;
  public boolean registered;
  private final VideoStartup videoStartup;
  // @llr LLR-AND-HISTORY-002
  private Context context;
  private boolean connected;
  private String outgoingPeer, unansweredPeer;
  String takeUnansweredPeer() { String peer = unansweredPeer; unansweredPeer = null; return peer; }

  public CallEngine(Events events) {
    this.events = events;
    videoStartup = new VideoStartup(android.os.SystemClock::elapsedRealtime, elapsed -> {
      android.util.Log.i("ZmalaMedia", "answer_to_video_ms=" + elapsed);
      events.changed("In a video call");
    });
  }

  public void start(Context context, JSONObject configuration) throws Exception {
    stop();
    this.context = context.getApplicationContext();
    config = configuration;
    Factory.instance().setDebugMode(false, "ZmalaPhone");
    core = Factory.instance().createCore(null, null, context.getApplicationContext());
    core.setUserAgent("ZmalaPhone", context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName);
    core.setAutoIterateEnabled(true);
    core.setDatabaseEnabled(false);
    core.setMaxCalls(1);
    core.setMaxCallLogs(0);
    core.setPushNotificationEnabled(false);
    core.setNativeRingingEnabled(false);
    core.setRing(null);
    core.setRingback(null);
    core.setVideoCaptureEnabled(true);
    core.setVideoDisplayEnabled(true);
    core.setEchoCancellationEnabled(true);
    core.setMicEnabled(true);
    SecureCalls.configure(core, config, context);
    transportConfig = new JSONObject(config.toString());
    appliedSettings = SecureCalls.settings(config);
    core.setRtpBundleEnabled(false);
    core.setAvpfMode(AVPFMode.Enabled);
    core.setRetransmissionOnNackEnabled(true);
    core.setPreferredVideoDefinitionByName("vga");
    core.setPreferredFramerate(15);
    for (PayloadType codec : core.getAudioPayloadTypes())
      codec.enable(
          "opus".equalsIgnoreCase(codec.getMimeType())
              || "PCMU".equalsIgnoreCase(codec.getMimeType())
              || "PCMA".equalsIgnoreCase(codec.getMimeType()));
    for (PayloadType codec : core.getVideoPayloadTypes())
      codec.enable(
          "H264".equalsIgnoreCase(codec.getMimeType())
              || "VP8".equalsIgnoreCase(codec.getMimeType()));
    core.addListener(
        new CoreListenerStub() {
          @Override
          public void onAccountRegistrationStateChanged(
              Core source, Account account, RegistrationState state, String message) {
            if (source != core) return;
            registered = state == RegistrationState.Ok;
            events.changed(
                registered
                    ? "Ready to call"
                    : state == RegistrationState.Failed
                        ? "Cannot connect to the call server"
                        : "Connecting…");
          }

          @Override
          public void onCallStateChanged(
              Core source, Call changed, Call.State state, String message) {
            if (source != core) return;
            if (state == Call.State.IncomingReceived) {
              Address remote = changed.getRemoteAddress();
              CallParams params = changed.getRemoteParams();
              if (call != null
                  || params == null
                  || !Enrollment.allowedIncoming(
                      config,
                      remote.getUsername(),
                      remote.getDomain(),
                      changed.getCallLog().getCallId(),
                      params.getCustomHeader("X-Family-Auth"))) {
                changed.decline(Reason.Declined);
                return;
              }
              // @llr LLR-AND-UPDATE-002
              if (!UpdateGate.INSTANCE.beginCall()) { changed.decline(Reason.Busy); return; }
              // @llr LLR-AND-HISTORY-002
              connected = false; outgoingPeer = null;
              CallNotices.ring(context, changed.getCallLog().getCallId(), remote.getUsername(), System.currentTimeMillis() + 120000);
              call = changed;
            } else if (state == Call.State.OutgoingInit) call = changed;
            if (call != changed) return;
            // @llr LLR-AND-HISTORY-002
            if (state == Call.State.Connected || state == Call.State.StreamsRunning) {
              connected = true;
              CallNotices.answered(context, changed.getCallLog().getCallId(), changed.getRemoteAddress().getUsername());
            }
            if (state == Call.State.End
                || state == Call.State.Error
                || state == Call.State.Released) {
              videoStartup.reset();
              // @llr LLR-AND-HISTORY-002
              if (!connected && outgoingPeer != null) unansweredPeer = outgoingPeer;
              if (outgoingPeer == null) CallNotices.finish(context, changed.getCallLog().getCallId(), !connected);
              outgoingPeer = null;
              call = null;
              // @llr LLR-AND-UPDATE-002
              UpdateGate.INSTANCE.endCall();
              core.setNativeVideoWindowId(null);
              core.setNativePreviewWindowId(null);
              events.changed(state == Call.State.Error ? "Call could not connect" : "Call ended");
            } else {
              videoStartup.state(changed, state);
              events.changed(
                  state == Call.State.IncomingReceived
                      ? "Incoming video call"
                      : state == Call.State.StreamsRunning ? "In a video call" : "Calling…");
            }
          }

          @Override
          public void onCallStatsUpdated(Core source, Call changed, CallStats stats) {
            if (source == core && changed == call) videoStartup.requestFrame(changed);
          }
        });
    core.start();
    // The core starts after Activity.onResume, so the SDK lifecycle observer misses it.
    // This engine exists only while the activity is visible; onStop releases it.
    core.enterForeground();
    JSONObject sip = config.getJSONObject("sip");
    Address identity =
        Factory.instance()
            .createAddress("sip:" + sip.getString("username") + "@" + sip.getString("domain"));
    Address proxy = Factory.instance().createAddress(sip.getString("proxy"));
    if (identity == null || proxy == null)
      throw new IllegalArgumentException("Invalid SIP address.");
    core.addAuthInfo(
        Factory.instance()
            .createAuthInfo(
                sip.getString("username"),
                null,
                sip.getString("password"),
                null,
                null,
                sip.getString("domain")));
    AccountParams parameters = core.createAccountParams();
    parameters.setIdentityAddress(identity);
    parameters.setServerAddress(proxy);
    parameters.setRoutesAddresses(new Address[] {proxy});
    parameters.setRegisterEnabled(true);
    parameters.setExpires(60);
    parameters.setUnregisterAtStopEnabled(true);
    Account account = core.createAccount(parameters);
    core.addAccount(account);
    core.setDefaultAccount(account);
    for (String device : core.getVideoDevicesList())
      if (device.toLowerCase(java.util.Locale.ROOT).contains("front")) {
        core.setVideoDevice(device);
        break;
      }
    speaker(true);
  }

  public void refresh(JSONObject configuration) {
    config = configuration;
  }

  // @llr LLR-AND-CALL-006
  public boolean requiresRestart(JSONObject next) throws Exception {
    return core == null || !SecureCalls.settings(next).equals(appliedSettings);
  }

  // @llr LLR-AND-CALL-006
  private MediaEncryption callEncryption() throws Exception {
    return SecureCalls.validate(transportConfig, System.currentTimeMillis() / 1000) == null
        ? MediaEncryption.None : MediaEncryption.SRTP;
  }

  public void dial(JSONObject contact) throws Exception {
    if (core == null || !registered || call != null || !contact.optBoolean("can_call")) return;
    boolean permitted = false;
    for (int i = 0; i < config.getJSONArray("contacts").length(); i++) {
      JSONObject current = config.getJSONArray("contacts").getJSONObject(i);
      if (current.getString("id").equals(contact.getString("id")) && current.optBoolean("can_call"))
        permitted = true;
    }
    if (!permitted) return;
    core.setMicEnabled(true);
    Address address =
        Factory.instance()
            .createAddress(
                "sip:"
                    + contact.getString("id")
                    + "@"
                    + config.getJSONObject("sip").getString("domain"));
    CallParams params = core.createCallParams(null);
    params.setVideoEnabled(true);
    params.setAudioEnabled(true);
    params.setMediaEncryption(callEncryption());
    params.setRtpBundleEnabled(false);
    // @llr LLR-AND-UPDATE-002
    if (!UpdateGate.INSTANCE.beginCall()) { events.changed("An update is being installed. Try again shortly."); return; }
    // @llr LLR-AND-HISTORY-002
    connected = false; outgoingPeer = contact.optString("id"); unansweredPeer = null;
    try {
      if (core.inviteAddressWithParams(address, params) == null) {
        UpdateGate.INSTANCE.endCall();
        events.changed("Call could not start");
      }
    } catch (RuntimeException error) { UpdateGate.INSTANCE.endCall(); throw error; }
  }

  public void answer() {
    if (call == null || core == null || call.getState() != Call.State.IncomingReceived) return;
    core.setMicEnabled(true);
    CallParams params = core.createCallParams(call);
    params.setVideoEnabled(true);
    params.setAudioEnabled(true);
    try {
      params.setMediaEncryption(callEncryption());
    } catch (Exception expired) {
      call.decline(Reason.NotAcceptable);
      return;
    }
    call.acceptWithParams(params);
  }

  public void hangup() {
    // @llr LLR-AND-HISTORY-002
    if (call != null && call.getState() == Call.State.IncomingReceived)
      CallNotices.finish(context, call.getCallLog().getCallId(), false);
    if (call != null) call.terminate();
  }

  public void mute(boolean value) {
    if (core != null) core.setMicEnabled(!value);
  }

  public void speaker(boolean value) {
    if (core == null) return;
    for (AudioDevice device : core.getAudioDevices()) {
      if (device.getType() == (value ? AudioDevice.Type.Speaker : AudioDevice.Type.Earpiece)) {
        core.setOutputAudioDevice(device);
        break;
      }
    }
  }

  // @llr LLR-AND-CALL-002
  public void flipCamera() {
    if (core == null || call == null) return;
    for (String device : core.getVideoDevicesList()) {
      if (!device.equals(core.getVideoDevice())
          && !device.toLowerCase(java.util.Locale.ROOT).contains("static")) {
        core.setVideoDevice(device);
        // A local camera change must not start another SDP/ICE negotiation.
        call.update(null);
        break;
      }
    }
  }

  public void video(TextureView remote, TextureView preview) {
    if (core != null) {
      core.setNativeVideoWindowId(remote);
      core.setNativePreviewWindowId(preview);
    }
  }

  // @llr LLR-AND-UI-002
  public boolean remoteVideoReady() {
    return videoStartup.ready(call);
  }

  public void rotateVideo(int degrees) {
    if (core != null && core.getDeviceRotation() != degrees) core.setDeviceRotation(degrees);
  }

  public void stop() {
    // @llr LLR-AND-HISTORY-002
    if (call != null && outgoingPeer == null && context != null)
      CallNotices.finish(context, call.getCallLog().getCallId(), !connected);
    videoStartup.reset();
    Core previous = core;
    core = null;
    call = null;
    // @llr LLR-AND-UPDATE-002
    UpdateGate.INSTANCE.endCall();
    registered = false;
    if (previous != null) {
      previous.terminateAllCalls();
      previous.setNativeVideoWindowId(null);
      previous.setNativePreviewWindowId(null);
      previous.stop();
      previous.clearAccounts();
      previous.clearAllAuthInfo();
    }
  }
}
