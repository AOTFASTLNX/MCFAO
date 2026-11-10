/* First-party, Mac build-JVM diagnostic only. No class transformation or allocation values.
 *
 * Two read-only modes:
 *  - default: the first heap OOM reports stack frames plus one shallow census (legacy records
 *    OOM/STACK_STATUS/FRAME/CLASSES_STATUS/CLASS/ITERATION_STATUS/CENSUS_END are unchanged).
 *  - opt-in scheduled snapshots: the "fabricaot.census.at=12,18,24" system property makes an
 *    agent thread take shallow class censuses at those second offsets, so the state *before* the
 *    OOM can be observed (SNAPSHOT_BEGIN/STATUS/CLASS/END).
 *
 * Callers must keep two limits in mind:
 *  - IterateThroughHeap stops the world and is expensive; each snapshot perturbs the run and can
 *    push an almost-full heap over the edge. Offsets are explicit because of that.
 *  - Counts are shallow objects present at that instant, including garbage a later collection
 *    would reclaim. They are not a dominance tree, not a root path, and not iOS target data.
 */
#include <jni.h>
#include <jvmti.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <string.h>
#include <time.h>

#define CLASS_LIMIT 131072
#define SNAPSHOT_MAX_OFFSETS 16
typedef struct { jlong count, bytes, elements; char *name; } Bucket;
static Bucket *buckets;
static FILE *report;
static atomic_int reported;
static atomic_int samples;
static char snapshot_spec[192];

