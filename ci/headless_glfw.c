/*
 * headless_glfw.c - minimal GLFW surface backed by OSMesa, for machines without a display.
 *
 * Minecraft reaches GL through LWJGL's GLFW bindings. On a headless runner glfwCreateWindow
 * fails, so the client never has a context and renderer class initialisers abort. This library
 * implements the subset of GLFW that Minecraft touches, keeps a single fake window, and creates
 * an OSMesa context for it so GL calls land in an offscreen RGBA buffer.
 *
 * Build (macOS):
 *   clang -dynamiclib -O2 -o libglfw.dylib headless_glfw.c
 * Run with:
 *   -Dorg.lwjgl.glfw.libname=/path/libglfw.dylib
 *   OSMESA_LIBRARY=$(brew --prefix mesa)/lib/libOSMesa.dylib
 */
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define TRUE_ 1
#define FALSE_ 0

typedef void (*GLFWglproc)(void);
typedef void (*GLFWerrorfun)(int, const char *);
typedef void (*GLFWwindowposfun)(void *, int, int);
typedef void (*GLFWwindowsizefun)(void *, int, int);
typedef void (*GLFWwindowclosefun)(void *);
typedef void (*GLFWwindowrefreshfun)(void *);
typedef void (*GLFWwindowfocusfun)(void *, int);
typedef void (*GLFWwindowiconifyfun)(void *, int);
typedef void (*GLFWwindowmaximizefun)(void *, int);
typedef void (*GLFWframebuffersizefun)(void *, int, int);
typedef void (*GLFWwindowcontentscalefun)(void *, float, float);
typedef void (*GLFWkeyfun)(void *, int, int, int, int);
typedef void (*GLFWcharfun)(void *, unsigned int);
typedef void (*GLFWcharmodsfun)(void *, unsigned int, int);
typedef void (*GLFWmousebuttonfun)(void *, int, int, int);
typedef void (*GLFWcursorposfun)(void *, double, double);
typedef void (*GLFWcursorenterfun)(void *, int);
typedef void (*GLFWscrollfun)(void *, double, double);
typedef void (*GLFWdropfun)(void *, int, const char **);
typedef void (*GLFWmonitorfun)(void *, int);
typedef void (*GLFWjoystickfun)(int, int);

typedef struct {
    int width;
    int height;
    int redBits, greenBits, blueBits, refreshRate;
} GLFWvidmode;

typedef struct {
    int width, height;
    int shouldClose;
    int visible;
    int focused;
    int iconified;
    double cursorX, cursorY;
    void *osmesa;
    unsigned char *pixels;
} Window;

static Window window;
static GLFWvidmode videoMode = {1280, 720, 8, 8, 8, 60};
static double started = 0.0;
static int ready = 0;

typedef void *(*create_ctx_fn)(int, int, int, int, void *);
typedef int (*make_current_fn)(void *, void *, int, int, int);
typedef void *(*get_proc_fn)(const char *);
static create_ctx_fn osmesaCreate = NULL;
static make_current_fn osmesaMakeCurrent = NULL;
static get_proc_fn osmesaGetProc = NULL;

static double clock_now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double) ts.tv_sec + (double) ts.tv_nsec / 1e9;
}

static void load_osmesa(void) {
    if (osmesaCreate) {
        return;
    }
    const char *path = getenv("OSMESA_LIBRARY");
    if (!path) {
        path = "libOSMesa.dylib";
    }
    void *handle = dlopen(path, RTLD_NOW | RTLD_GLOBAL);
    if (!handle) {
        fprintf(stderr, "[glfw-lite] no OSMesa at %s (%s)\n", path, dlerror());
        return;
    }
    osmesaCreate = (create_ctx_fn) dlsym(handle, "OSMesaCreateContextExt");
    osmesaMakeCurrent = (make_current_fn) dlsym(handle, "OSMesaMakeCurrent");
    osmesaGetProc = (get_proc_fn) dlsym(handle, "OSMesaGetProcAddress");
    fprintf(stderr, "[glfw-lite] OSMesa from %s\n", path);
}

/* ---- lifecycle ---- */
int glfwInit(void) {
    if (ready) {
        return TRUE_;
    }
    load_osmesa();
    started = clock_now();
    ready = 1;
    fprintf(stderr, "[glfw-lite] init\n");
    return TRUE_;
}

