#include "osmesa_gl.h"

#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <pthread/qos.h>
#include <time.h>

/* Constants from Mesa's MIT-licensed include/GL/osmesa.h (25.x). */
enum {
    OSMESA_BGRA_FORMAT = 0x1,
    OSMESA_RGBA_FORMAT = 0x1908,
    OSMESA_ROW_LENGTH = 0x10,
    OSMESA_Y_UP = 0x11,
    OSMESA_FORMAT = 0x22,
    OSMESA_DEPTH_BITS = 0x30,
    OSMESA_STENCIL_BITS = 0x31,
    OSMESA_PROFILE = 0x33,
    OSMESA_COMPAT_PROFILE = 0x35,
    OSMESA_CONTEXT_MAJOR_VERSION = 0x36,
    OSMESA_CONTEXT_MINOR_VERSION = 0x37,
    GL_UNSIGNED_BYTE_VALUE = 0x1401
};

typedef void *OSMesaContext;
typedef OSMesaContext (*CreateContextAttribs)(const int *, OSMesaContext);
typedef void (*DestroyContext)(OSMesaContext);
typedef unsigned char (*MakeCurrent)(OSMesaContext, void *, int, int, int);
typedef void (*PixelStore)(int, int);
typedef unsigned char *(*GetString)(int);
typedef void (*Finish)(void);

typedef struct {
    void *library;
    CreateContextAttribs create;
    DestroyContext destroy;
    MakeCurrent make_current;
    PixelStore pixel_store;
    GetString get_string;
    Finish finish;
} OSMesaAPI;

static OSMesaAPI api;
static int attempted;
static OSMesaContext context;
static void *frame;
static size_t frame_bytes;
static int frame_width, frame_height;
static void *present_surface;
static int current_width, current_height, logged, made_current, bgra_format = 1;
static int qos_set, perf_frames;
static double perf_last, perf_finish_ms, perf_present_ms;
/* One-millisecond buckets, with 100 representing 100 ms or longer. */
enum { PERF_LAST_BUCKET = 100 };
static unsigned perf_finish_hist[PERF_LAST_BUCKET + 1];
static unsigned perf_outside_hist[PERF_LAST_BUCKET + 1];
static unsigned perf_outside_frames;
static double perf_previous_present;

static void perf_observe(unsigned *hist, double ms) {
    unsigned bucket = ms >= PERF_LAST_BUCKET ? PERF_LAST_BUCKET : (unsigned)ms;
    if (bucket < PERF_LAST_BUCKET && (double)bucket < ms) bucket++;
    hist[bucket]++;
}

static unsigned perf_p95(const unsigned *hist, unsigned samples) {
    unsigned rank = samples - samples / 20;
    for (unsigned i = 0; i <= PERF_LAST_BUCKET; i++) {
        if (hist[i] >= rank) return i;
        rank -= hist[i];
    }
    return PERF_LAST_BUCKET;
}

static void perf_reset_window(void) {
    perf_frames = 0;
    perf_finish_ms = perf_present_ms = 0;
    perf_outside_frames = 0;
    memset(perf_finish_hist, 0, sizeof perf_finish_hist);
    memset(perf_outside_hist, 0, sizeof perf_outside_hist);
}

extern void faot_surface_present_bgra(void *surface, const void *pixels, int width, int height);

static double now_ms(void) {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return value.tv_sec * 1000.0 + value.tv_nsec / 1000000.0;
}

static void set_default(const char *name, const char *value) {
    if (!getenv(name)) setenv(name, value, 1);
}

