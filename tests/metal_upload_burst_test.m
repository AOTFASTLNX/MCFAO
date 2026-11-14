// Exercises the actual JNI upload implementation, not a pool-only model.
#import "../ios/metal-bridge/metal_bridge.m"
void *faot_glfw_metal_layer(GLFWwindow *window) { (void)window; return NULL; }
static int errors;
static jclass JNICALL fakeFindClass(JNIEnv *env, const char *name) {
    (void)env; (void)name; errors++; return NULL;
}
static int uploadBurst(NSUInteger cap, NSUInteger maxBatches) { @autoreleasepool {
    id<MTLDevice> device=MTLCreateSystemDefaultDevice();
    if(!device)return 77;
    FAOTMetalContext *ctx=[FAOTMetalContext new];
    ctx.device=device;ctx.queue=[device newCommandQueue];ctx.perf=[FAOTPerfCollector new];
    ctx.resources=[[FAOTResourceTracker alloc] initWithDevice:device maxTransientBytes:cap];
    struct JNINativeInterface_ table={0};table.FindClass=fakeFindClass;
    JNIEnv env=&table;
    MTLTextureDescriptor *desc=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:256 height:256 mipmapped:NO];
    desc.storageMode=MTLStorageModePrivate;
    id<MTLTexture> texture=[device newTextureWithDescriptor:desc];
    jlong h=(jlong)(uintptr_t)(__bridge void *)ctx;
    jlong t=(jlong)(uintptr_t)(__bridge void *)texture;
    uint8_t pixels[16*16*4];
    NSUInteger peak=0;
    for(int i=0;i<20000;i++) { @autoreleasepool {
        for(NSUInteger j=0;j<sizeof(pixels);j++)pixels[j]=(uint8_t)(i+j);
        Java_fabricaot_metal_MetalNative_writeTexture(&env,NULL,h,t,0,0,(i%16)*16,((i/16)%16)*16,16,16,(jlong)(uintptr_t)pixels,64,4);
        peak=MAX(peak,ctx.resources.transientAllocatedBytes);
        if(errors){fprintf(stderr,"FAIL: JNI upload rejected at upload %d, %s\n",i,ctx.resources.memorySnapshot.UTF8String);return 1;}
    }}
    if(ctx.uploadBatchCount==0||ctx.uploadBatchCount>=maxBatches||ctx.syncWaitSeconds!=0){
        fprintf(stderr,"FAIL: uploads must use bounded asynchronous batches\n");return 1;
    }
    // GPU readback after all submitted batches proves same-queue ordering and
    // that recycled staging was never overwritten before its copy completed.
    id<MTLBuffer> readback=[device newBufferWithLength:256*256*4 options:MTLResourceStorageModeShared];
    id<MTLCommandBuffer> cb=commands(ctx);
    id<MTLBlitCommandEncoder> blit=[cb blitCommandEncoder];
    [blit copyFromTexture:texture sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(256,256,1) toBuffer:readback destinationOffset:0 destinationBytesPerRow:1024 destinationBytesPerImage:256*256*4];
    [blit endEncoding];
    if(!submitAndWait(&env,ctx)||errors)return 1;
    const uint8_t *out=readback.contents;
    for(int tile=0;tile<256;tile++){
        int last=tile+((19999-tile)/256)*256;
        for(int y=0;y<16;y++)for(int x=0;x<64;x++){
            NSUInteger at=((tile/16)*16+y)*1024+(tile%16)*64+x;
            if(out[at]!=(uint8_t)(last+y*64+x)){fprintf(stderr,"FAIL: upload pixels differ tile=%d\n",tile);return 1;}
        }
    }
    if(peak>cap)return 1;
    if(cap>=64*1024*1024){
        NSUInteger batches=ctx.uploadBatchCount;
        NSMutableData *large=[NSMutableData dataWithLength:256*256*4];
        for(int i=0;i<40;i++){
            memset(large.mutableBytes,i,large.length);
            Java_fabricaot_metal_MetalNative_writeTexture(&env,NULL,h,t,0,0,0,0,256,256,(jlong)(uintptr_t)large.bytes,1024,4);
        }
        if(errors||ctx.uploadBatchCount!=batches+1){
            fprintf(stderr,"FAIL: byte threshold must submit before 256 uploads\n");return 1;
        }
        cb=commands(ctx);blit=[cb blitCommandEncoder];
        [blit copyFromTexture:texture sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(256,256,1) toBuffer:readback destinationOffset:0 destinationBytesPerRow:1024 destinationBytesPerImage:256*256*4];
        [blit endEncoding];
        if(!submitAndWait(&env,ctx)||errors)return 1;
        for(NSUInteger i=0;i<large.length;i++)if(out[i]!=39){
            fprintf(stderr,"FAIL: byte-batched upload pixels differ\n");return 1;
        }
    }
    fprintf(stderr,"peak_transient_bytes=%lu %s\n",(unsigned long)peak,ctx.resources.memorySnapshot.UTF8String);
    [ctx.resources close];
    puts("METAL_UPLOAD_BURST_PASS uploads=20000 pixels=verified");
    return 0;
}}

int main(void) {
    int result=uploadBurst(64*1024*1024,200);
    if(result)return result;
    // A cap below the proactive batch size forces the pre-allocation submit
    // path. The allocator must never wait on uncommitted uploads.
    return uploadBurst(128*1024,1000);
}