void glfwTerminate(void) { ready = 0; }
int glfwGetError(const char **description) {
    if (description) {
        *description = NULL;
    }
    return 0;
}
void glfwSetErrorCallback(GLFWerrorfun cb) { (void) cb; }
void glfwInitHint(int hint, int value) { (void) hint; (void) value; }
void glfwWindowHint(int hint, int value) { (void) hint; (void) value; }
void glfwWindowHintString(int hint, const char *value) { (void) hint; (void) value; }
void glfwDefaultWindowHints(void) {}
const char *glfwGetVersionString(void) { return "3.4.0 headless-lite"; }
void glfwGetVersion(int *major, int *minor, int *rev) {
    if (major) *major = 3;
    if (minor) *minor = 4;
    if (rev) *rev = 0;
}
int glfwGetPlatform(void) { return 0x00060005; }
int glfwPlatformSupported(int platform) { (void) platform; return TRUE_; }

/* ---- window ---- */
void *glfwCreateWindow(int width, int height, const char *title, void *monitor, void *share) {
    (void) title; (void) monitor; (void) share;
    if (window.osmesa) {
        return &window;
    }
    window.width = width > 0 ? width : 1280;
    window.height = height > 0 ? height : 720;
    window.visible = TRUE_;
    window.focused = TRUE_;
    window.pixels = (unsigned char *) calloc((size_t) window.width * (size_t) window.height * 4u, 1);
    if (osmesaCreate && osmesaMakeCurrent) {
        /* OSMESA_RGBA = 0x1908, GL_UNSIGNED_BYTE = 0x1401 */
        window.osmesa = osmesaCreate(0x1908, 24, 8, 0, NULL);
        if (window.osmesa) {
            int current = osmesaMakeCurrent(window.osmesa, window.pixels, 0x1401, window.width, window.height);
            fprintf(stderr, "[glfw-lite] window %dx%d context=%p current=%d\n",
                    window.width, window.height, window.osmesa, current);
        } else {
            fprintf(stderr, "[glfw-lite] OSMesa context creation failed\n");
        }
    }
    return &window;
}
void glfwDestroyWindow(void *w) { (void) w; }
int glfwWindowShouldClose(void *w) { (void) w; return window.shouldClose; }
void glfwSetWindowShouldClose(void *w, int value) { (void) w; window.shouldClose = value; }
void glfwShowWindow(void *w) { (void) w; window.visible = TRUE_; }
void glfwHideWindow(void *w) { (void) w; window.visible = FALSE_; }
void glfwFocusWindow(void *w) { (void) w; window.focused = TRUE_; }
void glfwRequestWindowAttention(void *w) { (void) w; }
void glfwMaximizeWindow(void *w) { (void) w; }
void glfwRestoreWindow(void *w) { (void) w; }
void glfwIconifyWindow(void *w) { (void) w; }
void glfwSetWindowTitle(void *w, const char *title) { (void) w; (void) title; }
void glfwSetWindowIcon(void *w, int count, const void *images) { (void) w; (void) count; (void) images; }
void glfwSetWindowPos(void *w, int x, int y) { (void) w; (void) x; (void) y; }
void glfwGetWindowPos(void *w, int *x, int *y) { (void) w; if (x) *x = 0; if (y) *y = 0; }
void glfwGetWindowSize(void *w, int *width, int *height) {
    (void) w;
    if (width) *width = window.width;
    if (height) *height = window.height;
}
void glfwSetWindowSize(void *w, int width, int height) {
    (void) w;
    window.width = width;
    window.height = height;
}
void glfwSetWindowSizeLimits(void *w, int minw, int minh, int maxw, int maxh) {
    (void) w; (void) minw; (void) minh; (void) maxw; (void) maxh;
}
void glfwGetFramebufferSize(void *w, int *width, int *height) {
    (void) w;
    if (width) *width = window.width;
    if (height) *height = window.height;
}
void glfwGetWindowContentScale(void *w, float *xscale, float *yscale) {
    (void) w;
    if (xscale) *xscale = 1.0f;
    if (yscale) *yscale = 1.0f;
}
float glfwGetWindowOpacity(void *w) { (void) w; return 1.0f; }
void glfwSetWindowOpacity(void *w, float opacity) { (void) w; (void) opacity; }
void *glfwGetWindowMonitor(void *w) { (void) w; return NULL; }
void glfwSetWindowMonitor(void *w, void *monitor, int x, int y, int width, int height, int refresh) {
    (void) w; (void) monitor; (void) x; (void) y; (void) width; (void) height; (void) refresh;
}
int glfwGetWindowAttrib(void *w, int attrib) { (void) w; (void) attrib; return TRUE_; }
void glfwSetWindowAttrib(void *w, int attrib, int value) { (void) w; (void) attrib; (void) value; }
void glfwSetWindowUserPointer(void *w, void *pointer) { (void) w; (void) pointer; }
void *glfwGetWindowUserPointer(void *w) { (void) w; return NULL; }