static int load_api(void) {
    if (attempted) return api.library != NULL;
    attempted = 1;
    set_default("GALLIUM_DRIVER", "zink");
    set_default("MESA_GL_VERSION_OVERRIDE", "4.1");
    set_default("MESA_GLSL_VERSION_OVERRIDE", "410");
    /* This OSMesa export surface implements OpenGL 4.1 entry points. Hide 4.5 direct-state
     * access so Minecraft takes its verified non-DSA path instead of resolving absent slots. */
    set_default("MESA_EXTENSION_OVERRIDE", "-GL_ARB_direct_state_access");
    set_default("mesa_glthread", "false");
    /* zink is a Vulkan driver; MoltenVK is the Vulkan implementation on iOS. */
    set_default("MVK_CONFIG_FAST_MATH_ENABLED", "2");
    set_default("MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS", "1");
    set_default("MVK_CONFIG_SWAPCHAIN_MIN_MAG_FILTER_USE_NEAREST", "0");
    const char *home = getenv("HOME");
    if (home) {
        char cache[900];
        snprintf(cache, sizeof cache, "%s/Documents/.mesa_shader_cache", home);
        (void)mkdir(cache, 0700);
        set_default("MESA_SHADER_CACHE_DIR", cache);
        set_default("MESA_GLSL_CACHE_DIR", cache);
    }
    /* MoltenVK is preloaded under its @rpath name so Mesa's zink driver finds the already
     * loaded Vulkan implementation in the signed app Frameworks directory. */
    void *molten = dlopen("@rpath/libMoltenVK.dylib", RTLD_NOW | RTLD_GLOBAL);
    if (!molten) fprintf(stderr, "[GL41] libMoltenVK.dylib unavailable: %s\n", dlerror());
    api.library = dlopen("@rpath/libOSMesa.8.dylib", RTLD_NOW | RTLD_GLOBAL);
    if (!api.library) {
        fprintf(stderr, "[GL41] libOSMesa.8.dylib unavailable: %s\n", dlerror());
        return 0;
    }
    api.create = (CreateContextAttribs)dlsym(api.library, "OSMesaCreateContextAttribs");
    api.destroy = (DestroyContext)dlsym(api.library, "OSMesaDestroyContext");
    api.make_current = (MakeCurrent)dlsym(api.library, "OSMesaMakeCurrent");
    api.pixel_store = (PixelStore)dlsym(api.library, "OSMesaPixelStore");
    api.get_string = (GetString)dlsym(api.library, "glGetString");
    api.finish = (Finish)dlsym(api.library, "glFinish");
    if (!api.create || !api.destroy || !api.make_current || !api.pixel_store || !api.finish) {
        fprintf(stderr, "[GL41] libOSMesa is missing required entry points\n");
        return 0;
    }
    return 1;
}

static int resize(int width, int height) {
    if (width <= 0 || height <= 0) return 0;
    size_t needed = (size_t)width * (size_t)height * 4u;
    if (needed > (size_t)64u * 1024u * 1024u) {
        fprintf(stderr, "[GL41] refused oversized OSMesa frame %dx%d\n", width, height);
        return 0;
    }
    if (frame_bytes < needed) {
        void *grown = realloc(frame, needed);
        if (!grown) return 0;
        frame = grown;
        frame_bytes = needed;
    }
    frame_width = width;
    frame_height = height;
    return 1;
}

