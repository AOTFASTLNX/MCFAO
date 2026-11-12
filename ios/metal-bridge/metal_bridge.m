#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#include <jni.h>
#import <objc/message.h>
#include <stdint.h>
#include <float.h>
#include <math.h>
#include <string.h>
#include <dispatch/dispatch.h>
#include "glfw_lite.h"
#include "texture_transfer.h"

@interface FAOTMetalContext : NSObject
@property(nonatomic,strong) id<MTLDevice> device;
@property(nonatomic,strong) id<MTLCommandQueue> queue;
@property(nonatomic,strong) id<MTLCommandQueue> texelUploadQueue;
@property(nonatomic,strong) CAMetalLayer *layer;
@property(nonatomic,strong) id<MTLCommandBuffer> pending;
@property(nonatomic,strong) id<MTLCommandBuffer> lastCommitted;
@property(nonatomic,strong) id<MTLRenderCommandEncoder> renderEncoder;
@property(nonatomic,strong) id<MTLTexture> activeColor;
@property(nonatomic,strong) id<MTLTexture> activeDepth;
@property(nonatomic) BOOL emptyScissor;
@property(nonatomic) BOOL presentationLogged;
@property(nonatomic,strong) id<MTLTexture> presentationSource;
@property(nonatomic,strong) id<MTLRenderPipelineState> presentationPipeline;
@property(nonatomic,strong) id<MTLLibrary> utilityLibrary;
@property(nonatomic,strong) NSMutableDictionary<NSNumber *,id<MTLRenderPipelineState>> *rectanglePipelines;
@property(nonatomic,strong) id<MTLDepthStencilState> rectangleDepth;
@end
@implementation FAOTMetalContext
@end
@interface FAOTMetalFence : NSObject
@property(nonatomic,strong) dispatch_group_t completion;
@property(atomic,strong) NSString *error;
@end
@implementation FAOTMetalFence
@end
static jlong keep(id object){return (jlong)(uintptr_t)(__bridge_retained void *)object;}
static FAOTMetalContext *context(jlong handle){return (__bridge FAOTMetalContext *)(void *)(uintptr_t)handle;}
static void failure(JNIEnv *env,const char *message){jclass c=(*env)->FindClass(env,"java/lang/IllegalStateException");if(c)(*env)->ThrowNew(env,c,message);}
static id<MTLTexture> texture(jlong handle){return (__bridge id<MTLTexture>)(void *)(uintptr_t)handle;}
static id<MTLBuffer> buffer(jlong handle){return (__bridge id<MTLBuffer>)(void *)(uintptr_t)handle;}
static id<MTLCommandBuffer> commands(FAOTMetalContext *ctx){if(!ctx.pending)ctx.pending=[ctx.queue commandBuffer];return ctx.pending;}
static id<MTLLibrary> utilityLibrary(JNIEnv *env, FAOTMetalContext *ctx) {
    if(!ctx.utilityLibrary){
        NSString *path=[NSBundle.mainBundle.privateFrameworksPath stringByAppendingPathComponent:@"fabricaot-present.metallib"];
        NSError *error=nil;
        ctx.utilityLibrary=[ctx.device newLibraryWithURL:[NSURL fileURLWithPath:path] error:&error];
        if(!ctx.utilityLibrary)failure(env,error.localizedDescription.UTF8String ?: "Metal utility library unavailable");
    }
    return ctx.utilityLibrary;
}
static BOOL outsidePass(JNIEnv *env,FAOTMetalContext *ctx){if(ctx.renderEncoder){failure(env,"Metal operation inside render pass");return NO;}return YES;}
static BOOL submitAndWait(JNIEnv *env,FAOTMetalContext *ctx){
    if(!outsidePass(env,ctx))return NO;
    if(ctx.pending){ctx.lastCommitted=ctx.pending;ctx.pending=nil;[ctx.lastCommitted commit];}
    if(ctx.lastCommitted){[ctx.lastCommitted waitUntilCompleted];if(ctx.lastCommitted.status==MTLCommandBufferStatusError){failure(env,ctx.lastCommitted.error.localizedDescription.UTF8String);return NO;}}
    return YES;
}
static NSUInteger pixelBytes(id<MTLTexture> value){switch(value.pixelFormat){case MTLPixelFormatRGBA8Unorm:case MTLPixelFormatDepth32Float:return 4;case MTLPixelFormatR8Unorm:case MTLPixelFormatR8Sint:return 1;default:return 0;}}
static MTLRenderPassDescriptor *attachments(JNIEnv *env,id<MTLTexture> color,BOOL clearColor,jint argb,id<MTLTexture> depth,BOOL clearDepth,double depthValue){
    if((color && color.textureType!=MTLTextureType2D)||(depth && depth.textureType!=MTLTextureType2D)) {failure(env,"Array/cubemap attachment rendering is not implemented");return nil;}
    if(color && color.pixelFormat!=MTLPixelFormatRGBA8Unorm && color.pixelFormat!=MTLPixelFormatR8Unorm){failure(env,"Unsupported color attachment format");return nil;}
    if(depth && depth.pixelFormat!=MTLPixelFormatDepth32Float){failure(env,"Expected DEPTH32 attachment");return nil;}
    if(color && depth && (color.width!=depth.width||color.height!=depth.height)){failure(env,"Metal attachment dimensions differ");return nil;}
    if(clearDepth && (!isfinite(depthValue)||depthValue<0||depthValue>1)){failure(env,"Depth clear must be finite and between zero and one");return nil;}
    MTLRenderPassDescriptor *pass=[MTLRenderPassDescriptor renderPassDescriptor];
    if(color){pass.colorAttachments[0].texture=color;pass.colorAttachments[0].loadAction=clearColor?MTLLoadActionClear:MTLLoadActionLoad;pass.colorAttachments[0].storeAction=MTLStoreActionStore;
        uint32_t c=(uint32_t)argb;pass.colorAttachments[0].clearColor=MTLClearColorMake(((c>>16)&255)/255.0,((c>>8)&255)/255.0,(c&255)/255.0,((c>>24)&255)/255.0);}
    if(depth){pass.depthAttachment.texture=depth;pass.depthAttachment.loadAction=clearDepth?MTLLoadActionClear:MTLLoadActionLoad;pass.depthAttachment.storeAction=MTLStoreActionStore;pass.depthAttachment.clearDepth=depthValue;}
    return pass;
}
JNIEXPORT jlong JNICALL Java_fabricaot_metal_MetalNative_create(JNIEnv *env,jclass cls,jlong window){
    (void)cls;
    @autoreleasepool {
        CAMetalLayer *layer=(__bridge CAMetalLayer *)faot_glfw_metal_layer((GLFWwindow *)(uintptr_t)window);
        if(!layer||!layer.device){failure(env,"Window has no CAMetalLayer/MTLDevice");return 0;}
        FAOTMetalContext *ctx=[FAOTMetalContext new];ctx.layer=layer;ctx.device=layer.device;ctx.queue=[ctx.device newCommandQueue];
        if(!ctx.queue){failure(env,"MTLCommandQueue allocation failed");return 0;}
        return keep(ctx);
    }
}
JNIEXPORT jstring JNICALL Java_fabricaot_metal_MetalNative_deviceName(JNIEnv *env,jclass cls,jlong handle){(void)cls;return (*env)->NewStringUTF(env,context(handle).device.name.UTF8String);}
JNIEXPORT jlong JNICALL Java_fabricaot_metal_MetalNative_createBuffer(JNIEnv *env,jclass cls,jlong handle,jlong bytes){
    (void)cls;
    @autoreleasepool {
        if(bytes<=0||bytes>256LL*1024*1024){failure(env,"Invalid Metal buffer length");return 0;}
        // Vanilla uniform writers stop at the last field (Fog uses 40 bytes), but Metal
        // validates the full struct size (48 bytes for Fog). Keep the Java size and slice
        // bounds intact, and round the backing allocation up for the shader's tail padding.
        NSUInteger length = ((NSUInteger)bytes + 15) & ~(NSUInteger)15;
        id<MTLBuffer> buffer=[context(handle).device newBufferWithLength:length options:MTLResourceStorageModeShared];
        if(!buffer){failure(env,"MTLBuffer allocation failed");return 0;}
        return keep(buffer);
    }
}
JNIEXPORT jlong JNICALL Java_fabricaot_metal_MetalNative_bufferAddress(JNIEnv *env,jclass cls,jlong handle){(void)env;(void)cls;id<MTLBuffer> buffer=(__bridge id<MTLBuffer>)(void *)(uintptr_t)handle;return (jlong)(uintptr_t)buffer.contents;}
JNIEXPORT jlong JNICALL Java_fabricaot_metal_MetalNative_createSampler(JNIEnv *env,jclass cls,jlong handle,jboolean u,jboolean v,jboolean min,jboolean mag,jint anisotropy,jdouble lod){
    (void)cls;
    @autoreleasepool {
        if(anisotropy<1||anisotropy>16||lod<0){failure(env,"Invalid Metal sampler descriptor");return 0;}
        MTLSamplerDescriptor *desc=[MTLSamplerDescriptor new];
        desc.sAddressMode=u?MTLSamplerAddressModeRepeat:MTLSamplerAddressModeClampToEdge;
        desc.tAddressMode=v?MTLSamplerAddressModeRepeat:MTLSamplerAddressModeClampToEdge;
        desc.minFilter=min?MTLSamplerMinMagFilterLinear:MTLSamplerMinMagFilterNearest;
        desc.magFilter=mag?MTLSamplerMinMagFilterLinear:MTLSamplerMinMagFilterNearest;
        desc.mipFilter=min?MTLSamplerMipFilterLinear:MTLSamplerMipFilterNearest;
        desc.maxAnisotropy=(NSUInteger)anisotropy;desc.lodMaxClamp=lod>FLT_MAX?FLT_MAX:(float)lod;
        id<MTLSamplerState> sampler=[context(handle).device newSamplerStateWithDescriptor:desc];
        if(!sampler){failure(env,"MTLSamplerState allocation failed");return 0;}
        return keep(sampler);
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_clearDiagnosticFrame(JNIEnv *env,jclass cls,jlong handle,jfloat r,jfloat g,jfloat b,jfloat a){
    (void)cls;
    @autoreleasepool {
        FAOTMetalContext *ctx=context(handle);
        id<CAMetalDrawable> drawable=[ctx.layer nextDrawable];
        if(!drawable){failure(env,"No Metal drawable available (background or zero-size surface)");return;}
        id<MTLTexture> texture=drawable.texture;
        NSUInteger width=texture.width,height=texture.height;
        MTLRenderPassDescriptor *pass=[MTLRenderPassDescriptor renderPassDescriptor];
        pass.colorAttachments[0].texture=texture;
        pass.colorAttachments[0].loadAction=MTLLoadActionClear;
        pass.colorAttachments[0].storeAction=MTLStoreActionStore;
        pass.colorAttachments[0].clearColor=MTLClearColorMake(r,g,b,a);
        id<MTLCommandBuffer> commands=[ctx.queue commandBuffer];
        id<MTLRenderCommandEncoder> encoder=[commands renderCommandEncoderWithDescriptor:pass];
        if(!encoder){failure(env,"Metal clear render command encoder failed");return;}
        [encoder endEncoding];[commands presentDrawable:drawable];[commands commit];[commands waitUntilCompleted];
        if(commands.status==MTLCommandBufferStatusError){failure(env,commands.error.localizedDescription.UTF8String);return;}
        fprintf(stderr,"[Metal] DIAGNOSTIC_FRAME_PRESENTED %lux%lu rgba=%.3f,%.3f,%.3f,%.3f\n",(unsigned long)width,(unsigned long)height,r,g,b,a);
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_release(JNIEnv *env,jclass cls,jlong handle){(void)env;(void)cls;if(handle){id value=(__bridge_transfer id)(void *)(uintptr_t)handle;(void)value;}}

JNIEXPORT jlong JNICALL Java_fabricaot_metal_MetalNative_createTexture(JNIEnv *env,jclass cls,jlong handle,jint format,jint usage,jint width,jint height,jint layers,jint mips){
    (void)cls;@autoreleasepool {
        MTLPixelFormat formats[]={MTLPixelFormatRGBA8Unorm,MTLPixelFormatR8Unorm,MTLPixelFormatR8Sint,MTLPixelFormatDepth32Float};
        if(format<0||format>3||width<=0||height<=0||layers<=0||mips<=0){failure(env,"Invalid Metal texture descriptor");return 0;}
        MTLTextureDescriptor *desc=[MTLTextureDescriptor new];desc.pixelFormat=formats[format];desc.width=width;desc.height=height;desc.mipmapLevelCount=mips;desc.storageMode=MTLStorageModePrivate;
        if(usage&16){desc.textureType=layers==6?MTLTextureTypeCube:MTLTextureTypeCubeArray;desc.arrayLength=layers/6;}
        else{desc.textureType=layers==1?MTLTextureType2D:MTLTextureType2DArray;desc.arrayLength=layers;}
        desc.usage=MTLTextureUsagePixelFormatView;
        if(usage&4)desc.usage|=MTLTextureUsageShaderRead;
        if(usage&8)desc.usage|=MTLTextureUsageRenderTarget;
        id<MTLTexture> value=[context(handle).device newTextureWithDescriptor:desc];if(!value){failure(env,"MTLTexture allocation failed");return 0;}return keep(value);
    }
}
JNIEXPORT jlong JNICALL Java_fabricaot_metal_MetalNative_createTextureView(JNIEnv *env,jclass cls,jlong handle,jint base,jint count){
    (void)cls;@autoreleasepool {
        id<MTLTexture> source=texture(handle);NSUInteger slices=source.arrayLength;
        if(source.textureType==MTLTextureTypeCube||source.textureType==MTLTextureTypeCubeArray)slices*=6;
        id<MTLTexture> view=[source newTextureViewWithPixelFormat:source.pixelFormat textureType:source.textureType levels:NSMakeRange(base,count) slices:NSMakeRange(0,slices)];
        if(!view){failure(env,"Metal texture view creation failed");return 0;}return keep(view);
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_clearTextures(JNIEnv *env,jclass cls,jlong handle,jlong color,jint argb,jlong depth,jdouble value){
    (void)cls;@autoreleasepool {FAOTMetalContext *ctx=context(handle);if(!outsidePass(env,ctx))return;
        MTLRenderPassDescriptor *pass=attachments(env,color?texture(color):nil,YES,argb,depth?texture(depth):nil,YES,value);if(!pass)return;
        id<MTLRenderCommandEncoder> encoder=[commands(ctx) renderCommandEncoderWithDescriptor:pass];if(!encoder){failure(env,"Metal texture clear encoder failed");return;}[encoder endEncoding];
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_clearRectangle(JNIEnv *env,jclass cls,jlong handle,jlong color,jint argb,jlong depth,jdouble value,jint x,jint y,jint width,jint height){
    (void)cls;
    @autoreleasepool {
        FAOTMetalContext *ctx=context(handle);
        if(!outsidePass(env,ctx))return;
        id<MTLTexture> target=texture(color), depthTarget=texture(depth);
        if(!target||!depthTarget||x<0||y<0||width<=0||height<=0||
           (uint64_t)x+width>target.width||(uint64_t)y+height>target.height||
           !isfinite(value)||value<0||value>1){
            failure(env,"Invalid Metal rectangle clear");return;
        }
        MTLRenderPassDescriptor *pass=attachments(env,target,NO,0,depthTarget,NO,value);
        if(!pass)return;
        if(!ctx.rectanglePipelines)ctx.rectanglePipelines=[NSMutableDictionary new];
        NSNumber *format=@(target.pixelFormat);
        id<MTLRenderPipelineState> pipelineState=ctx.rectanglePipelines[format];
        if(!pipelineState){
            id<MTLLibrary> library=utilityLibrary(env,ctx);
            if(!library)return;
            MTLRenderPipelineDescriptor *desc=[MTLRenderPipelineDescriptor new];
            desc.vertexFunction=[library newFunctionWithName:@"faot_clear_vertex"];
            desc.fragmentFunction=[library newFunctionWithName:@"faot_clear_fragment"];
            desc.colorAttachments[0].pixelFormat=target.pixelFormat;
            desc.depthAttachmentPixelFormat=depthTarget.pixelFormat;
            NSError *error=nil;
            pipelineState=[ctx.device newRenderPipelineStateWithDescriptor:desc error:&error];
            if(!pipelineState){failure(env,error.localizedDescription.UTF8String ?: "Metal rectangle clear pipeline failed");return;}
            ctx.rectanglePipelines[format]=pipelineState;
        }
        if(!ctx.rectangleDepth){
            MTLDepthStencilDescriptor *desc=[MTLDepthStencilDescriptor new];
            desc.depthCompareFunction=MTLCompareFunctionAlways;desc.depthWriteEnabled=YES;
            ctx.rectangleDepth=[ctx.device newDepthStencilStateWithDescriptor:desc];
            if(!ctx.rectangleDepth){failure(env,"Metal rectangle depth state failed");return;}
        }
        id<MTLRenderCommandEncoder> encoder=[commands(ctx) renderCommandEncoderWithDescriptor:pass];
        if(!encoder){failure(env,"Metal rectangle clear encoder failed");return;}
        [encoder setRenderPipelineState:pipelineState];
        [encoder setDepthStencilState:ctx.rectangleDepth];
        [encoder setScissorRect:(MTLScissorRect){(NSUInteger)x,target.height-(NSUInteger)y-(NSUInteger)height,(NSUInteger)width,(NSUInteger)height}];
        uint32_t c=(uint32_t)argb;
        float rgba[]={((c>>16)&255)/255.f,((c>>8)&255)/255.f,(c&255)/255.f,((c>>24)&255)/255.f};
        float z=(float)value;
        [encoder setVertexBytes:&z length:sizeof z atIndex:0];
        [encoder setFragmentBytes:rgba length:sizeof rgba atIndex:0];
        [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
        [encoder endEncoding];
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_beginPass(JNIEnv *env,jclass cls,jlong handle,jlong color,jboolean clear,jint argb,jlong depth,jboolean depthClear,jdouble value){
    (void)cls;@autoreleasepool {FAOTMetalContext *ctx=context(handle);if(!outsidePass(env,ctx))return;
        MTLRenderPassDescriptor *pass=attachments(env,texture(color),clear,argb,depth?texture(depth):nil,depthClear,value);if(!pass)return;
        ctx.renderEncoder=[commands(ctx) renderCommandEncoderWithDescriptor:pass];if(!ctx.renderEncoder)failure(env,"Metal render pass creation failed");
        else{ctx.activeColor=texture(color);ctx.activeDepth=depth?texture(depth):nil;ctx.emptyScissor=NO;}
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_endPass(JNIEnv *env,jclass cls,jlong handle){(void)cls;FAOTMetalContext *ctx=context(handle);if(!ctx.renderEncoder){failure(env,"No active Metal render pass");return;}[ctx.renderEncoder endEncoding];ctx.renderEncoder=nil;ctx.activeColor=nil;ctx.activeDepth=nil;ctx.emptyScissor=NO;}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_debugGroup(JNIEnv *env,jclass cls,jlong handle,jstring label,jboolean push){
    (void)cls;FAOTMetalContext *ctx=context(handle);if(!ctx.renderEncoder){failure(env,"No active Metal render pass");return;}
    if(push){const char *s=(*env)->GetStringUTFChars(env,label,NULL);if(!s)return;[ctx.renderEncoder pushDebugGroup:[NSString stringWithUTF8String:s]];(*env)->ReleaseStringUTFChars(env,label,s);}else[ctx.renderEncoder popDebugGroup];
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_synchronize(JNIEnv *env,jclass cls,jlong handle){(void)cls;@autoreleasepool{submitAndWait(env,context(handle));}}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_writeTexture(JNIEnv *env,jclass cls,jlong handle,jlong target,jint mip,jint layer,jint x,jint y,jint width,jint height,jlong data,jint sourceStride,jint components){
    (void)cls;@autoreleasepool {FAOTMetalContext *ctx=context(handle);if(!outsidePass(env,ctx))return;id<MTLTexture> destination=texture(target);
        NSUInteger bytes=pixelBytes(destination);
        if(!data||components<1||components>4||destination.pixelFormat==MTLPixelFormatDepth32Float||((bytes==1)&&components!=1)||sourceStride<(int64_t)width*components){failure(env,"Unsupported texture upload layout");return;}
        NSUInteger row=((NSUInteger)width*bytes+255)&~(NSUInteger)255,total=row*(NSUInteger)height;
        if(total>64*1024*1024){failure(env,"Texture transfer exceeds 64 MiB staging budget");return;}
        id<MTLBuffer> staging=[ctx.device newBufferWithLength:total options:MTLResourceStorageModeShared];if(!staging){failure(env,"Texture upload staging allocation failed");return;}
        for(int line=0;line<height;line++){
            const uint8_t *src=(const uint8_t *)(uintptr_t)data+(NSUInteger)line*sourceStride;uint8_t *dst=(uint8_t *)staging.contents+(NSUInteger)line*row;
            if(bytes==1||components==4)memcpy(dst,src,(NSUInteger)width*bytes);
            else if(!faot_expand_rgba(dst,src,(NSUInteger)width,components)){failure(env,"Invalid upload component layout");return;}
        }
        id<MTLBlitCommandEncoder> encoder=[commands(ctx) blitCommandEncoder];
        [encoder copyFromBuffer:staging sourceOffset:0 sourceBytesPerRow:row sourceBytesPerImage:total sourceSize:MTLSizeMake(width,height,1) toTexture:destination destinationSlice:layer destinationLevel:mip destinationOrigin:MTLOriginMake(x,y,0)];[encoder endEncoding];
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_readTexture(JNIEnv *env,jclass cls,jlong handle,jlong source,jint mip,jint x,jint y,jint width,jint height,jlong destination,jlong offset){
    (void)cls;@autoreleasepool {FAOTMetalContext *ctx=context(handle);if(!outsidePass(env,ctx))return;id<MTLTexture> input=texture(source);NSUInteger bytes=pixelBytes(input);
        if(!bytes){failure(env,"Unsupported texture readback format");return;}
        NSUInteger row=((NSUInteger)width*bytes+255)&~(NSUInteger)255,total=row*(NSUInteger)height;
        if(total>64*1024*1024){failure(env,"Texture readback exceeds 64 MiB staging budget");return;}
        id<MTLBuffer> staging=[ctx.device newBufferWithLength:total options:MTLResourceStorageModeShared];if(!staging){failure(env,"Texture readback staging allocation failed");return;}
        id<MTLBlitCommandEncoder> encoder=[commands(ctx) blitCommandEncoder];
        [encoder copyFromTexture:input sourceSlice:0 sourceLevel:mip sourceOrigin:MTLOriginMake(x,y,0) sourceSize:MTLSizeMake(width,height,1) toBuffer:staging destinationOffset:0 destinationBytesPerRow:row destinationBytesPerImage:total];[encoder endEncoding];
        if(!submitAndWait(env,ctx))return;
        uint8_t *dst=(uint8_t *)buffer(destination).contents+(NSUInteger)offset;
        for(int line=0;line<height;line++)memcpy(dst+(NSUInteger)line*width*bytes,(uint8_t *)staging.contents+(NSUInteger)line*row,(NSUInteger)width*bytes);
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_copyTexture(JNIEnv *env,jclass cls,jlong handle,jlong source,jlong destination,jint mip,jint sx,jint sy,jint dx,jint dy,jint width,jint height){
    (void)cls;@autoreleasepool {FAOTMetalContext *ctx=context(handle);if(!outsidePass(env,ctx))return;
        id<MTLBlitCommandEncoder> encoder=[commands(ctx) blitCommandEncoder];
        [encoder copyFromTexture:texture(source) sourceSlice:0 sourceLevel:mip sourceOrigin:MTLOriginMake(sx,sy,0) sourceSize:MTLSizeMake(width,height,1) toTexture:texture(destination) destinationSlice:0 destinationLevel:mip destinationOrigin:MTLOriginMake(dx,dy,0)];[encoder endEncoding];
    }
}
JNIEXPORT jlong JNICALL Java_fabricaot_metal_MetalNative_createFence(JNIEnv *env,jclass cls,jlong handle){
    (void)cls;@autoreleasepool {FAOTMetalContext *ctx=context(handle);if(!outsidePass(env,ctx))return 0;FAOTMetalFence *fence=[FAOTMetalFence new];fence.completion=dispatch_group_create();dispatch_group_enter(fence.completion);
        id<MTLCommandBuffer> pending=commands(ctx);[pending addCompletedHandler:^(id<MTLCommandBuffer> completed){if(completed.status==MTLCommandBufferStatusError)fence.error=completed.error.localizedDescription;dispatch_group_leave(fence.completion);}];
        ctx.lastCommitted=pending;ctx.pending=nil;[pending commit];return keep(fence);
    }
}
JNIEXPORT jboolean JNICALL Java_fabricaot_metal_MetalNative_awaitFence(JNIEnv *env,jclass cls,jlong handle,jlong timeout){
    (void)cls;FAOTMetalFence *fence=(__bridge FAOTMetalFence *)(void *)(uintptr_t)handle;
    if(dispatch_group_wait(fence.completion,dispatch_time(DISPATCH_TIME_NOW,timeout))!=0)return JNI_FALSE;
    if(fence.error){failure(env,fence.error.UTF8String);return JNI_FALSE;}return JNI_TRUE;
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_presentTexture(JNIEnv *env,jclass cls,jlong handle,jlong view){
    (void)cls;FAOTMetalContext *ctx=context(handle);if(!outsidePass(env,ctx))return;id<MTLTexture> source=texture(view);
    if(source.pixelFormat!=MTLPixelFormatRGBA8Unorm||source.textureType!=MTLTextureType2D){failure(env,"Presentation requires an RGBA8 2D texture view");return;}
    ctx.presentationSource=source;
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_setDisplaySync(JNIEnv *env,jclass cls,jlong handle,jboolean enabled){(void)env;(void)cls;FAOTMetalContext *ctx=context(handle);if(!ctx||!ctx.layer)return;@autoreleasepool{SEL selector=@selector(setDisplaySyncEnabled:);if([ctx.layer respondsToSelector:selector])((void(*)(id,SEL,BOOL))objc_msgSend)((id)ctx.layer,selector,(BOOL)(enabled==JNI_TRUE));}}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_presentFrame(JNIEnv *env,jclass cls,jlong handle){
    (void)cls;@autoreleasepool {FAOTMetalContext *ctx=context(handle);if(!outsidePass(env,ctx))return;
        if(!ctx.presentationSource){failure(env,"No texture was queued for Metal presentation");return;}
        if(!ctx.presentationPipeline){
            NSError *error=nil;
            id<MTLLibrary> library=utilityLibrary(env,ctx);if(!library)return;
            MTLRenderPipelineDescriptor *desc=[MTLRenderPipelineDescriptor new];desc.vertexFunction=[library newFunctionWithName:@"faot_present_vertex"];desc.fragmentFunction=[library newFunctionWithName:@"faot_present_fragment"];desc.colorAttachments[0].pixelFormat=ctx.layer.pixelFormat;
            ctx.presentationPipeline=[ctx.device newRenderPipelineStateWithDescriptor:desc error:&error];if(!ctx.presentationPipeline){failure(env,error.localizedDescription.UTF8String);return;}
        }
        id<CAMetalDrawable> drawable=[ctx.layer nextDrawable];if(!drawable){failure(env,"No drawable available for texture presentation");return;}
        id<MTLTexture> output=drawable.texture;NSUInteger width=output.width,height=output.height;
        MTLRenderPassDescriptor *pass=[MTLRenderPassDescriptor renderPassDescriptor];pass.colorAttachments[0].texture=output;pass.colorAttachments[0].loadAction=MTLLoadActionDontCare;pass.colorAttachments[0].storeAction=MTLStoreActionStore;
        id<MTLCommandBuffer> pending=commands(ctx);id<MTLRenderCommandEncoder> encoder=[pending renderCommandEncoderWithDescriptor:pass];
        [encoder setRenderPipelineState:ctx.presentationPipeline];[encoder setFragmentTexture:ctx.presentationSource atIndex:0];[encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];[encoder endEncoding];
        [pending presentDrawable:drawable];ctx.presentationSource=nil;if(!submitAndWait(env,ctx))return;
        if(!ctx.presentationLogged){ctx.presentationLogged=YES;fprintf(stderr,"[Metal] TEXTURE_FRAME_PRESENTED %lux%lu\n",(unsigned long)width,(unsigned long)height);}
    }
}

@interface FAOTMetalPipeline : NSObject
@property(nonatomic,strong) id<MTLFunction> vertex;
@property(nonatomic) BOOL flipsVertexY;
@property(nonatomic,strong) id<MTLFunction> fragment;
@property(nonatomic,strong) MTLVertexDescriptor *vertices;
@property(nonatomic,strong) NSMutableDictionary<NSString *,id<MTLRenderPipelineState>> *states;
@property(nonatomic,strong) id<MTLDepthStencilState> depth;
@property(nonatomic,strong) NSData *configuration;
@property(nonatomic) float depthBiasScale;
@property(nonatomic) float depthBiasConstant;
@end
@implementation FAOTMetalPipeline
@end
static FAOTMetalPipeline *pipeline(jlong handle){return (__bridge FAOTMetalPipeline *)(void *)(uintptr_t)handle;}
static MTLVertexFormat vertexFormat(int type,int count,int normalized){
    if(type<0||type>6||count<1||count>4)return MTLVertexFormatInvalid;
    static const MTLVertexFormat floating[]={MTLVertexFormatFloat,MTLVertexFormatFloat2,MTLVertexFormatFloat3,MTLVertexFormatFloat4};
    static const MTLVertexFormat unsignedByte[]={MTLVertexFormatUChar,MTLVertexFormatUChar2,MTLVertexFormatUChar3,MTLVertexFormatUChar4};
    static const MTLVertexFormat signedByte[]={MTLVertexFormatChar,MTLVertexFormatChar2,MTLVertexFormatChar3,MTLVertexFormatChar4};
    static const MTLVertexFormat unsignedShort[]={MTLVertexFormatUShort,MTLVertexFormatUShort2,MTLVertexFormatUShort3,MTLVertexFormatUShort4};
    static const MTLVertexFormat signedShort[]={MTLVertexFormatShort,MTLVertexFormatShort2,MTLVertexFormatShort3,MTLVertexFormatShort4};
    static const MTLVertexFormat unsignedInt[]={MTLVertexFormatUInt,MTLVertexFormatUInt2,MTLVertexFormatUInt3,MTLVertexFormatUInt4};
    static const MTLVertexFormat signedInt[]={MTLVertexFormatInt,MTLVertexFormatInt2,MTLVertexFormatInt3,MTLVertexFormatInt4};
    static const MTLVertexFormat normalizedUnsignedByte[]={MTLVertexFormatUCharNormalized,MTLVertexFormatUChar2Normalized,MTLVertexFormatUChar3Normalized,MTLVertexFormatUChar4Normalized};
    static const MTLVertexFormat normalizedSignedByte[]={MTLVertexFormatCharNormalized,MTLVertexFormatChar2Normalized,MTLVertexFormatChar3Normalized,MTLVertexFormatChar4Normalized};
    static const MTLVertexFormat normalizedUnsignedShort[]={MTLVertexFormatUShortNormalized,MTLVertexFormatUShort2Normalized,MTLVertexFormatUShort3Normalized,MTLVertexFormatUShort4Normalized};
    static const MTLVertexFormat normalizedSignedShort[]={MTLVertexFormatShortNormalized,MTLVertexFormatShort2Normalized,MTLVertexFormatShort3Normalized,MTLVertexFormatShort4Normalized};
    const MTLVertexFormat *formats[]={floating,unsignedByte,signedByte,unsignedShort,signedShort,unsignedInt,signedInt};
    if(normalized&&type!=0){const MTLVertexFormat *normalizedFormats[]={NULL,normalizedUnsignedByte,normalizedSignedByte,normalizedUnsignedShort,normalizedSignedShort,NULL,NULL};if(!normalizedFormats[type])return MTLVertexFormatInvalid;return normalizedFormats[type][count-1];}
    return formats[type][count-1];
}
static BOOL requirePass(JNIEnv *env,FAOTMetalContext *ctx){if(!ctx.renderEncoder){failure(env,"Metal draw/binding requires an active render pass");return NO;}return YES;}
JNIEXPORT jlong JNICALL Java_fabricaot_metal_MetalNative_createPipeline(JNIEnv *env,jclass cls,jlong handle,jstring key,jintArray attributes,jint stride,jintArray configuration,jfloat scale,jfloat constant){
    (void)cls;@autoreleasepool {
        if(!key||!attributes||!configuration||(*env)->GetArrayLength(env,configuration)!=11||!isfinite(scale)||!isfinite(constant)){failure(env,"Invalid Metal pipeline descriptor");return 0;}
        jint values[11];(*env)->GetIntArrayRegion(env,configuration,0,11,values);if((*env)->ExceptionCheck(env))return 0;
        if(values[0]<0||values[0]>15||values[6]<0||values[6]>7||values[10]<0||values[10]>5){failure(env,"Invalid pipeline state range");return 0;}
        const char *utf=(*env)->GetStringUTFChars(env,key,NULL);if(!utf)return 0;NSString *name=[NSString stringWithUTF8String:utf];(*env)->ReleaseStringUTFChars(env,key,utf);
        NSCharacterSet *invalid=[[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"] invertedSet];
        if(name.length!=64||[name rangeOfCharacterFromSet:invalid].location!=NSNotFound){failure(env,"Invalid shader library key");return 0;}
        NSString *path=[[NSBundle.mainBundle.privateFrameworksPath stringByAppendingPathComponent:@"fabricaot-shaders"] stringByAppendingPathComponent:[name stringByAppendingString:@".metallib"]];NSError *error=nil;
        FAOTMetalContext *ctx=context(handle);id<MTLLibrary> library=[ctx.device newLibraryWithURL:[NSURL fileURLWithPath:path] error:&error];
        if(!library){failure(env,error.localizedDescription.UTF8String);return 0;}
        FAOTMetalPipeline *result=[FAOTMetalPipeline new];result.vertex=[library newFunctionWithName:@"faot_vertex"];result.fragment=[library newFunctionWithName:@"faot_fragment"];
        if(!result.vertex){result.vertex=[library newFunctionWithName:@"faot_texture_vertex"];result.flipsVertexY=result.vertex!=nil;}
        if(!result.vertex||!result.fragment){failure(env,"Precompiled shader entry point missing");return 0;}
        jsize length=(*env)->GetArrayLength(env,attributes);if(length%5||length>31*5||(length&&(stride<=0||stride>2048))){failure(env,"Invalid vertex descriptor length/stride");return 0;}
        if(length){
            jint *data=(*env)->GetIntArrayElements(env,attributes,NULL);if(!data)return 0;MTLVertexDescriptor *descriptor=[MTLVertexDescriptor vertexDescriptor];BOOL valid=YES;uint32_t locations=0;
            for(int i=0;i<length;i+=5){
                int location=data[i],type=data[i+1],count=data[i+2],normalized=data[i+3],offset=data[i+4];MTLVertexFormat format=vertexFormat(type,count,normalized);
                static const int bytes[]={4,1,1,2,2,4,4};
                if(location<0||location>=31||format==MTLVertexFormatInvalid||offset<0||offset>stride-count*(type>=0&&type<7?bytes[type]:0)||(locations&(1u<<location))){valid=NO;break;}
                locations|=1u<<location;descriptor.attributes[location].format=format;descriptor.attributes[location].offset=offset;descriptor.attributes[location].bufferIndex=30;
            }
            (*env)->ReleaseIntArrayElements(env,attributes,data,JNI_ABORT);if(!valid){failure(env,"Unsupported vertex attribute format/range");return 0;}
            descriptor.layouts[30].stride=stride;descriptor.layouts[30].stepFunction=MTLVertexStepFunctionPerVertex;result.vertices=descriptor;
        }
        MTLDepthStencilDescriptor *depth=[MTLDepthStencilDescriptor new];static const MTLCompareFunction comparisons[]={MTLCompareFunctionAlways,MTLCompareFunctionLess,MTLCompareFunctionLessEqual,MTLCompareFunctionEqual,MTLCompareFunctionNotEqual,MTLCompareFunctionGreaterEqual,MTLCompareFunctionGreater,MTLCompareFunctionNever};
        depth.depthCompareFunction=comparisons[values[6]];depth.depthWriteEnabled=values[7]!=0;result.depth=[ctx.device newDepthStencilStateWithDescriptor:depth];
        result.configuration=[NSData dataWithBytes:values length:sizeof values];result.states=[NSMutableDictionary new];result.depthBiasScale=scale;result.depthBiasConstant=constant;return keep(result);
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_setPipeline(JNIEnv *env,jclass cls,jlong handle,jlong value){
    (void)cls;@autoreleasepool {FAOTMetalContext *ctx=context(handle);if(!requirePass(env,ctx))return;FAOTMetalPipeline *p=pipeline(value);const jint *state=p.configuration.bytes;
        if(!ctx.activeDepth&&(state[7]||state[6]!=0)){failure(env,"Pipeline requires a depth attachment");return;}
        NSString *key=[NSString stringWithFormat:@"%lu/%lu/%lu",(unsigned long)ctx.activeColor.pixelFormat,(unsigned long)ctx.activeDepth.pixelFormat,(unsigned long)ctx.activeColor.sampleCount];
        id<MTLRenderPipelineState> compiled=p.states[key];
        if(!compiled){
            MTLRenderPipelineDescriptor *desc=[MTLRenderPipelineDescriptor new];desc.vertexFunction=p.vertex;desc.fragmentFunction=p.fragment;desc.vertexDescriptor=p.vertices;desc.rasterSampleCount=ctx.activeColor.sampleCount;
            desc.colorAttachments[0].pixelFormat=ctx.activeColor.pixelFormat;desc.depthAttachmentPixelFormat=ctx.activeDepth?ctx.activeDepth.pixelFormat:MTLPixelFormatInvalid;
            MTLRenderPipelineColorAttachmentDescriptor *color=desc.colorAttachments[0];color.writeMask=MTLColorWriteMaskNone;
            if(state[0]&1)color.writeMask|=MTLColorWriteMaskRed;if(state[0]&2)color.writeMask|=MTLColorWriteMaskGreen;if(state[0]&4)color.writeMask|=MTLColorWriteMaskBlue;if(state[0]&8)color.writeMask|=MTLColorWriteMaskAlpha;
            color.blendingEnabled=state[1]!=0;
            if(color.blendingEnabled){
                static const MTLBlendFactor factors[]={MTLBlendFactorZero,MTLBlendFactorOne,MTLBlendFactorSourceColor,MTLBlendFactorOneMinusSourceColor,MTLBlendFactorSourceAlpha,MTLBlendFactorOneMinusSourceAlpha,MTLBlendFactorDestinationColor,MTLBlendFactorOneMinusDestinationColor,MTLBlendFactorDestinationAlpha,MTLBlendFactorOneMinusDestinationAlpha,MTLBlendFactorSourceAlphaSaturated,MTLBlendFactorBlendColor,MTLBlendFactorOneMinusBlendColor,MTLBlendFactorBlendAlpha,MTLBlendFactorOneMinusBlendAlpha};
                for(int i=2;i<6;i++)if(state[i]<0||state[i]>=15){failure(env,"Invalid blend factor");return;}
                color.sourceRGBBlendFactor=factors[state[2]];color.destinationRGBBlendFactor=factors[state[3]];color.sourceAlphaBlendFactor=factors[state[4]];color.destinationAlphaBlendFactor=factors[state[5]];
            }
            NSError *error=nil;compiled=[ctx.device newRenderPipelineStateWithDescriptor:desc error:&error];if(!compiled){failure(env,error.localizedDescription.UTF8String);return;}p.states[key]=compiled;
        }
        [ctx.renderEncoder setRenderPipelineState:compiled];[ctx.renderEncoder setDepthStencilState:p.depth];[ctx.renderEncoder setCullMode:state[8]?MTLCullModeBack:MTLCullModeNone];[ctx.renderEncoder setFrontFacingWinding:p.flipsVertexY?MTLWindingClockwise:MTLWindingCounterClockwise];
        [ctx.renderEncoder setTriangleFillMode:state[9]?MTLTriangleFillModeLines:MTLTriangleFillModeFill];[ctx.renderEncoder setDepthBias:p.depthBiasConstant slopeScale:p.depthBiasScale clamp:0];[ctx.renderEncoder setBlendColorRed:0 green:0 blue:0 alpha:0];
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_bindUniform(JNIEnv *env,jclass cls,jlong handle,jint stage,jint index,jlong value,jlong offset,jlong length){
    (void)cls;FAOTMetalContext *ctx=context(handle);if(!requirePass(env,ctx))return;id<MTLBuffer> input=buffer(value);
    if(stage<0||stage>1||index<0||index>=30||offset<0||length<0||(uint64_t)offset>input.length||(uint64_t)length>input.length-(uint64_t)offset||offset%256){failure(env,"Invalid or unaligned uniform buffer slice");return;}
    if(stage==0)[ctx.renderEncoder setVertexBuffer:input offset:offset atIndex:index];else[ctx.renderEncoder setFragmentBuffer:input offset:offset atIndex:index];
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_bindTexture(JNIEnv *env,jclass cls,jlong handle,jint stage,jint index,jint samplerIndex,jlong value,jlong sampler){
    (void)cls;FAOTMetalContext *ctx=context(handle);if(!requirePass(env,ctx))return;
    if(stage<0||stage>1||index<0||index>=16||samplerIndex < -1||samplerIndex>=16){failure(env,"Invalid Metal texture/sampler binding");return;}
    id<MTLSamplerState> state=(__bridge id<MTLSamplerState>)(void *)(uintptr_t)sampler;
    if(stage==0){[ctx.renderEncoder setVertexTexture:texture(value) atIndex:index];if(samplerIndex>=0)[ctx.renderEncoder setVertexSamplerState:state atIndex:samplerIndex];}
    else{[ctx.renderEncoder setFragmentTexture:texture(value) atIndex:index];if(samplerIndex>=0)[ctx.renderEncoder setFragmentSamplerState:state atIndex:samplerIndex];}
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_bindTexelBuffer(JNIEnv *env,jclass cls,jlong handle,jint stage,jint index,jint format,jlong value,jlong offset,jlong length){
    (void)cls;@autoreleasepool {FAOTMetalContext *ctx=context(handle);if(!requirePass(env,ctx))return;
        if(stage<0||stage>1||index<0||index>=16||format<0||format>2||offset<0||length<=0||length>64*1024*1024){failure(env,"Invalid Metal texel buffer");return;}
        static const MTLPixelFormat formats[]={MTLPixelFormatRGBA8Unorm,MTLPixelFormatR8Unorm,MTLPixelFormatR8Sint};NSUInteger bytes=format==0?4:1;id<MTLBuffer> source=buffer(value);
        if((uint64_t)offset>source.length||(uint64_t)length>source.length-(uint64_t)offset||length%bytes){failure(env,"Texel buffer range/format mismatch");return;}
        MTLPixelFormat pixelFormat=formats[format];
        NSUInteger alignment=[ctx.device minimumTextureBufferAlignmentForPixelFormat:pixelFormat];
        if(!alignment||alignment>65536){failure(env,"Invalid Metal texel buffer alignment");return;}
        NSUInteger stride=(((NSUInteger)length+alignment-1)/alignment)*alignment;
        // The simulator rejects linear texture views of shared buffers. Use a separate queue
        // to finish the CPU snapshot upload while the graphics queue has an open render pass.
        id<MTLBuffer> staging=[ctx.device newBufferWithLength:stride options:MTLResourceStorageModeShared];
        id<MTLBuffer> snapshot=[ctx.device newBufferWithLength:stride options:MTLResourceStorageModePrivate];
        if(!staging||!snapshot){failure(env,"Metal texel buffer allocation failed");return;}
        memcpy(staging.contents,(uint8_t *)source.contents+offset,(NSUInteger)length);
        memset((uint8_t *)staging.contents+length,0,stride-(NSUInteger)length);
        MTLTextureDescriptor *desc=[MTLTextureDescriptor new];desc.textureType=MTLTextureTypeTextureBuffer;desc.pixelFormat=pixelFormat;desc.width=length/bytes;desc.height=1;desc.storageMode=MTLStorageModePrivate;desc.usage=MTLTextureUsageShaderRead;
        id<MTLTexture> view=[snapshot newTextureWithDescriptor:desc offset:0 bytesPerRow:stride];if(!view){failure(env,"Metal texel buffer view allocation failed");return;}
        if(!ctx.texelUploadQueue)ctx.texelUploadQueue=[ctx.device newCommandQueue];
        id<MTLCommandBuffer> upload=[ctx.texelUploadQueue commandBuffer];id<MTLBlitCommandEncoder> transfer=[upload blitCommandEncoder];
        if(!transfer){failure(env,"Metal texel buffer upload encoder allocation failed");return;}
        [transfer copyFromBuffer:staging sourceOffset:0 toBuffer:snapshot destinationOffset:0 size:stride];
        [transfer endEncoding];[upload commit];[upload waitUntilCompleted];
        if(upload.status!=MTLCommandBufferStatusCompleted){failure(env,"Metal texel buffer upload failed");return;}
        if(stage==0)[ctx.renderEncoder setVertexTexture:view atIndex:index];else[ctx.renderEncoder setFragmentTexture:view atIndex:index];
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_vertexBuffer(JNIEnv *env,jclass cls,jlong handle,jlong value){(void)cls;FAOTMetalContext *ctx=context(handle);if(requirePass(env,ctx))[ctx.renderEncoder setVertexBuffer:buffer(value) offset:0 atIndex:30];}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_scissor(JNIEnv *env,jclass cls,jlong handle,jboolean enabled,jint x,jint y,jint width,jint height){
    (void)cls;FAOTMetalContext *ctx=context(handle);if(!requirePass(env,ctx))return;int64_t w=ctx.activeColor.width,h=ctx.activeColor.height;
    int64_t left=enabled?MAX((int64_t)x,0):0,right=enabled?MIN((int64_t)x+width,w):w;
    int64_t top=enabled?MAX(h-(int64_t)y-height,0):0,bottom=enabled?MIN(h-(int64_t)y,h):h;
    ctx.emptyScissor=right<=left||bottom<=top;if(!ctx.emptyScissor)[ctx.renderEncoder setScissorRect:(MTLScissorRect){(NSUInteger)left,(NSUInteger)top,(NSUInteger)(right-left),(NSUInteger)(bottom-top)}];
}
static MTLPrimitiveType primitive(FAOTMetalPipeline *p){const jint *state=p.configuration.bytes;static const MTLPrimitiveType modes[]={MTLPrimitiveTypePoint,MTLPrimitiveTypeLine,MTLPrimitiveTypeLineStrip,MTLPrimitiveTypeTriangle,MTLPrimitiveTypeTriangleStrip};return modes[state[10]];}
static void fan(JNIEnv *env,FAOTMetalContext *ctx,id<MTLBuffer> indices,int indexType,int first,int count,int baseVertex,int instances){
    if(count<3||instances==0)return;uint64_t words=(uint64_t)(count-2)*3;if(words>64*1024*1024/4){failure(env,"Triangle fan staging budget exceeded");return;}
    id<MTLBuffer> expanded=[ctx.device newBufferWithLength:words*4 options:MTLResourceStorageModeShared];if(!expanded){failure(env,"Triangle fan allocation failed");return;}uint32_t *out=expanded.contents;
    for(int i=0;i<count-2;i++)for(int j=0;j<3;j++){
        NSUInteger n=first+(j==0?0:i+j);uint32_t value;
        if(!indices)value=(uint32_t)n;else if(indexType==0){uint16_t v;memcpy(&v,(uint8_t *)indices.contents+n*2,2);value=v;}else memcpy(&value,(uint8_t *)indices.contents+n*4,4);
        out[i*3+j]=value;
    }
    [ctx.renderEncoder drawIndexedPrimitives:MTLPrimitiveTypeTriangle indexCount:words indexType:MTLIndexTypeUInt32 indexBuffer:expanded indexBufferOffset:0 instanceCount:instances baseVertex:baseVertex baseInstance:0];
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_draw(JNIEnv *env,jclass cls,jlong handle,jlong value,jint first,jint count){
    (void)cls;@autoreleasepool {FAOTMetalContext *ctx=context(handle);if(!requirePass(env,ctx)||ctx.emptyScissor)return;FAOTMetalPipeline *p=pipeline(value);const jint *state=p.configuration.bytes;
        if(state[10]==5)fan(env,ctx,nil,0,first,count,0,1);else[ctx.renderEncoder drawPrimitives:primitive(p) vertexStart:first vertexCount:count];
    }
}
JNIEXPORT void JNICALL Java_fabricaot_metal_MetalNative_drawIndexed(JNIEnv *env,jclass cls,jlong handle,jlong value,jlong indices,jint indexType,jint first,jint count,jint baseVertex,jint instances){
    (void)cls;@autoreleasepool {FAOTMetalContext *ctx=context(handle);if(!requirePass(env,ctx)||ctx.emptyScissor)return;FAOTMetalPipeline *p=pipeline(value);const jint *state=p.configuration.bytes;
        if(state[10]==5)fan(env,ctx,buffer(indices),indexType,first,count,baseVertex,instances);
        else[ctx.renderEncoder drawIndexedPrimitives:primitive(p) indexCount:count indexType:indexType==0?MTLIndexTypeUInt16:MTLIndexTypeUInt32 indexBuffer:buffer(indices) indexBufferOffset:(NSUInteger)first*(indexType==0?2:4) instanceCount:instances baseVertex:baseVertex baseInstance:0];
    }
}
