/* The desktop ANGLE library uses prefixed exports. This bridge preserves
 * EGL's ABI and exposes a small render diagnostic for the terminal self-test.
 * It reads five pixels from the app's own framebuffer, never the desktop. */
#include <windows.h>

typedef unsigned int (*Swap)(void *, void *);
typedef void (*GetInteger)(unsigned int, int *);
typedef void (*ReadPixels)(int, int, int, int, unsigned int, unsigned int, void *);
typedef void *(*GetProc)(const char *);
static volatile LONG frames = 0, coloured_frames = 0;
unsigned int family_swap(void *display, void *surface);

void *family_get_proc(const char *name) {
    const char expected[] = "eglSwapBuffers";
    int equal = 1;
    for (int i = 0; i < sizeof(expected); ++i) {
        if (name[i] != expected[i]) { equal = 0; break; }
    }
    if (equal) return (void *)family_swap;
    GetProc resolve = (GetProc)GetProcAddress(GetModuleHandleA("av_libglesv2.dll"), "EGL_GetProcAddress");
    return resolve(name);
}

__declspec(dllexport) long family_renderer_frames(void) { return frames; }
__declspec(dllexport) long family_renderer_coloured_frames(void) { return coloured_frames; }

unsigned int family_swap(void *display, void *surface) {
    HMODULE angle = GetModuleHandleA("av_libglesv2.dll");
    Swap swap = (Swap)GetProcAddress(angle, "EGL_SwapBuffers");
    if (frames < 20 || frames % 60 == 0) {
        GetInteger get_integer = (GetInteger)GetProcAddress(angle, "GL_GetIntegerv");
        ReadPixels read_pixels = (ReadPixels)GetProcAddress(angle, "GL_ReadPixels");
        int viewport[4] = {0}, minimum[3] = {255,255,255}, maximum[3] = {0};
        get_integer(0x0BA2, viewport); /* GL_VIEWPORT */
        for (int i = 1; i <= 5; ++i) {
            unsigned char pixel[4] = {0};
            read_pixels(viewport[2] * i / 6, viewport[3] / 2, 1, 1,
                        0x1908, 0x1401, pixel); /* RGBA, UNSIGNED_BYTE */
            for (int j = 0; j < 3; ++j) {
                if (pixel[j] < minimum[j]) minimum[j] = pixel[j];
                if (pixel[j] > maximum[j]) maximum[j] = pixel[j];
            }
        }
        if (maximum[0] - minimum[0] > 30 || maximum[1] - minimum[1] > 30 || maximum[2] - minimum[2] > 30)
            InterlockedIncrement(&coloured_frames);
    }
    unsigned int result = swap(display, surface);
    if (result) InterlockedIncrement(&frames);
    return result;
}
