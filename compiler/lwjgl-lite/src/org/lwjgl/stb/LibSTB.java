package org.lwjgl.stb;
import org.lwjgl.system.Library;

/** Image JNI is linked into the signed core library with the same system allocator. */
final class LibSTB {
    static { Library.initialize(); }
    private LibSTB() {}
    static void initialize() {}
}
