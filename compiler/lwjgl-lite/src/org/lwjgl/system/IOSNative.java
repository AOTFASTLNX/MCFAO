package org.lwjgl.system;
/** Fixed, signed JNI entry points. There is no arbitrary executable allocation API. */
final class IOSNative {
    static native long open(String path);
    static native String error();
    static native long symbol(long handle,long utf8Name);
    static native void close(long handle);
    static native long callbackCreate(Object instance,int kind);
    static native void callbackFree(long address);
    static native Object callbackGet(long address);
}