static long long now_millis(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static void JNICALL sampled(jvmtiEnv *ti, JNIEnv *jni, jthread thread, jobject object,
                           jclass klass, jlong size) {
    (void)object;
    int id = atomic_fetch_add(&samples, 1);
    if (id >= 4096) return;
    char *name = NULL;
    (*ti)->GetClassSignature(ti, klass, &name, NULL);
    jvmtiFrameInfo frames[12]; jint depth = 0;
    jvmtiError status = (*ti)->GetStackTrace(ti, thread, 0, 12, frames, &depth);
    flockfile(report);
    if (ftell(report) > 8*1024*1024) {
        funlockfile(report);
        if (name) (*ti)->Deallocate(ti, (unsigned char *)name);
        return;
    }
    fprintf(report, "ALLOC\t%d\t%lld\t%.2048s\t%d\n", id, (long long)size, name ? name : "?", status);
    if (name) (*ti)->Deallocate(ti, (unsigned char *)name);
    for (jint i = 0; status == JVMTI_ERROR_NONE && i < depth; i++) {
        jclass owner = NULL; char *type = NULL, *method = NULL;
        (*ti)->GetMethodDeclaringClass(ti, frames[i].method, &owner);
        if (owner) (*ti)->GetClassSignature(ti, owner, &type, NULL);
        (*ti)->GetMethodName(ti, frames[i].method, &method, NULL, NULL);
        fprintf(report, "ALLOC_FRAME\t%d\t%.2048s\t%.1024s\t%lld\n", id,
                type ? type : "?", method ? method : "?", (long long)frames[i].location);
        if (type) (*ti)->Deallocate(ti, (unsigned char *)type);
        if (method) (*ti)->Deallocate(ti, (unsigned char *)method);
        if (owner) (*jni)->DeleteLocalRef(jni, owner);
    }
    fflush(report); funlockfile(report);
}

/** Largest individual arrays in the current snapshot: distinguishes a few huge maps from many small ones. */
#define LARGE_SLOTS 12
static struct { jlong length; size_t cls; } largest[LARGE_SLOTS];

static void note_length(jlong length, size_t cls) {
    if (length <= largest[LARGE_SLOTS-1].length) return;
    int slot = LARGE_SLOTS-1;
    while (slot > 0 && largest[slot-1].length < length) {
        largest[slot] = largest[slot-1];
        slot--;
    }
    largest[slot].length = length;
    largest[slot].cls = cls;
}

static jint JNICALL visit(jlong class_tag, jlong size, jlong *tag, jint length, void *data) {
    (void)tag; (void)data;
    size_t i = class_tag > 0 && class_tag <= CLASS_LIMIT ? (size_t)class_tag : 0;
    buckets[i].count++;
    buckets[i].bytes += size;
    if (length > 0) { buckets[i].elements += length; note_length(length, i); }
    return JVMTI_VISIT_OBJECTS;
}

static void clear_buckets(jvmtiEnv *ti) {
    memset(largest, 0, sizeof(largest));
    for (size_t i = 0; i <= CLASS_LIMIT; i++) {
        if (buckets[i].name) (*ti)->Deallocate(ti, (unsigned char *)buckets[i].name);
        buckets[i].name = NULL;
        buckets[i].count = 0; buckets[i].bytes = 0; buckets[i].elements = 0;
    }
}

/** Tag loaded classes and take one shallow census written as a labelled block. */
static void take_snapshot(jvmtiEnv *ti, JNIEnv *jni, const char *label) {
    clear_buckets(ti);
    jint classes = 0; jclass *loaded = NULL;
    jvmtiError error = (*ti)->GetLoadedClasses(ti, &classes, &loaded);
    jint tagging_errors = 0;
    if (error == JVMTI_ERROR_NONE && classes > CLASS_LIMIT) error = JVMTI_ERROR_ILLEGAL_ARGUMENT;
    if (error == JVMTI_ERROR_NONE) {
        for (jint i = 0; i < classes; i++) {
            (*ti)->GetClassSignature(ti, loaded[i], &buckets[i+1].name, NULL);
            if ((*ti)->SetTag(ti, loaded[i], i+1) != JVMTI_ERROR_NONE) tagging_errors++;
            (*jni)->DeleteLocalRef(jni, loaded[i]);
        }
        (*ti)->Deallocate(ti, (unsigned char *)loaded);
        jvmtiHeapCallbacks callbacks; memset(&callbacks, 0, sizeof(callbacks));
        callbacks.heap_iteration_callback = visit;
        error = (*ti)->IterateThroughHeap(ti, 0, NULL, &callbacks, NULL);
    }
    flockfile(report);
    fprintf(report, "SNAPSHOT_BEGIN\t%s\t%lld\n", label, now_millis());
    fprintf(report, "SNAPSHOT_STATUS\t%s\t%d\t%d\t%d\n", label, error, tagging_errors, classes);
    for (jint i = 0; i <= classes && i <= CLASS_LIMIT; i++) {
        if (buckets[i].count) fprintf(report, "SNAPSHOT_CLASS\t%s\t%s\t%lld\t%lld\t%lld\n", label,
            buckets[i].name ? buckets[i].name : "<unknown>", (long long)buckets[i].count,
            (long long)buckets[i].bytes, (long long)buckets[i].elements);
    }
    for (int slot = 0; slot < LARGE_SLOTS; slot++) {
        if (largest[slot].length <= 0) break;
        fprintf(report, "SNAPSHOT_LARGE\t%s\t%s\t%lld\n", label,
                buckets[largest[slot].cls].name ? buckets[largest[slot].cls].name : "<unknown>",
                (long long)largest[slot].length);
    }
    fprintf(report, "SNAPSHOT_END\t%s\n", label);
    fflush(report); funlockfile(report);
}

static void run_snapshots(jvmtiEnv *ti, JNIEnv *jni) {
    int offsets[SNAPSHOT_MAX_OFFSETS]; int count = 0;
    const char *cursor = snapshot_spec;
    while (*cursor && count < SNAPSHOT_MAX_OFFSETS) {
        char *end = NULL;
        long value = strtol(cursor, &end, 10);
        if (end == cursor) break;
        if (value > 0 && value <= 3600) offsets[count++] = (int)value;
        cursor = (*end == ',') ? end + 1 : end;
    }
    if (!count) return;
    struct timespec start; clock_gettime(CLOCK_MONOTONIC, &start);
    for (int i = 0; i < count; i++) {
        for (;;) {
            struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
            double elapsed = (double)(now.tv_sec - start.tv_sec) + (double)(now.tv_nsec - start.tv_nsec) / 1e9;
            if (elapsed >= (double)offsets[i]) break;
            struct timespec pause = {0, 50 * 1000 * 1000};
            nanosleep(&pause, NULL);
        }
        char label[24];
        snprintf(label, sizeof(label), "T%d", offsets[i]);
        take_snapshot(ti, jni, label);
    }
}

static jvmtiEnv *global_ti;
static JavaVM *global_vm;

/** Body of the detached snapshot thread: attach as a daemon so the VM can still exit. */
static void *snapshot_thread(void *unused) {
    (void)unused;
    JNIEnv *env = NULL;
    if ((*global_vm)->AttachCurrentThreadAsDaemon(global_vm, (void **)&env, NULL) != JNI_OK || env == NULL) {
        flockfile(report);
        fprintf(report, "SNAPSHOT_STATUS\tattach\t%d\t0\t0\n", JVMTI_ERROR_INTERNAL);
        fflush(report); funlockfile(report);
        return NULL;
    }
    run_snapshots(global_ti, env);
    (*global_vm)->DetachCurrentThread(global_vm);
    return NULL;
}

/** RunAgentThread needs a thread argument in JDK 25, so the snapshot thread is a plain pthread. */
static void JNICALL vm_init(jvmtiEnv *ti, JNIEnv *jni, jthread thread) {
    (void)thread;
    if (!snapshot_spec[0]) return;
    global_ti = ti;
    if ((*jni)->GetJavaVM(jni, &global_vm) != JNI_OK) return;
    pthread_t handle;
    if (pthread_create(&handle, NULL, snapshot_thread, NULL) == 0) {
        pthread_detach(handle);
    } else {
        flockfile(report);
        fprintf(report, "SNAPSHOT_STATUS\tpthread\t%d\t0\t0\n", JVMTI_ERROR_INTERNAL);
        fflush(report); funlockfile(report);
    }
}

static void JNICALL exhausted(jvmtiEnv *ti, JNIEnv *jni, jint flags,
                             const void *reserved, const char *description) {
    (void)reserved;
    if (!(flags & JVMTI_RESOURCE_EXHAUSTED_JAVA_HEAP) || atomic_exchange(&reported, 1)) return;
    fprintf(report, "OOM\t%d\t%s\n", flags, description ? description : "unknown");
    jthread thread = NULL;
    jvmtiFrameInfo frames[64]; jint depth = 0;
    jvmtiError error = (*ti)->GetCurrentThread(ti, &thread);
    if (error == JVMTI_ERROR_NONE) error = (*ti)->GetStackTrace(ti, thread, 0, 64, frames, &depth);
    fprintf(report, "STACK_STATUS\t%d\t%d\n", error, depth);
    for (jint i = 0; error == JVMTI_ERROR_NONE && i < depth; i++) {
        jclass owner = NULL; char *klass = NULL, *method = NULL, *signature = NULL;
        (*ti)->GetMethodDeclaringClass(ti, frames[i].method, &owner);
        if (owner) (*ti)->GetClassSignature(ti, owner, &klass, NULL);
        (*ti)->GetMethodName(ti, frames[i].method, &method, &signature, NULL);
        fprintf(report, "FRAME\t%s\t%s\t%s\t%lld\n", klass ? klass : "?", method ? method : "?",
                signature ? signature : "?", (long long)frames[i].location);
        if (klass) (*ti)->Deallocate(ti, (unsigned char *)klass);
        if (method) (*ti)->Deallocate(ti, (unsigned char *)method);
        if (signature) (*ti)->Deallocate(ti, (unsigned char *)signature);
        if (owner) (*jni)->DeleteLocalRef(jni, owner);
    }
    if (thread) (*jni)->DeleteLocalRef(jni, thread);
    fflush(report);

    jint classes = 0; jclass *loaded = NULL;
    error = (*ti)->GetLoadedClasses(ti, &classes, &loaded);
    fprintf(report, "CLASSES_STATUS\t%d\t%d\n", error, classes);
    if (error != JVMTI_ERROR_NONE || classes > CLASS_LIMIT) { fflush(report); return; }
    jint tagging_errors = 0;
    for (jint i = 0; i < classes; i++) {
        (*ti)->GetClassSignature(ti, loaded[i], &buckets[i+1].name, NULL);
        if ((*ti)->SetTag(ti, loaded[i], i+1) != JVMTI_ERROR_NONE) tagging_errors++;
        (*jni)->DeleteLocalRef(jni, loaded[i]);
    }
    (*ti)->Deallocate(ti, (unsigned char *)loaded);
    jvmtiHeapCallbacks callbacks; memset(&callbacks, 0, sizeof(callbacks));
    callbacks.heap_iteration_callback = visit;
    error = (*ti)->IterateThroughHeap(ti, 0, NULL, &callbacks, NULL);
    fprintf(report, "ITERATION_STATUS\t%d\t%d\n", error, tagging_errors);
    for (jint i = 0; i <= classes; i++) {
        if (buckets[i].count) fprintf(report, "CLASS\t%s\t%lld\t%lld\t%lld\n",
            buckets[i].name ? buckets[i].name : "<unknown>", (long long)buckets[i].count,
            (long long)buckets[i].bytes, (long long)buckets[i].elements);
        if (buckets[i].name) (*ti)->Deallocate(ti, (unsigned char *)buckets[i].name);
    }
    fprintf(report, "CENSUS_END\n"); fflush(report);
}

/*
 * Scheduled snapshots reuse the buckets array but free names first, so a snapshot followed by the
 * OOM census (or the reverse) never double-frees: clear_buckets() nulls every name it frees and the
 * OOM path always stores fresh signatures it obtained itself.
 */
JNIEXPORT jint JNICALL Agent_OnLoad(JavaVM *vm, char *options, void *reserved) {
    (void)reserved;
    if (!options || options[0] != '/') return JNI_ERR;
    buckets = calloc(CLASS_LIMIT+1, sizeof(Bucket));
    if (!buckets) return JNI_ERR;
    report = fopen(options, "wx");
    if (!report) return JNI_ERR;
    jvmtiEnv *ti = NULL;
    if ((*vm)->GetEnv(vm, (void **)&ti, JVMTI_VERSION_1_2) != JNI_OK) return JNI_ERR;
    jvmtiCapabilities capabilities; memset(&capabilities, 0, sizeof(capabilities));
    capabilities.can_tag_objects = 1;
    capabilities.can_generate_resource_exhaustion_heap_events = 1;
    capabilities.can_generate_sampled_object_alloc_events = 1;
    jvmtiEventCallbacks callbacks; memset(&callbacks, 0, sizeof(callbacks));
    callbacks.ResourceExhausted = exhausted;
    callbacks.SampledObjectAlloc = sampled;
    callbacks.VMInit = vm_init;
    char *spec = NULL;
    if ((*ti)->GetSystemProperty(ti, "fabricaot.census.at", &spec) == JVMTI_ERROR_NONE && spec) {
        snprintf(snapshot_spec, sizeof(snapshot_spec), "%s", spec);
        (*ti)->Deallocate(ti, (unsigned char *)spec);
        if ((*ti)->SetEventNotificationMode(ti, JVMTI_ENABLE, JVMTI_EVENT_VM_INIT, NULL) != JVMTI_ERROR_NONE) {
            snapshot_spec[0] = '\0';
            fprintf(report, "SNAPSHOT_STATUS\tconfig\t%d\t0\t0\n", JVMTI_ERROR_INTERNAL);
            fflush(report);
        }
    }
    if ((*ti)->AddCapabilities(ti, &capabilities) != JVMTI_ERROR_NONE ||
        (*ti)->SetEventCallbacks(ti, &callbacks, sizeof(callbacks)) != JVMTI_ERROR_NONE ||
        (*ti)->SetEventNotificationMode(ti, JVMTI_ENABLE, JVMTI_EVENT_RESOURCE_EXHAUSTED, NULL) != JVMTI_ERROR_NONE ||
        (*ti)->SetHeapSamplingInterval(ti, 16*1024*1024) != JVMTI_ERROR_NONE ||
        (*ti)->SetEventNotificationMode(ti, JVMTI_ENABLE, JVMTI_EVENT_SAMPLED_OBJECT_ALLOC, NULL) != JVMTI_ERROR_NONE)
        return JNI_ERR;
    fprintf(report, "AGENT_READY\n"); fflush(report);
    return JNI_OK;
}
