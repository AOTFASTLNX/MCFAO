/* Matching LWJGL 3.4.1 STB headers, checksum-locked in compiler/stb.lock.json.
   Memory-only image APIs; callbacks use the precompiled bank in this same library. */
#include <jni.h>
#include <stdint.h>
#include <stddef.h>
#include <limits.h>
#define STBI_NO_STDIO
#define STBI_MAX_DIMENSIONS 16384
#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"
#define STBI_WRITE_NO_STDIO
#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"
#define STB_IMAGE_RESIZE_IMPLEMENTATION
#include "stb_image_resize2.h"

#define ADDRESS(p) ((jlong)(uintptr_t)(p))
#define POINTER(p) ((void *)(uintptr_t)(p))
#define IMAGE_BUDGET (256ULL*1024*1024)
static void invalid(JNIEnv *e,const char *message){jclass c=(*e)->FindClass(e,"java/lang/IllegalArgumentException");if(c)(*e)->ThrowNew(e,c,message);}
static int layout_valid(int w,int h,int components,int stride){
    if(w<=0||h<=0||w>16384||h>16384||components<1||components>4||stride<0)return 0;
    uint64_t row=(uint64_t)w*components;
    if(stride && (uint64_t)stride<row)return 0;
    return (uint64_t)(h-1)*(stride?(uint64_t)stride:row)+row<=IMAGE_BUDGET;
}
JNIEXPORT jlong JNICALL Java_org_lwjgl_stb_STBImage_nstbi_1load_1from_1memory__JIJJJI(JNIEnv *e,jclass cls,jlong input,jint length,jlong x,jlong y,jlong channels,jint desired){
    (void)cls;int w,h,n;
    if(!input||length<=0||!x||!y||!channels||desired<0||desired>4){invalid(e,"Invalid memory image decode arguments");return 0;}
    if(!stbi_info_from_memory(POINTER(input),length,&w,&h,&n))return 0;
    if(!layout_valid(w,h,desired?desired:n,0)){invalid(e,"Decoded image exceeds the 256 MiB / 16384 pixel research limits");return 0;}
    return ADDRESS(stbi_load_from_memory(POINTER(input),length,POINTER(x),POINTER(y),POINTER(channels),desired));
}
JNIEXPORT jlong JNICALL Java_org_lwjgl_stb_STBImage_nstbi_1failure_1reason(JNIEnv *e,jclass cls){(void)e;(void)cls;return ADDRESS(stbi_failure_reason());}
JNIEXPORT void JNICALL Java_org_lwjgl_stb_STBImage_nstbi_1image_1free(JNIEnv *e,jclass cls,jlong data){(void)e;(void)cls;stbi_image_free(POINTER(data));}
JNIEXPORT jlong JNICALL Java_org_lwjgl_stb_STBImageResize_nstbir_1resize_1uint8_1linear(JNIEnv *e,jclass cls,jlong input,jint iw,jint ih,jint istride,jlong output,jint ow,jint oh,jint ostride,jint layout){
    (void)cls;
    /* NativeImage passes its component count, i.e. layouts 1..4. Other STB layouts remain unsupported. */
    if(!input||!output||!layout_valid(iw,ih,layout,istride)||!layout_valid(ow,oh,layout,ostride)){
        invalid(e,"Unsupported image resize layout or size (components 1..4, preallocated output required)");return 0;
    }
    return ADDRESS(stbir_resize_uint8_linear(POINTER(input),iw,ih,istride,POINTER(output),ow,oh,ostride,(stbir_pixel_layout)layout));
}
JNIEXPORT jint JNICALL Java_org_lwjgl_stb_STBImageWrite_nstbi_1write_1png_1to_1func(JNIEnv *e,jclass cls,jlong function,jlong user,jint width,jint height,jint components,jlong data,jint stride){
    (void)cls;
    if(!function||!data||!layout_valid(width,height,components,stride)){invalid(e,"Invalid PNG callback, pixel layout or size");return 0;}
    return stbi_write_png_to_func((stbi_write_func *)(uintptr_t)function,POINTER(user),width,height,components,POINTER(data),stride);
}
#define GLOBAL(Suffix,Name) JNIEXPORT jlong JNICALL Java_org_lwjgl_stb_STBImageWrite_n##Suffix(JNIEnv *e,jclass cls){(void)e;(void)cls;return ADDRESS(&Name);}
GLOBAL(stbi_1write_1png_1compression_1level,stbi_write_png_compression_level)
GLOBAL(stbi_1write_1force_1png_1filter,stbi_write_force_png_filter)
GLOBAL(stbi_1zlib_1compress,stbi_zlib_compress)
GLOBAL(stbi_1write_1tga_1with_1rle,stbi_write_tga_with_rle)
