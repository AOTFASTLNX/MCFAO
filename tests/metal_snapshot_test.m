// Host-side Metal regression: immutable snapshots survive mutation of source data
// and release of CPU references after encoding. This does not replace iOS tests.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <string.h>
#include <stdint.h>
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
    // A pending draw must still see the old buffer after a partial write has
    // cloned it, replaced the CPU handle, and released the old CPU reference.
    NSString *bufferSource=@"#include <metal_stdlib>\nusing namespace metal; kernel void copyBuffer(device const uint *in [[buffer(0)]], device uint *out [[buffer(1)]], uint i [[thread_position_in_grid]]) { out[i]=in[i]; }";
    id<MTLLibrary> bufferLibrary=[device newLibraryWithSource:bufferSource options:nil error:&error];
    id<MTLFunction> bufferFunction=[bufferLibrary newFunctionWithName:@"copyBuffer"];
    id<MTLComputePipelineState> bufferPipeline=bufferFunction?[device newComputePipelineStateWithFunction:bufferFunction error:&error]:nil;
    if(!bufferPipeline){fprintf(stderr,"%s\n",error.description.UTF8String);return 1;}
    id<MTLBuffer> oldOutput=[device newBufferWithLength:16 options:MTLResourceStorageModeShared];
    id<MTLBuffer> newOutput=[device newBufferWithLength:16 options:MTLResourceStorageModeShared];
    id<MTLCommandBuffer> bufferCommand=[queue commandBuffer];
    @autoreleasepool {
        id<MTLBuffer> old=[device newBufferWithLength:16 options:MTLResourceStorageModeShared];
        uint32_t initial[4]={10,20,30,40};memcpy(old.contents,initial,sizeof(initial));
        id<MTLComputeCommandEncoder> first=[bufferCommand computeCommandEncoder];
        [first setComputePipelineState:bufferPipeline];[first setBuffer:old offset:0 atIndex:0];[first setBuffer:oldOutput offset:0 atIndex:1];
        [first dispatchThreads:MTLSizeMake(4,1,1) threadsPerThreadgroup:MTLSizeMake(1,1,1)];[first endEncoding];
        id<MTLBuffer> replacement=[device newBufferWithLength:16 options:MTLResourceStorageModeShared];
        memcpy(replacement.contents,old.contents,16);((uint32_t *)replacement.contents)[2]=99;
        id<MTLComputeCommandEncoder> second=[bufferCommand computeCommandEncoder];
        [second setComputePipelineState:bufferPipeline];[second setBuffer:replacement offset:0 atIndex:0];[second setBuffer:newOutput offset:0 atIndex:1];
        [second dispatchThreads:MTLSizeMake(4,1,1) threadsPerThreadgroup:MTLSizeMake(1,1,1)];[second endEncoding];
    }
    [bufferCommand commit];[bufferCommand waitUntilCompleted];
    if(bufferCommand.status!=MTLCommandBufferStatusCompleted){fprintf(stderr,"%s\n",bufferCommand.error.description.UTF8String);return 1;}
    uint32_t expectedOld[4]={10,20,30,40},expectedNew[4]={10,20,99,40};
    if(memcmp(oldOutput.contents,expectedOld,16)||memcmp(newOutput.contents,expectedNew,16)){fprintf(stderr,"Buffer snapshot data mismatch\n");return 1;}
    puts("METAL_SNAPSHOT_PASS");return 0;
}}
