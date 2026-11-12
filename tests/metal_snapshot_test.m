// Host-side Metal regression: immutable snapshots survive mutation of source data
// and release of CPU references after encoding. This does not replace iOS tests.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <string.h>
int main(void) { @autoreleasepool {
    id<MTLDevice> device=MTLCreateSystemDefaultDevice();
    if(!device) { fprintf(stderr,"No Metal device available\n"); return 1; }
    NSError *error=nil;
    NSString *source=@"#include <metal_stdlib>\nusing namespace metal; kernel void readback(texture_buffer<float, access::read> t [[texture(0)]], device float4 *out [[buffer(0)]], uint i [[thread_position_in_grid]]) { out[i]=t.read(i); }";
    id<MTLLibrary> lib=[device newLibraryWithSource:source options:nil error:&error];
    id<MTLFunction> fn=[lib newFunctionWithName:@"readback"];
    id<MTLComputePipelineState> pipeline=fn ? [device newComputePipelineStateWithFunction:fn error:&error] : nil;
    if(!pipeline) { fprintf(stderr,"%s\n",error.description.UTF8String);return 1; }
    id<MTLCommandQueue> queue=[device newCommandQueue];
    for(NSUInteger count=1;count<=257;count+=128) {
        NSUInteger alignment=[device minimumTextureBufferAlignmentForPixelFormat:MTLPixelFormatRGBA8Unorm];
        NSUInteger bytes=count*4, stride=((bytes+alignment-1)/alignment)*alignment;
        id<MTLBuffer> output=[device newBufferWithLength:count*4*sizeof(float) options:MTLResourceStorageModeShared];
        id<MTLCommandBuffer> command=[queue commandBuffer];
        @autoreleasepool {
            NSMutableData *original=[NSMutableData dataWithLength:bytes];
            memset(original.mutableBytes,255,bytes);
            id<MTLBuffer> snapshot=[device newBufferWithLength:stride options:MTLResourceStorageModeShared];
            memcpy(snapshot.contents,original.bytes,bytes);
            memset((uint8_t *)snapshot.contents+bytes,0,stride-bytes);
            MTLTextureDescriptor *desc=[MTLTextureDescriptor new];
            desc.textureType=MTLTextureTypeTextureBuffer;desc.pixelFormat=MTLPixelFormatRGBA8Unorm;
            desc.width=count;desc.height=1;desc.storageMode=MTLStorageModeShared;desc.usage=MTLTextureUsageShaderRead;
            id<MTLTexture> view=[snapshot newTextureWithDescriptor:desc offset:0 bytesPerRow:stride];
            if(!view) { fprintf(stderr,"Shared texture buffer unsupported on host\n");return 1; }
            id<MTLComputeCommandEncoder> encoder=[command computeCommandEncoder];
            [encoder setComputePipelineState:pipeline];[encoder setTexture:view atIndex:0];
            [encoder setBuffer:output offset:0 atIndex:0];
            [encoder dispatchThreads:MTLSizeMake(count,1,1) threadsPerThreadgroup:MTLSizeMake(1,1,1)];
            [encoder endEncoding];
            memset(original.mutableBytes,0,bytes);
        }
        [command commit];[command waitUntilCompleted];
        if(command.status!=MTLCommandBufferStatusCompleted){fprintf(stderr,"%s\n",command.error.description.UTF8String);return 1;}
        float *values=output.contents;
        for(NSUInteger i=0;i<count*4;i++) if(values[i]!=1.0f){fprintf(stderr,"Snapshot corrupted at %lu\n",(unsigned long)i);return 1;}
    }
    puts("METAL_SNAPSHOT_PASS");return 0;
}}
