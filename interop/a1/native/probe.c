#include <jni.h>

JNIEXPORT jint JNICALL Java_fabricaot_probe_A1Probe_add(
    JNIEnv *env, jclass type, jint a, jint b) {
    (void)env;
    (void)type;
    return a + b;
}

JNIEXPORT jstring JNICALL Java_fabricaot_probe_A1Probe_echo(
    JNIEnv *env, jclass type, jstring input) {
    (void)type;
    const char *text = (*env)->GetStringUTFChars(env, input, NULL);
    if (text == NULL) return NULL;
    jstring result = (*env)->NewStringUTF(env, text);
    (*env)->ReleaseStringUTFChars(env, input, text);
    return result;
}