/* ---- monitors ---- */
void **glfwGetMonitors(int *count) {
    static void *monitors[1];
    monitors[0] = (void *) &videoMode;
    if (count) *count = 1;
    return monitors;
}
void *glfwGetPrimaryMonitor(void) { return (void *) &videoMode; }
void glfwGetMonitorPos(void *monitor, int *x, int *y) { (void) monitor; if (x) *x = 0; if (y) *y = 0; }
void glfwGetMonitorWorkarea(void *monitor, int *x, int *y, int *width, int *height) {
    (void) monitor;
    if (x) *x = 0;
    if (y) *y = 0;
    if (width) *width = videoMode.width;
    if (height) *height = videoMode.height;
}
void glfwGetMonitorPhysicalSize(void *monitor, int *widthMM, int *heightMM) {
    (void) monitor;
    if (widthMM) *widthMM = 300;
    if (heightMM) *heightMM = 200;
}
void glfwGetMonitorContentScale(void *monitor, float *xscale, float *yscale) {
    (void) monitor;
    if (xscale) *xscale = 1.0f;
    if (yscale) *yscale = 1.0f;
}
const char *glfwGetMonitorName(void *monitor) { (void) monitor; return "headless"; }
void glfwSetMonitorUserPointer(void *monitor, void *pointer) { (void) monitor; (void) pointer; }
void *glfwGetMonitorUserPointer(void *monitor) { (void) monitor; return NULL; }
void glfwSetMonitorCallback(GLFWmonitorfun cb) { (void) cb; }
const GLFWvidmode *glfwGetVideoModes(void *monitor, int *count) { (void) monitor; if (count) *count = 1; return &videoMode; }
const GLFWvidmode *glfwGetVideoMode(void *monitor) { (void) monitor; return &videoMode; }
void glfwSetGamma(void *monitor, float gamma) { (void) monitor; (void) gamma; }

/* ---- input ---- */
void glfwSetInputMode(void *w, int mode, int value) { (void) w; (void) mode; (void) value; }
int glfwGetInputMode(void *w, int mode) { (void) w; (void) mode; return 0; }
int glfwRawMouseMotionSupported(void) { return FALSE_; }
const char *glfwGetKeyName(int key, int scancode) { (void) key; (void) scancode; return NULL; }
int glfwGetKeyScancode(int key) { (void) key; return 0; }
int glfwGetKey(void *w, int key) { (void) w; (void) key; return 0; }
int glfwGetMouseButton(void *w, int button) { (void) w; (void) button; return 0; }
void glfwGetCursorPos(void *w, double *x, double *y) {
    (void) w;
    if (x) *x = window.cursorX;
    if (y) *y = window.cursorY;
}
void glfwSetCursorPos(void *w, double x, double y) { (void) w; window.cursorX = x; window.cursorY = y; }
void *glfwCreateCursor(const void *image, int hotx, int hoty) { (void) image; (void) hotx; (void) hoty; return NULL; }
void *glfwCreateStandardCursor(int shape) { (void) shape; return NULL; }
void glfwDestroyCursor(void *cursor) { (void) cursor; }
void glfwSetCursor(void *w, void *cursor) { (void) w; (void) cursor; }
const char *glfwGetClipboardString(void *w) { (void) w; return ""; }
void glfwSetClipboardString(void *w, const char *string) { (void) w; (void) string; }
int glfwJoystickPresent(int jid) { (void) jid; return FALSE_; }
const float *glfwGetJoystickAxes(int jid, int *count) { (void) jid; if (count) *count = 0; return NULL; }
const unsigned char *glfwGetJoystickButtons(int jid, int *count) { (void) jid; if (count) *count = 0; return NULL; }
const char *glfwGetJoystickName(int jid) { (void) jid; return NULL; }
int glfwJoystickIsGamepad(int jid) { (void) jid; return FALSE_; }
void glfwSetJoystickCallback(GLFWjoystickfun cb) { (void) cb; }
int glfwUpdateGamepadMappings(const char *mappings) { (void) mappings; return FALSE_; }

