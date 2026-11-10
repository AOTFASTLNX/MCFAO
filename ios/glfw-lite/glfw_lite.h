#ifndef FAOT_GLFW_LITE_H
#define FAOT_GLFW_LITE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct GLFWwindow GLFWwindow;
typedef struct GLFWmonitor GLFWmonitor;
typedef struct GLFWcursor GLFWcursor;
typedef struct { int width, height, redBits, greenBits, blueBits, refreshRate; } GLFWvidmode;
typedef struct { int width, height; unsigned char *pixels; } GLFWimage;
typedef void (*GLFWerrorfun)(int, const char *);
typedef void (*GLFWmonitorfun)(GLFWmonitor *, int);
typedef void (*GLFWwindowposfun)(GLFWwindow *, int, int);
typedef GLFWwindowposfun GLFWwindowsizefun;
typedef GLFWwindowposfun GLFWframebuffersizefun;
typedef void (*GLFWwindowclosefun)(GLFWwindow *);
typedef void (*GLFWwindowfocusfun)(GLFWwindow *, int);
typedef GLFWwindowfocusfun GLFWwindowiconifyfun;
typedef GLFWwindowfocusfun GLFWcursorenterfun;
typedef void (*GLFWkeyfun)(GLFWwindow *, int, int, int, int);
typedef void (*GLFWcharfun)(GLFWwindow *, unsigned int);
typedef void (*GLFWmousebuttonfun)(GLFWwindow *, int, int, int);
typedef void (*GLFWcursorposfun)(GLFWwindow *, double, double);
typedef GLFWcursorposfun GLFWscrollfun;
typedef void (*GLFWdropfun)(GLFWwindow *, int, const char **);
typedef void (*GLFWimestatusfun)(GLFWwindow *);
/* Mojang 3.4.1 binding: (window, count, UTF-32*, blockCount, int*, focusedBlock, caret). */
typedef void (*GLFWpreeditfun)(GLFWwindow *, int, unsigned int *, int, int *, int, int);
enum {
    GLFW_FALSE = 0, GLFW_TRUE = 1, GLFW_NO_ERROR = 0,
    GLFW_NOT_INITIALIZED = 0x10001, GLFW_INVALID_VALUE = 0x10004,
    GLFW_API_UNAVAILABLE = 0x10006, GLFW_PLATFORM_ERROR = 0x10008,
    GLFW_FEATURE_UNAVAILABLE = 0x1000c, GLFW_FOCUSED = 0x20001,
    GLFW_CLIENT_API = 0x22001, GLFW_NO_API = 0, GLFW_OPENGL_API = 0x30001,
    GLFW_CURSOR = 0x33001, GLFW_RAW_MOUSE_MOTION = 0x33005,
    GLFW_CURSOR_NORMAL = 0x34001, GLFW_CURSOR_HIDDEN = 0x34002,
    GLFW_CURSOR_DISABLED = 0x34003, GLFW_CONNECTED = 0x40001,
    GLFW_IME = 0x33007, FAOT_GLFW_PLATFORM_IOS = 0x60010
};
int glfwInit(void);
void glfwTerminate(void);
void glfwInitHint(int, int);
void glfwDefaultWindowHints(void);
void glfwWindowHint(int, int);
int glfwGetPlatform(void);
int glfwPlatformSupported(int);
const char *glfwGetVersionString(void);
void glfwGetVersion(int *, int *, int *);
GLFWerrorfun glfwSetErrorCallback(GLFWerrorfun);
int glfwGetError(const char **);
GLFWwindow *glfwCreateWindow(int, int, const char *, GLFWmonitor *, GLFWwindow *);
void glfwDestroyWindow(GLFWwindow *);
int glfwWindowShouldClose(GLFWwindow *);
void glfwSetWindowShouldClose(GLFWwindow *, int);
void glfwPollEvents(void);
void glfwGetWindowSize(GLFWwindow *, int *, int *);
void glfwGetFramebufferSize(GLFWwindow *, int *, int *);
void glfwGetWindowPos(GLFWwindow *, int *, int *);
void glfwSetWindowTitle(GLFWwindow *, const char *);
void glfwSetWindowSizeLimits(GLFWwindow *, int, int, int, int);
void glfwSetWindowIcon(GLFWwindow *, int, const GLFWimage *);
GLFWmonitor *glfwGetPrimaryMonitor(void);
GLFWmonitor **glfwGetMonitors(int *);
const GLFWvidmode *glfwGetVideoMode(GLFWmonitor *);
const GLFWvidmode *glfwGetVideoModes(GLFWmonitor *, int *);
void glfwGetMonitorPos(GLFWmonitor *, int *, int *);
const char *glfwGetMonitorName(GLFWmonitor *);
GLFWmonitor *glfwGetWindowMonitor(GLFWwindow *);
void glfwSetWindowMonitor(GLFWwindow *, GLFWmonitor *, int, int, int, int, int);
GLFWmonitorfun glfwSetMonitorCallback(GLFWmonitorfun);
void glfwMakeContextCurrent(GLFWwindow *);
GLFWwindow *glfwGetCurrentContext(void);
void glfwSwapBuffers(GLFWwindow *);
void glfwSwapInterval(int);
double glfwGetTime(void);
uint64_t glfwGetTimerValue(void);
uint64_t glfwGetTimerFrequency(void);
int glfwGetInputMode(GLFWwindow *, int);
void glfwSetInputMode(GLFWwindow *, int, int);
int glfwRawMouseMotionSupported(void);
int glfwGetKey(GLFWwindow *, int);
const char *glfwGetKeyName(int, int);
void glfwSetCursorPos(GLFWwindow *, double, double);
void glfwGetCursorPos(GLFWwindow *, double *, double *);
GLFWcursor *glfwCreateStandardCursor(int);
void glfwDestroyCursor(GLFWcursor *);
void glfwSetCursor(GLFWwindow *, GLFWcursor *);
const char *glfwGetClipboardString(GLFWwindow *);
void glfwSetClipboardString(GLFWwindow *, const char *);
void glfwSetPreeditCursorRectangle(GLFWwindow *, int, int, int, int);
void *glfwGetCocoaWindow(GLFWwindow *);
GLFWwindowposfun glfwSetWindowPosCallback(GLFWwindow *, GLFWwindowposfun);
GLFWwindowsizefun glfwSetWindowSizeCallback(GLFWwindow *, GLFWwindowsizefun);
GLFWframebuffersizefun glfwSetFramebufferSizeCallback(GLFWwindow *, GLFWframebuffersizefun);
GLFWwindowclosefun glfwSetWindowCloseCallback(GLFWwindow *, GLFWwindowclosefun);
GLFWwindowfocusfun glfwSetWindowFocusCallback(GLFWwindow *, GLFWwindowfocusfun);
GLFWwindowiconifyfun glfwSetWindowIconifyCallback(GLFWwindow *, GLFWwindowiconifyfun);
GLFWcursorenterfun glfwSetCursorEnterCallback(GLFWwindow *, GLFWcursorenterfun);
GLFWkeyfun glfwSetKeyCallback(GLFWwindow *, GLFWkeyfun);
GLFWcharfun glfwSetCharCallback(GLFWwindow *, GLFWcharfun);
GLFWmousebuttonfun glfwSetMouseButtonCallback(GLFWwindow *, GLFWmousebuttonfun);
GLFWcursorposfun glfwSetCursorPosCallback(GLFWwindow *, GLFWcursorposfun);
GLFWscrollfun glfwSetScrollCallback(GLFWwindow *, GLFWscrollfun);
GLFWdropfun glfwSetDropCallback(GLFWwindow *, GLFWdropfun);
GLFWimestatusfun glfwSetIMEStatusCallback(GLFWwindow *, GLFWimestatusfun);
GLFWpreeditfun glfwSetPreeditCallback(GLFWwindow *, GLFWpreeditfun);

/* Narrow host/Metal bridge. UIKit owns the view, game thread owns the callback dispatch. */
enum { FAOT_EVENT_RESIZE, FAOT_EVENT_FOCUS, FAOT_EVENT_CURSOR, FAOT_EVENT_BUTTON,
       FAOT_EVENT_SCROLL, FAOT_EVENT_CHAR, FAOT_EVENT_KEY, FAOT_EVENT_CLOSE, FAOT_EVENT_CURSOR_DELTA };
int faot_glfw_enqueue(GLFWwindow *, int kind, double a, double b, int c, int d);
void faot_glfw_resize(GLFWwindow *, int width, int height, int pixelsWidth, int pixelsHeight);
void *faot_glfw_metal_layer(GLFWwindow *);
void *faot_surface_create(GLFWwindow *, int *, int *, int *, int *);
void faot_surface_destroy(void *);
void faot_surface_screen(GLFWvidmode *);
void faot_surface_input(void *, int mode, int value);
void faot_surface_ime_rect(void *, int, int, int, int);
void faot_surface_title(void *, const char *);
void faot_surface_clipboard_set(const char *);
char *faot_surface_clipboard_copy(void);
void *faot_surface_layer(void *);
#ifdef __cplusplus
}
#endif
#endif
