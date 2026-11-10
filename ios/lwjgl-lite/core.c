#include <jni.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

#define JLONG(p) ((jlong)(uintptr_t)(p))
#define PTR(p) ((void *)(uintptr_t)(p))
static void *aligned(size_t alignment,size_t size){void *p=NULL;if(alignment<sizeof(void *)||(alignment&(alignment-1)))return NULL;return posix_memalign(&p,alignment,size)?NULL:p;}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_IOSNative_open(JNIEnv *e,jclass c,jstring path){(void)c;const char *s=(*e)->GetStringUTFChars(e,path,NULL);if(!s)return 0;void *h=dlopen(s,RTLD_NOW|RTLD_LOCAL);(*e)->ReleaseStringUTFChars(e,path,s);return JLONG(h);}
JNIEXPORT jstring JNICALL Java_org_lwjgl_system_IOSNative_error(JNIEnv *e,jclass c){(void)c;const char *s=dlerror();return (*e)->NewStringUTF(e,s?s:"unknown loader error");}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_IOSNative_symbol(JNIEnv *e,jclass c,jlong h,jlong name){(void)e;(void)c;return h&&name?JLONG(dlsym(PTR(h),PTR(name))):0;}
JNIEXPORT void JNICALL Java_org_lwjgl_system_IOSNative_close(JNIEnv *e,jclass c,jlong h){(void)e;(void)c;if(h)dlclose(PTR(h));}
JNIEXPORT jint JNICALL Java_org_lwjgl_system_MemoryAccessJNI_getPointerSize(JNIEnv *e,jclass c){(void)e;(void)c;return sizeof(void *);}
#define ADDRESS(Name,Function) JNIEXPORT jlong JNICALL Java_org_lwjgl_system_MemoryAccessJNI_##Name(JNIEnv *e,jclass c){(void)e;(void)c;return JLONG(Function);}
ADDRESS(malloc,malloc) ADDRESS(calloc,calloc) ADDRESS(realloc,realloc) ADDRESS(free,free)
ADDRESS(aligned_1alloc,aligned) ADDRESS(aligned_1free,free)
#define ACCESS(Name,Type,JType) \
JNIEXPORT JType JNICALL Java_org_lwjgl_system_MemoryAccessJNI_nget##Name(JNIEnv *e,jclass c,jlong p){(void)e;(void)c;Type v;memcpy(&v,PTR(p),sizeof v);return (JType)v;} \
JNIEXPORT void JNICALL Java_org_lwjgl_system_MemoryAccessJNI_nput##Name(JNIEnv *e,jclass c,jlong p,JType value){(void)e;(void)c;Type v=(Type)value;memcpy(PTR(p),&v,sizeof v);}
ACCESS(Byte,int8_t,jbyte) ACCESS(Short,int16_t,jshort) ACCESS(Int,int32_t,jint)
ACCESS(Long,int64_t,jlong) ACCESS(Float,float,jfloat) ACCESS(Double,double,jdouble) ACCESS(Address,uintptr_t,jlong)
JNIEXPORT jobject JNICALL Java_org_lwjgl_system_MemoryUtil_memGlobalRefToObject(JNIEnv *e,jclass c,jlong p){(void)c;return (*e)->NewLocalRef(e,(jobject)PTR(p));}
JNIEXPORT jobject JNICALL Java_org_lwjgl_system_jni_JNINativeInterface_nNewDirectByteBuffer(JNIEnv *e,jclass c,jlong p,jlong capacity){(void)c;return (*e)->NewDirectByteBuffer(e,PTR(p),capacity);}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_jni_JNINativeInterface_GetDirectBufferAddress(JNIEnv *e,jclass c,jobject buffer){(void)c;return JLONG((*e)->GetDirectBufferAddress(e,buffer));}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_jni_JNINativeInterface_GetDirectBufferCapacity(JNIEnv *e,jclass c,jobject buffer){(void)c;return (*e)->GetDirectBufferCapacity(e,buffer);}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_jni_JNINativeInterface_NewGlobalRef(JNIEnv *e,jclass c,jobject o){(void)c;return JLONG((*e)->NewGlobalRef(e,o));}
JNIEXPORT void JNICALL Java_org_lwjgl_system_jni_JNINativeInterface_nDeleteGlobalRef(JNIEnv *e,jclass c,jlong p){(void)c;(*e)->DeleteGlobalRef(e,(jobject)PTR(p));}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_libc_LibCStdlib_nmalloc(JNIEnv *e,jclass c,jlong n){(void)e;(void)c;return JLONG(malloc((size_t)n));}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_libc_LibCStdlib_ncalloc(JNIEnv *e,jclass c,jlong n,jlong s){(void)e;(void)c;return JLONG(calloc((size_t)n,(size_t)s));}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_libc_LibCStdlib_nrealloc(JNIEnv *e,jclass c,jlong p,jlong n){(void)e;(void)c;return JLONG(realloc(PTR(p),(size_t)n));}
JNIEXPORT void JNICALL Java_org_lwjgl_system_libc_LibCStdlib_nfree(JNIEnv *e,jclass c,jlong p){(void)e;(void)c;free(PTR(p));}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_libc_LibCStdlib_naligned_1alloc(JNIEnv *e,jclass c,jlong a,jlong n){(void)e;(void)c;return JLONG(aligned((size_t)a,(size_t)n));}
JNIEXPORT void JNICALL Java_org_lwjgl_system_libc_LibCStdlib_naligned_1free(JNIEnv *e,jclass c,jlong p){(void)e;(void)c;free(PTR(p));}
/* These names are overloaded with Java arrays. Long JNI names prevent an array from being
   accidentally treated as a native pointer by the short-name resolver. */
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_libc_LibCString_nmemset__JIJ(JNIEnv *e,jclass c,jlong p,jint value,jlong size){(void)e;(void)c;return JLONG(memset(PTR(p),value,(size_t)size));}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_libc_LibCString_nmemcpy__JJJ(JNIEnv *e,jclass c,jlong dst,jlong src,jlong size){(void)e;(void)c;return JLONG(memcpy(PTR(dst),PTR(src),(size_t)size));}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_libc_LibCString_nmemmove__JJJ(JNIEnv *e,jclass c,jlong dst,jlong src,jlong size){(void)e;(void)c;return JLONG(memmove(PTR(dst),PTR(src),(size_t)size));}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_libc_LibCString_nstrlen(JNIEnv *e,jclass c,jlong p){(void)e;(void)c;return (jlong)strlen(PTR(p));}
JNIEXPORT jlong JNICALL Java_org_lwjgl_system_libc_LibCString_nstrerror(JNIEnv *e,jclass c,jint code){(void)e;(void)c;return JLONG(strerror(code));}
