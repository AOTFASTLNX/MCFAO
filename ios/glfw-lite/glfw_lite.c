#include "glfw_lite.h"
#include "osmesa_gl.h"
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* One iOS scene/surface. Handles are validated before dereference, including queued events. */
struct GLFWmonitor { int connected; };
struct GLFWcursor { int shape; };
struct GLFWwindow {
    void *surface;
    int width, height, pixelWidth, pixelHeight, close, focus, cursorMode, ime;
    int glContext, swapInterval, wantsGL;
    double cursorX, cursorY;
    GLFWmonitor *monitor;
    GLFWwindowposfun pos; GLFWwindowsizefun size; GLFWframebuffersizefun framebuffer;
    GLFWwindowclosefun closed; GLFWwindowfocusfun focused; GLFWwindowiconifyfun iconified;
    GLFWcursorenterfun entered; GLFWkeyfun key; GLFWcharfun character;
    GLFWmousebuttonfun button; GLFWcursorposfun cursor; GLFWscrollfun scroll;
    GLFWdropfun drop; GLFWimestatusfun imeStatus; GLFWpreeditfun preedit;
    unsigned char keys[349];
    /* Pollable mirror of FAOT_EVENT_BUTTON presses: malilib re-checks keybinds by polling
     * glfwGetMouseButton every tick, so button state must survive between events the same
     * way key state does for glfwGetKey. GLFW supports 8 buttons; GLFW_MOUSE_BUTTON_LAST=7. */
    unsigned char mouseButtons[8];
};
typedef struct { GLFWwindow *window; int kind; double a, b; int c, d; } Event;
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static Event events[1024];
static unsigned int readIndex, writeIndex;
static GLFWwindow *live;
static GLFWmonitor monitor = {1};
static GLFWmonitor *monitors[] = {&monitor};
static GLFWvidmode video;
static GLFWerrorfun errorCallback;
static GLFWmonitorfun monitorCallback;
static int initialized, clientAPI = GLFW_OPENGL_API;
static double gl41_scale_value(void) {
    if (live && !live->wantsGL) return 1.0;
    const char *text = getenv("FAOT_GL41_SCALE");
    double value = text ? atof(text) : 0.8;
    if (!(value >= 0.5 && value <= 1.0)) value = 0.8;
    return value;
}
static _Thread_local int lastError;
static _Thread_local char errorText[512], returnedError[512];
static _Thread_local GLFWwindow *current;
static char *clipboard;
static double epoch;

