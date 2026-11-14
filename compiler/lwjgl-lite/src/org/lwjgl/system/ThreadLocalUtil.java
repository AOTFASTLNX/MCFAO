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
        // This build resolves every GL entry through the explicit pointer buffer passed to JNI;
        // there is no VM JNIEnv table to rebase per thread. Keeping the address is unnecessary.
        if(address<0)throw new IllegalArgumentException("negative capability address");
    }
    public static void setFunctionMissingAddresses(int count){
        /* The generated static JNI adapters validate their explicit pointer argument before
           every call, so this bookkeeping count is not used. */
        if(count<0)throw new IllegalArgumentException("negative function count");
    }
}