int faot_gl41_make_current(void *surface, int width, int height) {
    if (!load_api()) return 0;
    if (!qos_set) {
        (void)pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
        qos_set = 1;
    }
    present_surface = surface;
    if (!context) {
        /* A compatibility profile is the requested 4.1 feature set; Minecraft only relies on
         * core facilities that remain valid in this profile. */
        int attribs[] = {
            OSMESA_FORMAT, OSMESA_BGRA_FORMAT,
            OSMESA_DEPTH_BITS, 24,
            OSMESA_STENCIL_BITS, 8,
            OSMESA_PROFILE, OSMESA_COMPAT_PROFILE,
            OSMESA_CONTEXT_MAJOR_VERSION, 4,
            OSMESA_CONTEXT_MINOR_VERSION, 1,
            0
        };
        context = api.create(attribs, NULL);
        if (!context) {
            attribs[1] = OSMESA_RGBA_FORMAT;
            context = api.create(attribs, NULL);
            bgra_format = 0;
        }
        if (!context) {
            /* Last resort: let Mesa choose the highest profile/version it can create. The
             * game still validates the reported version before using it. */
            unsetenv("MESA_GL_VERSION_OVERRIDE");
            unsetenv("MESA_GLSL_VERSION_OVERRIDE");
            const int minimal[] = {OSMESA_FORMAT, OSMESA_RGBA_FORMAT,
                                   OSMESA_DEPTH_BITS, 24, OSMESA_STENCIL_BITS, 8, 0};
            context = api.create(minimal, NULL);
            bgra_format = 0;
        }
        if (!context) {
            fprintf(stderr, "[GL41] OSMesa 4.1 context creation failed\n");
            return 0;
        }
        fprintf(stderr, "[GL41] OSMesa context created; zink over MoltenVK\n");
        fprintf(stderr, "[GL41] first render size %dx%d\n", width, height);
    }
    if (!resize(width, height)) return 0;
    if (made_current && width == current_width && height == current_height) {
        return 1;
    }
    if (!api.make_current(context, frame, GL_UNSIGNED_BYTE_VALUE, width, height)) {
        fprintf(stderr, "[GL41] OSMesaMakeCurrent failed\n");
        return 0;
    }
    api.pixel_store(OSMESA_ROW_LENGTH, width);
    api.pixel_store(OSMESA_Y_UP, 0);
    current_width = width;
    current_height = height;
    made_current = 1;
    if (api.get_string && !logged) {
        logged = 1;
        const unsigned char *version = api.get_string(0x1F02 /* GL_VERSION */);
        const unsigned char *renderer = api.get_string(0x1F01 /* GL_RENDERER */);
        if (version) fprintf(stderr, "[GL41] GL_VERSION=%s\n", version);
        if (renderer) fprintf(stderr, "[GL41] GL_RENDERER=%s\n", renderer);
    }
    return 1;
}

void faot_gl41_swap(void *surface) {
    if (!context || !frame) return;
    double start = now_ms();
    if (api.finish) api.finish();
    double finished = now_ms();
    if (!bgra_format) {
        uint32_t *pixels = (uint32_t *)frame;
        size_t count = (size_t)frame_width * (size_t)frame_height;
        for (size_t i = 0; i < count; i++) {
            uint32_t value = pixels[i];
            pixels[i] = (value & 0xff00ff00u) | ((value & 0x00ff0000u) >> 16) | ((value & 0x000000ffu) << 16);
        }
    }
    faot_surface_present_bgra(surface ? surface : present_surface, frame, frame_width, frame_height);
    double presented = now_ms();
    perf_finish_ms += finished - start;
    perf_present_ms += presented - finished;
    perf_frames++;
    perf_observe(perf_finish_hist, finished - start);
    if (perf_previous_present != 0) {
        perf_observe(perf_outside_hist, start - perf_previous_present);
        perf_outside_frames++;
    }
    perf_previous_present = presented;
    if (perf_last == 0) perf_last = start;
    if (presented - perf_last >= 5000.0) {
        double seconds = (presented - perf_last) / 1000.0;
        fprintf(stderr, "[GL41] perf fps=%.1f finish=%.2fms present=%.2fms finishP95=%ums outsideSwapP95=%ums\n",
                perf_frames / seconds, perf_finish_ms / perf_frames, perf_present_ms / perf_frames,
                perf_p95(perf_finish_hist, (unsigned)perf_frames),
                perf_p95(perf_outside_hist, perf_outside_frames));
        perf_last = presented;
        perf_reset_window();
    }
}

void faot_gl41_release(void) {
    if (api.destroy && context) api.destroy(context);
    context = NULL;
    free(frame);
    frame = NULL;
    frame_bytes = 0;
    frame_width = frame_height = 0;
    made_current = logged = 0;
    bgra_format = 1;
    perf_last = perf_previous_present = 0;
    perf_reset_window();
}
