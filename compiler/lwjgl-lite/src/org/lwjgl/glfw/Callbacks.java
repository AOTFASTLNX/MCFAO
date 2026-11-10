package org.lwjgl.glfw;
import org.lwjgl.system.Callback;
import static org.lwjgl.glfw.GLFW.*;
/** Releases only callback ABIs implemented by GLFW-lite. No calls through optional null entries. */
public final class Callbacks {
    private Callbacks(){}
    public static void glfwFreeCallbacks(long window){
        Callback[] callbacks={glfwSetWindowPosCallback(window,null),glfwSetWindowSizeCallback(window,null),
            glfwSetFramebufferSizeCallback(window,null),glfwSetWindowCloseCallback(window,null),
            glfwSetWindowFocusCallback(window,null),glfwSetWindowIconifyCallback(window,null),
            glfwSetCursorEnterCallback(window,null),glfwSetKeyCallback(window,null),
            glfwSetCharCallback(window,null),glfwSetMouseButtonCallback(window,null),
            glfwSetCursorPosCallback(window,null),glfwSetScrollCallback(window,null),
            glfwSetDropCallback(window,null),glfwSetIMEStatusCallback(window,null),glfwSetPreeditCallback(window,null)};
        for(Callback callback:callbacks)if(callback!=null)callback.free();
    }
}
