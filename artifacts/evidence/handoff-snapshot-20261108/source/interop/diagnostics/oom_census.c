/* First-party, Mac build-JVM diagnostic only. No class transformation or allocation values. */
#include <jni.h>
#include <jvmti.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CLASS_LIMIT 131072
typedef struct { jlong count, bytes, elements; char *name; } Bucket;
static Bucket *buckets;
static FILE *report;
static atomic_int reported;
static atomic_int samples;

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

static jint JNICALL visit(jlong class_tag, jlong size, jlong *tag, jint length, void *data) {
    (void)tag; (void)data;
    size_t i = class_tag > 0 && class_tag <= CLASS_LIMIT ? (size_t)class_tag : 0;
    buckets[i].count++;
    buckets[i].bytes += size;
    if (length > 0) buckets[i].elements += length;
    return JVMTI_VISIT_OBJECTS;
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
    if ((*ti)->AddCapabilities(ti, &capabilities) != JVMTI_ERROR_NONE ||
        (*ti)->SetEventCallbacks(ti, &callbacks, sizeof(callbacks)) != JVMTI_ERROR_NONE ||
        (*ti)->SetEventNotificationMode(ti, JVMTI_ENABLE, JVMTI_EVENT_RESOURCE_EXHAUSTED, NULL) != JVMTI_ERROR_NONE ||
        (*ti)->SetHeapSamplingInterval(ti, 16*1024*1024) != JVMTI_ERROR_NONE ||
        (*ti)->SetEventNotificationMode(ti, JVMTI_ENABLE, JVMTI_EVENT_SAMPLED_OBJECT_ALLOC, NULL) != JVMTI_ERROR_NONE)
        return JNI_ERR;
    fprintf(report, "AGENT_READY\n"); fflush(report);
    return JNI_OK;
}
