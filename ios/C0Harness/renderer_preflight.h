#ifndef FAOT_RENDERER_PREFLIGHT_H
#define FAOT_RENDERER_PREFLIGHT_H
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

/* Query only our fixed C ABI; no game/JVM code executes here. Keep the handle open because
 * the JNI loader will reuse this same UIKit/GLFW image later in the process. */
static int FAOTRequireGL41Bridge(const char *frameworks, char *reason, size_t capacity) {
    char path[4096];
    if (snprintf(path, sizeof path, "%s/libglfw.dylib", frameworks) >= (int)sizeof path) {
        snprintf(reason, capacity, "GLFW path exceeds the native path budget"); return 0;
    }
    void *handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!handle) {
        snprintf(reason, capacity, "Cannot load GLFW bridge: %s", dlerror()); return 0;
    }
    typedef const char *(*contract_fn)(void);
    contract_fn query = (contract_fn)dlsym(handle, "faot_glfw_client_api_contract");
    const char *contract = query ? query() : NULL;
    if (!contract || strcmp(contract, "FAOT_GLFW_CLIENT_APIS:v1:NO_API,OPENGL_OSMESA")) {
        snprintf(reason, capacity, "GL41 requires the OpenGL/OSMesa GLFW bridge; rebuild the native graphics inputs");
        return 0;
    }
    fprintf(stdout, "[FAOT] glfwClientAPIs=%s\n", contract);
    fflush(stdout);
    return 1;
}
#endif