static double monotonic(void) {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return value.tv_sec + value.tv_nsec / 1000000000.0;
}
static void fail(int code, const char *message) {
    lastError = code;
    snprintf(errorText, sizeof errorText, "%s", message);
    fprintf(stderr, "[GLFW-lite] 0x%x: %s\n", code, message);
    if (errorCallback) errorCallback(code, errorText);
}
static int ready(void) {
    if (initialized) return 1;
    fail(GLFW_NOT_INITIALIZED, "glfwInit has not succeeded"); return 0;
}
static int valid(GLFWwindow *w) {
    if (!ready()) return 0;
    if (w && w == live) return 1;
    fail(GLFW_INVALID_VALUE, "invalid or destroyed window handle"); return 0;
}
static int validMonitor(GLFWmonitor *m) {
    if (!ready()) return 0;
    if (m == &monitor) return 1;
    fail(GLFW_INVALID_VALUE, "invalid monitor"); return 0;
}
int glfwInit(void) {
    if (!initialized) { epoch = monotonic(); faot_surface_screen(&video); initialized = 1; }
    fprintf(stderr, "[GLFW-lite] initialized: %s\n",glfwGetVersionString());
    return 1;
}
void glfwTerminate(void) {
    if (live) glfwDestroyWindow(live);
    initialized = 0; errorCallback = NULL; monitorCallback = NULL;
    free(clipboard); clipboard = NULL;
    glfwDefaultWindowHints();
}
void glfwInitHint(int hint, int value) {
    /* Cocoa menubar/chdir are desktop-only; they have no process-global side effects here. */
    fprintf(stderr, "[GLFW-lite] init hint 0x%x=%d has no UIKit equivalent\n", hint, value);
}
void glfwDefaultWindowHints(void) { clientAPI = GLFW_OPENGL_API; }
void glfwWindowHint(int hint, int value) {
    if (!ready()) return;
    if (hint == GLFW_CLIENT_API) clientAPI = value;
    else fprintf(stderr, "[GLFW-lite] window hint 0x%x=%d is not configurable on iOS\n", hint, value);
}
int glfwGetPlatform(void) { return ready() ? FAOT_GLFW_PLATFORM_IOS : 0; }
int glfwPlatformSupported(int platform) { return platform == FAOT_GLFW_PLATFORM_IOS; }
const char *glfwGetVersionString(void) {
#if defined(__ENVIRONMENT_IPHONE_OS_VERSION_MIN_REQUIRED__)
    return "3.4.0 FabricAOT iOS UIKit Metal (experimental)";
#else
    return "3.4.0 FabricAOT host test surface (fixture only)";
#endif
}
void glfwGetVersion(int *a, int *b, int *c) { if(a)*a=3; if(b)*b=4; if(c)*c=0; }
GLFWerrorfun glfwSetErrorCallback(GLFWerrorfun f) { GLFWerrorfun old=errorCallback; errorCallback=f; return old; }
int glfwGetError(const char **description) {
    int code = lastError;
    if (description) {
        memcpy(returnedError, errorText, sizeof returnedError);
        *description = code ? returnedError : NULL;
    }
    lastError = 0; return code;
}
GLFWwindow *glfwCreateWindow(int width, int height, const char *title, GLFWmonitor *m, GLFWwindow *share) {
    if (!ready()) return NULL;
    if (width <= 0 || height <= 0 || !title || (m && m != &monitor)) {
        fail(GLFW_INVALID_VALUE, "invalid window dimensions, title or monitor"); return NULL;
    }
    if ((clientAPI != GLFW_NO_API && clientAPI != GLFW_OPENGL_API) || share) {
        fail(GLFW_API_UNAVAILABLE, "GLFW-lite supports GLFW_NO_API or GLFW_OPENGL_API without sharing"); return NULL;
    }
    if (live) { fail(GLFW_FEATURE_UNAVAILABLE, "only one UIKit game surface is supported"); return NULL; }
    GLFWwindow *w = calloc(1, sizeof *w);
    if (!w) { fail(GLFW_PLATFORM_ERROR, "window allocation failed"); return NULL; }
    w->width=width; w->height=height; w->monitor=m; w->cursorMode=GLFW_CURSOR_NORMAL; w->focus=1;
    w->wantsGL=(clientAPI!=GLFW_NO_API);
    pthread_mutex_lock(&mutex); live=w; pthread_mutex_unlock(&mutex);
    w->surface=faot_surface_create(w, &w->width, &w->height, &w->pixelWidth, &w->pixelHeight);
    if (!w->surface) {
        pthread_mutex_lock(&mutex); live=NULL; readIndex=writeIndex=0; pthread_mutex_unlock(&mutex);
        free(w); fail(GLFW_PLATFORM_ERROR, "no foreground UIWindowScene / Metal surface available"); return NULL;
    }
    faot_surface_title(w->surface,title);
    /* Initial real geometry/focus are delivered once, after the caller installs callbacks. */
    faot_glfw_enqueue(w,FAOT_EVENT_RESIZE,0,0,0,0);
    faot_glfw_enqueue(w,FAOT_EVENT_FOCUS,1,0,0,0);
    fprintf(stderr,"[GLFW-lite] window created %dx%d points %dx%d pixels\n",w->width,w->height,w->pixelWidth,w->pixelHeight);
    return w;
}
void glfwDestroyWindow(GLFWwindow *w) {
    if (!valid(w)) return;
    if (w->glContext) { faot_gl41_release(); w->glContext=0; }
    pthread_mutex_lock(&mutex); live=NULL; readIndex=writeIndex=0; pthread_mutex_unlock(&mutex);
    faot_surface_destroy(w->surface);
    if (current==w) current=NULL;
    free(w);
}
int glfwWindowShouldClose(GLFWwindow *w) { return valid(w) ? w->close : 1; }
void glfwSetWindowShouldClose(GLFWwindow *w,int value) { if(valid(w))w->close=!!value; }
int faot_glfw_enqueue(GLFWwindow *w,int kind,double a,double b,int c,int d) {
    int accepted=0;
    pthread_mutex_lock(&mutex);
    if (w && w==live && writeIndex-readIndex < 1024) {
        events[writeIndex++ % 1024]=(Event){w,kind,a,b,c,d}; accepted=1;
    }
    pthread_mutex_unlock(&mutex);
    if (!accepted) fprintf(stderr,"[GLFW-lite] event rejected: stale window or full queue\n");
    return accepted;
}
void faot_glfw_resize(GLFWwindow *w,int width,int height,int pw,int ph) {
    pthread_mutex_lock(&mutex);
    if (w && w==live) { w->width=width; w->height=height; w->pixelWidth=pw; w->pixelHeight=ph; }
    pthread_mutex_unlock(&mutex);
    faot_glfw_enqueue(w,FAOT_EVENT_RESIZE,0,0,0,0);
}
void glfwPollEvents(void) {
    if (!ready()) return;
    /* Bound a poll to its initial queue: callbacks may enqueue more events or destroy a window. */
    pthread_mutex_lock(&mutex); unsigned int end=writeIndex; pthread_mutex_unlock(&mutex);
    for (;;) {
        pthread_mutex_lock(&mutex);
        if (readIndex==writeIndex || readIndex==end) { pthread_mutex_unlock(&mutex); break; }
        Event e=events[readIndex++ % 1024];
        GLFWwindow *w=(e.window==live ? live : NULL);
        pthread_mutex_unlock(&mutex);
        if (!w) continue;
        switch(e.kind) {
        case FAOT_EVENT_RESIZE: {
            pthread_mutex_lock(&mutex);
            int width=w->width,height=w->height,pw=w->pixelWidth,ph=w->pixelHeight;
            pthread_mutex_unlock(&mutex);
            double scale=gl41_scale_value();
            if(w->size)w->size(w,(int)(width*scale+0.5),(int)(height*scale+0.5));
            if(w==live && w->framebuffer)w->framebuffer(w,(int)(pw*scale+0.5),(int)(ph*scale+0.5));
            break;
        }
        case FAOT_EVENT_FOCUS:
            w->focus=!!e.a;
            if(!w->focus){
                for(int k=0;k<349&&w==live;k++)if(w->keys[k]){w->keys[k]=0;if(w->key)w->key(w,k,0,0,0);}
                for(int b=0;b<8&&w==live;b++)w->mouseButtons[b]=0;
            }
            if(w==live&&w->focused)w->focused(w,w->focus);break;
        case FAOT_EVENT_CURSOR: {
            double scale=gl41_scale_value();
            w->cursorX=e.a*scale; w->cursorY=e.b*scale;
            if(w->cursor)w->cursor(w,w->cursorX,w->cursorY);
            break;
        }
        case FAOT_EVENT_CURSOR_DELTA:
            if(w->cursorMode==GLFW_CURSOR_DISABLED){w->cursorX+=e.a;w->cursorY+=e.b;if(w->cursor)w->cursor(w,w->cursorX,w->cursorY);}break;
        case FAOT_EVENT_BUTTON:
            /* uikit_surface.m enqueues (button, action, 0, 0): the action lands in e.b. */
            if((int)e.a>=0&&(int)e.a<8)w->mouseButtons[(int)e.a]=(e.b!=0);
            if(w->button)w->button(w,(int)e.a,(int)e.b,e.c); break;
        case FAOT_EVENT_SCROLL: if(w->scroll)w->scroll(w,e.a,e.b); break;
        case FAOT_EVENT_CHAR: if(w->character)w->character(w,(unsigned int)e.a); break;
        case FAOT_EVENT_KEY:
            if ((int)e.a>=0 && (int)e.a<349)w->keys[(int)e.a]=(e.c!=0);
            if(w->key)w->key(w,(int)e.a,(int)e.b,e.c,e.d); break;
        case FAOT_EVENT_CLOSE: w->close=1; if(w->closed)w->closed(w); break;
        default: fail(GLFW_INVALID_VALUE,"unknown event kind"); break;
        }
    }
}
void glfwGetWindowSize(GLFWwindow *w,int *a,int *b) { if(valid(w)){double scale=gl41_scale_value();pthread_mutex_lock(&mutex);if(a)*a=(int)(w->width*scale+0.5);if(b)*b=(int)(w->height*scale+0.5);pthread_mutex_unlock(&mutex);} }
void glfwGetFramebufferSize(GLFWwindow *w,int *a,int *b) { if(valid(w)){double scale=gl41_scale_value();pthread_mutex_lock(&mutex);if(a)*a=(int)(w->pixelWidth*scale+0.5);if(b)*b=(int)(w->pixelHeight*scale+0.5);pthread_mutex_unlock(&mutex);} }
void glfwGetWindowPos(GLFWwindow *w,int *a,int *b) { if(valid(w)){if(a)*a=0;if(b)*b=0;} }
void glfwSetWindowTitle(GLFWwindow *w,const char *title) { if(valid(w)&&title)faot_surface_title(w->surface,title); }
void glfwSetWindowSizeLimits(GLFWwindow *w,int a,int b,int c,int d) { (void)a;(void)b;(void)c;(void)d;if(valid(w))fprintf(stderr,"[GLFW-lite] window size limits are controlled by UIWindowScene\n"); }
void glfwSetWindowIcon(GLFWwindow *w,int count,const GLFWimage *images) { (void)count;(void)images;if(valid(w))fprintf(stderr,"[GLFW-lite] UIKit uses the signed app icon\n"); }
GLFWmonitor *glfwGetPrimaryMonitor(void) { return ready()?&monitor:NULL; }
GLFWmonitor **glfwGetMonitors(int *count) { if(count)*count=initialized?1:0;return ready()?monitors:NULL; }
const GLFWvidmode *glfwGetVideoMode(GLFWmonitor *m) { return validMonitor(m)?&video:NULL; }
const GLFWvidmode *glfwGetVideoModes(GLFWmonitor *m,int *count) { if(count)*count=(initialized && m==&monitor)?1:0;return validMonitor(m)?&video:NULL; }
void glfwGetMonitorPos(GLFWmonitor *m,int *a,int *b) { if(validMonitor(m)){if(a)*a=0;if(b)*b=0;} }
const char *glfwGetMonitorName(GLFWmonitor *m) { return validMonitor(m)?"iOS UIWindowScene display":NULL; }
GLFWmonitor *glfwGetWindowMonitor(GLFWwindow *w) { return valid(w)?w->monitor:NULL; }
void glfwSetWindowMonitor(GLFWwindow *w,GLFWmonitor *m,int x,int y,int width,int height,int rate) {
    (void)x;(void)y;(void)width;(void)height;(void)rate;
    if(!valid(w))return;
    if(m && !validMonitor(m))return;
    w->monitor=m;
    fprintf(stderr,"[GLFW-lite] fullscreen preference recorded; UIKit controls scene geometry\n");
}
GLFWmonitorfun glfwSetMonitorCallback(GLFWmonitorfun f) { GLFWmonitorfun old=monitorCallback;monitorCallback=f;return old; }
void glfwMakeContextCurrent(GLFWwindow *w) {
    if(!w){current=NULL;return;}
    if(!valid(w))return;
    current=w;
    if(!w->wantsGL)return;
    if(w->glContext)return;
    int scale_w=(int)(w->pixelWidth*gl41_scale_value()+0.5), scale_h=(int)(w->pixelHeight*gl41_scale_value()+0.5);
    if(w->surface && faot_gl41_make_current(w->surface,scale_w,scale_h))w->glContext=1;
    else fail(GLFW_API_UNAVAILABLE,"OpenGL 4.1 context unavailable");
}
GLFWwindow *glfwGetCurrentContext(void) { return current==live?current:NULL; }
void glfwSwapBuffers(GLFWwindow *w) {
    if(!valid(w))return;
    if(!w->wantsGL){fail(GLFW_API_UNAVAILABLE,"Metal presentFrame must present the drawable, not glfwSwapBuffers");return;}
    if(!w->glContext){fail(GLFW_API_UNAVAILABLE,"OpenGL context was not created");return;}
    if(w->pixelWidth!=0 && w->pixelHeight!=0){
        int scale_w=(int)(w->pixelWidth*gl41_scale_value()+0.5), scale_h=(int)(w->pixelHeight*gl41_scale_value()+0.5);
        faot_gl41_make_current(w->surface,scale_w,scale_h);
    }
    faot_gl41_swap(w->surface);
}
void glfwSwapInterval(int interval) { if(live)live->swapInterval=interval; }
double glfwGetTime(void) { return ready()?monotonic()-epoch:0; }
uint64_t glfwGetTimerValue(void) { struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec; }
uint64_t glfwGetTimerFrequency(void) { return 1000000000; }
int glfwGetInputMode(GLFWwindow *w,int mode) {
    if(!valid(w))return 0;
    if(mode==GLFW_CURSOR)return w->cursorMode;
    if(mode==GLFW_IME)return w->ime;
    if(mode==GLFW_RAW_MOUSE_MOTION)return 0;
    fail(GLFW_FEATURE_UNAVAILABLE,"unsupported input mode");return 0;
}
void glfwSetInputMode(GLFWwindow *w,int mode,int value) {
    if(!valid(w))return;
    if(mode==GLFW_CURSOR && value>=GLFW_CURSOR_NORMAL && value<=GLFW_CURSOR_DISABLED)w->cursorMode=value;
    else if(mode==GLFW_IME)w->ime=!!value;
    else { fail(GLFW_FEATURE_UNAVAILABLE,"unsupported input mode/value");return; }
    faot_surface_input(w->surface,mode,value);
}
int glfwRawMouseMotionSupported(void) { return 0; }
int glfwGetKey(GLFWwindow *w,int key) { return valid(w)&&key>=0&&key<349?w->keys[key]:0; }
int glfwGetMouseButton(GLFWwindow *w,int button) { return valid(w)&&button>=0&&button<8?w->mouseButtons[button]:0; }
const char *glfwGetKeyName(int key,int scan) { (void)scan;static _Thread_local char name[2];if(key>=32&&key<=126){name[0]=(char)key;name[1]=0;return name;}return NULL; }
void glfwSetCursorPos(GLFWwindow *w,double x,double y) { if(valid(w)&&isfinite(x)&&isfinite(y)){double scale=gl41_scale_value();faot_glfw_enqueue(w,FAOT_EVENT_CURSOR,x/scale,y/scale,0,0);} }
void glfwGetCursorPos(GLFWwindow *w,double *x,double *y) { if(valid(w)){if(x)*x=w->cursorX;if(y)*y=w->cursorY;} }
GLFWcursor *glfwCreateStandardCursor(int shape) { if(!ready())return NULL;GLFWcursor *c=malloc(sizeof *c);if(c)c->shape=shape;return c; }
void glfwDestroyCursor(GLFWcursor *c) { free(c); }
void glfwSetCursor(GLFWwindow *w,GLFWcursor *c) { (void)c;(void)w; }  /* hot path: Minecraft sets the cursor every frame */
const char *glfwGetClipboardString(GLFWwindow *w) { if(w&&!valid(w))return NULL;free(clipboard);clipboard=faot_surface_clipboard_copy();return clipboard; }
void glfwSetClipboardString(GLFWwindow *w,const char *s) { if((!w||valid(w))&&s)faot_surface_clipboard_set(s); }
void glfwSetPreeditCursorRectangle(GLFWwindow *w,int x,int y,int width,int height) { if(valid(w))faot_surface_ime_rect(w->surface,x,y,width,height); }
void *glfwGetCocoaWindow(GLFWwindow *w) { if(valid(w))fail(GLFW_FEATURE_UNAVAILABLE,"NSWindow does not exist on iOS; use faot_glfw_metal_layer");return NULL; }
void *faot_glfw_metal_layer(GLFWwindow *w) { return valid(w)?faot_surface_layer(w->surface):NULL; }
#define SET_CALLBACK(Name,Type,Field) Type glfwSet##Name##Callback(GLFWwindow *w,Type f){if(!valid(w))return NULL;Type old=w->Field;w->Field=f;return old;}
SET_CALLBACK(WindowPos,GLFWwindowposfun,pos)
SET_CALLBACK(WindowSize,GLFWwindowsizefun,size)
SET_CALLBACK(FramebufferSize,GLFWframebuffersizefun,framebuffer)
SET_CALLBACK(WindowClose,GLFWwindowclosefun,closed)
SET_CALLBACK(WindowFocus,GLFWwindowfocusfun,focused)
SET_CALLBACK(WindowIconify,GLFWwindowiconifyfun,iconified)
SET_CALLBACK(CursorEnter,GLFWcursorenterfun,entered)
SET_CALLBACK(Key,GLFWkeyfun,key)
SET_CALLBACK(Char,GLFWcharfun,character)
SET_CALLBACK(MouseButton,GLFWmousebuttonfun,button)
SET_CALLBACK(CursorPos,GLFWcursorposfun,cursor)
SET_CALLBACK(Scroll,GLFWscrollfun,scroll)
SET_CALLBACK(Drop,GLFWdropfun,drop)
SET_CALLBACK(IMEStatus,GLFWimestatusfun,imeStatus)
SET_CALLBACK(Preedit,GLFWpreeditfun,preedit)