/* ---- callbacks (all unused headless, still exported) ---- */
void glfwSetWindowPosCallback(void *w, GLFWwindowposfun cb) { (void) w; (void) cb; }
void glfwSetWindowSizeCallback(void *w, GLFWwindowsizefun cb) { (void) w; (void) cb; }
void glfwSetWindowCloseCallback(void *w, GLFWwindowclosefun cb) { (void) w; (void) cb; }
void glfwSetWindowRefreshCallback(void *w, GLFWwindowrefreshfun cb) { (void) w; (void) cb; }
void glfwSetWindowFocusCallback(void *w, GLFWwindowfocusfun cb) { (void) w; (void) cb; }
void glfwSetWindowIconifyCallback(void *w, GLFWwindowiconifyfun cb) { (void) w; (void) cb; }
void glfwSetWindowMaximizeCallback(void *w, GLFWwindowmaximizefun cb) { (void) w; (void) cb; }
void glfwSetFramebufferSizeCallback(void *w, GLFWframebuffersizefun cb) { (void) w; (void) cb; }
void glfwSetWindowContentScaleCallback(void *w, GLFWwindowcontentscalefun cb) { (void) w; (void) cb; }
void glfwSetKeyCallback(void *w, GLFWkeyfun cb) { (void) w; (void) cb; }
void glfwSetCharCallback(void *w, GLFWcharfun cb) { (void) w; (void) cb; }
void glfwSetCharModsCallback(void *w, GLFWcharmodsfun cb) { (void) w; (void) cb; }
void glfwSetMouseButtonCallback(void *w, GLFWmousebuttonfun cb) { (void) w; (void) cb; }
void glfwSetCursorPosCallback(void *w, GLFWcursorposfun cb) { (void) w; (void) cb; }
void glfwSetCursorEnterCallback(void *w, GLFWcursorenterfun cb) { (void) w; (void) cb; }
void glfwSetScrollCallback(void *w, GLFWscrollfun cb) { (void) w; (void) cb; }
void glfwSetDropCallback(void *w, GLFWdropfun cb) { (void) w; (void) cb; }

/* ---- events and timing ---- */
void glfwPollEvents(void) {}
void glfwWaitEvents(void) {}
void glfwWaitEventsTimeout(double timeout) { (void) timeout; }
void glfwPostEmptyEvent(void) {}
double glfwGetTime(void) { return clock_now() - started; }
void glfwSetTime(double time) { started = clock_now() - time; }
uint64_t glfwGetTimerValue(void) { return (uint64_t) (clock_now() * 1000.0); }
uint64_t glfwGetTimerFrequency(void) { return 1000u; }

/* ---- context and GL ---- */
void glfwMakeContextCurrent(void *w) {
    (void) w;
    if (window.osmesa && osmesaMakeCurrent) {
        osmesaMakeCurrent(window.osmesa, window.pixels, 0x1401, window.width, window.height);
    }
}
void *glfwGetCurrentContext(void) { return window.osmesa ? &window : NULL; }
void glfwSwapBuffers(void *w) { (void) w; }
void glfwSwapInterval(int interval) { (void) interval; }
int glfwExtensionSupported(const char *extension) { (void) extension; return FALSE_; }
GLFWglproc glfwGetProcAddress(const char *name) {
    if (osmesaGetProc) {
        void *address = osmesaGetProc(name);
        if (address) {
            return (GLFWglproc) address;
        }
    }
    void *symbol = dlsym(RTLD_DEFAULT, name);
    return (GLFWglproc) symbol;
}
const char **glfwGetRequiredInstanceExtensions(uint32_t *count) {
    if (count) *count = 0;
    return NULL;
}
