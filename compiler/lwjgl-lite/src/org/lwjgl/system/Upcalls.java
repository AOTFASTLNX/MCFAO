package org.lwjgl.system;
import org.lwjgl.glfw.*;
import org.lwjgl.stb.STBIWriteCallbackI;

/** Bounded precompiled callback bank. Unknown callback ABIs are rejected by name. */
final class Upcalls {
    static long upcallCreate(Callback.Descriptor descriptor,Object instance){
        Library.initialize();
        int kind;
        if(instance instanceof GLFWErrorCallbackI)kind=0;
        else if(instance instanceof GLFWMonitorCallbackI)kind=1;
        else if(instance instanceof GLFWWindowPosCallbackI)kind=2;
        else if(instance instanceof GLFWWindowSizeCallbackI)kind=3;
        else if(instance instanceof GLFWFramebufferSizeCallbackI)kind=4;
        else if(instance instanceof GLFWWindowCloseCallbackI)kind=5;
        else if(instance instanceof GLFWWindowFocusCallbackI)kind=6;
        else if(instance instanceof GLFWWindowIconifyCallbackI)kind=7;
        else if(instance instanceof GLFWCursorEnterCallbackI)kind=8;
        else if(instance instanceof GLFWKeyCallbackI)kind=9;
        else if(instance instanceof GLFWCharCallbackI)kind=10;
        else if(instance instanceof GLFWMouseButtonCallbackI)kind=11;
        else if(instance instanceof GLFWCursorPosCallbackI)kind=12;
        else if(instance instanceof GLFWScrollCallbackI)kind=13;
        else if(instance instanceof GLFWDropCallbackI)kind=14;
        else if(instance instanceof GLFWIMEStatusCallbackI)kind=15;
        else if(instance instanceof GLFWPreeditCallbackI)kind=16;
        else if(instance instanceof STBIWriteCallbackI)kind=17;
        else throw new UnsupportedOperationException("Unregistered iOS static callback ABI: "+instance.getClass().getName());
        return IOSNative.callbackCreate(instance,kind);
    }
    @SuppressWarnings("unchecked") static <T extends CallbackI> T upcallGet(long address){return (T)IOSNative.callbackGet(address);}
    static void upcallFree(long address){IOSNative.callbackFree(address);}
}
