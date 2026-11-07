# Zmala Phone

Android application, package `org.zmala.phone`. Build with the pinned Gradle wrapper.

| Responsibility | Source |
| --- | --- |
| App owners | `app/src/main/java/org/zmala/phone/`: `MainActivity`, `CallSession`, `CallEngine` |
| Network boundary | `Enrollment`, `ServerApi`, `HttpPolicy` and secure/update policies |
| UI and resources | Contact/call screens, Android resources and manifest |
| Native adapter | `app/src/main/cpp/` and `../build_tools/android/build-turn.py` |

JVM tests and device scenarios live in `../tests/android/`, not under the Gradle app tree. `make test-android-device` requires an explicitly selected test device. Release signing inputs belong only in the release workflow.

Read the [implementation guide](../docs/android.md) and
[development setup](../docs/development.md). Product requirements are in
[`requirements/android/`](../requirements/android/); unit and system plans are in
[`tests/android/`](../tests/android/).

Run from the repository root after installing the development dependencies:

```sh
make phone test-android
make requirements
```
