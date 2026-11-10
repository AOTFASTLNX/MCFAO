package fabricaot.graphics;
import java.util.OptionalInt;
import com.mojang.blaze3d.*;
import com.mojang.blaze3d.platform.*;
import com.mojang.blaze3d.shaders.*;
import com.mojang.blaze3d.systems.*;
import static org.lwjgl.glfw.GLFW.*;

/** Executes the actual 26.1.2 Window constructor. Host surface is explicitly a test adapter. */
public final class WindowProbe {
    public static final class WindowOnlyBackend implements GpuBackend {
        public String getName(){return "iOS WindowProbe (NO RENDERER)";}
        public void setWindowHints(){glfwWindowHint(GLFW_CLIENT_API,GLFW_NO_API);}
        public void handleWindowCreationErrors(GLFWErrorCapture.Error error)throws BackendCreationException{
            if(error!=null)throw new BackendCreationException("GLFW-lite window creation failed: "+error);
        }
        public GpuDevice createDevice(long handle,ShaderSource source,GpuDebugOptions options){throw new UnsupportedOperationException("Window probe has no renderer");}
    }
    public static void main(String[] args)throws Exception{
        RenderSystem.initRenderThread();
        GLX._initGlfw(new BackendOptions(false));
        Window window=new Window(new WindowEventHandler(){public void resizeGui(){}public void cursorEntered(){}},
            new DisplayData(390,844,OptionalInt.empty(),OptionalInt.empty(),false),null,"26.1.2 WindowProbe",new WindowOnlyBackend());
        if(window.handle()==0||window.getWidth()<=0||window.getHeight()<=0)throw new AssertionError("Window dimensions/handle");
        glfwPollEvents();
        System.out.println("MINECRAFT_WINDOW_CONSTRUCTED platform="+Window.getPlatform()+" framebuffer="+window.getWidth()+"x"+window.getHeight());
        window.close();
        System.out.println("MINECRAFT_WINDOW_PROBE_PASS renderer=NOT_INITIALIZED surface="+glfwGetVersionString());
    }
}
