package org.zmala.phone;

import android.app.job.JobParameters;
import android.app.job.JobService;

// @llr LLR-AND-UPDATE-002
/** Background work only checks metadata; APK work requires an idle visible app. */
public final class UpdateJob extends JobService {
  @Override public boolean onStartJob(JobParameters params) {
    AppUpdates.get(this).check(false, () -> jobFinished(params, false));
    return true;
  }
  @Override public boolean onStopJob(JobParameters params) { return false; }
}
