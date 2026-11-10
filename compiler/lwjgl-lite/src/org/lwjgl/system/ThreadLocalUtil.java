package org.lwjgl.system;
import org.lwjgl.PointerBuffer;
import java.util.Objects;

/** Explicit function-pointer JNI dispatch does not patch the VM's JNIEnv function table. */
public final class ThreadLocalUtil {
    private ThreadLocalUtil(){}
    public static PointerBuffer setupAddressBuffer(PointerBuffer addresses){
        // Keep missing symbols at zero; every precompiled JNI adapter checks before calling.
        return Objects.requireNonNull(addresses);
    }
    public static boolean areCapabilitiesDifferent(PointerBuffer first,PointerBuffer second){
        if(first.remaining()!=second.remaining())return true;
        for(int i=0;i<first.remaining();i++){
            long incoming=second.get(i);
            if(incoming!=0&&first.get(i)!=incoming)return true;
        }
        return false;
    }
    public static void setCapabilities(long address){
        if(address!=0)throw new UnsupportedOperationException("JNI thread-table dispatch is unavailable; explicit function pointers are required");
    }
    public static void setFunctionMissingAddresses(int count){
        if(count!=0)throw new UnsupportedOperationException("JNI thread-table dispatch is unavailable; missing explicit pointers fail in the static adapter");
    }
}
