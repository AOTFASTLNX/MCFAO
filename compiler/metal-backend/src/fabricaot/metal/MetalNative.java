package fabricaot.metal;
import java.nio.file.Path;
final class MetalNative {
    static {System.load(Path.of(System.getProperty("org.lwjgl.librarypath"),"libfaot_metal.dylib").toAbsolutePath().toString());}
    static native long create(long window);
    static native String deviceName(long context);
    static native long createBuffer(long context,long bytes);
    static native long bufferAddress(long buffer);
    static native long createSampler(long context,boolean repeatU,boolean repeatV,boolean linearMin,boolean linearMag,int anisotropy,double maxLod);
    static native long createTexture(long context,int format,int usage,int width,int height,int layers,int mips);
    static native long createTextureView(long texture,int baseMip,int mips);
    static native void clearTextures(long context,long color,int argb,long depth,double depthValue);
    static native void writeTexture(long context,long texture,int mip,int layer,int x,int y,int width,int height,long source,int rowStride,int components);
    static native void readTexture(long context,long texture,int mip,int x,int y,int width,int height,long buffer,long offset);
    static native void copyTexture(long context,long source,long destination,int mip,int sourceX,int sourceY,int destX,int destY,int width,int height);
    static native void beginPass(long context,long color,boolean clearColor,int argb,long depth,boolean clearDepth,double depthValue);
    static native void endPass(long context);
    static native void debugGroup(long context,String name,boolean push);
    static native long createPipeline(long context,String shaderKey,int[] attributes,int stride,int[] state,float depthBiasScale,float depthBiasConstant);
    static native void setPipeline(long context,long pipeline);
    static native void bindUniform(long context,int stage,int index,long buffer,long offset,long length);
    static native void bindTexture(long context,int stage,int index,int samplerIndex,long view,long sampler);
    static native void bindTexelBuffer(long context,int stage,int index,int format,long buffer,long offset,long length);
    static native void vertexBuffer(long context,long buffer);
    static native void scissor(long context,boolean enabled,int x,int y,int width,int height);
    static native void draw(long context,long pipeline,int first,int count);
    static native void drawIndexed(long context,long pipeline,long indices,int indexType,int firstIndex,int count,int baseVertex,int instances);
    static native void synchronize(long context);
    static native void clearRectangle(long context,long color,int argb,long depth,double value,int x,int y,int width,int height);
    static native long createFence(long context);
    static native boolean awaitFence(long fence,long timeoutNanos);
    static native void presentTexture(long context,long view);
    static native void presentFrame(long context);
    static native void setDisplaySync(long context, boolean enabled);
    static native void clearDiagnosticFrame(long context,float r,float g,float b,float a);
    static native void release(long object);
}
