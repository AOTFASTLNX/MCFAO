#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdint.h>
#include <stdlib.h>

int main(void) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) return 77;
        for (int fixed = 0; fixed < 2; fixed++) {
            NSString *type = fixed ? @"uint3" : @"int3";
            NSString *source = [NSString stringWithFormat:
                @"#include <metal_stdlib>\nusing namespace metal;\n"
                 "struct Input { %@ entity [[attribute(0)]]; };\n"
                 "struct Vary { float4 position [[position]]; float size [[point_size]]; int3 entity [[flat]]; };\n"
                 "vertex Vary v(Input in [[stage_in]], uint id [[vertex_id]]) { Vary o; o.entity = int3(in.entity); o.size=1; o.position=float4((float(id%%256)+0.5)/128-1, 1-(float(id/256)+0.5)/128, 0, 1); return o; }\n"
                 "fragment int4 f(Vary in [[stage_in]]) { return int4(in.entity, 1); }\n", type];
            NSError *error = nil;
            id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
            if (!library) { NSLog(@"%@", error); return 1; }
            MTLRenderPipelineDescriptor *descriptor = [MTLRenderPipelineDescriptor new];
            descriptor.vertexFunction = [library newFunctionWithName:@"v"];
            descriptor.fragmentFunction = [library newFunctionWithName:@"f"];
            descriptor.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA32Sint;
            MTLVertexDescriptor *vertices = [MTLVertexDescriptor vertexDescriptor];
            vertices.attributes[0].format = MTLVertexFormatUShort4;
            vertices.attributes[0].bufferIndex = 0;
            vertices.layouts[0].stride = 8;
            descriptor.vertexDescriptor = vertices;
            id<MTLRenderPipelineState> pipeline = [device newRenderPipelineStateWithDescriptor:descriptor error:&error];
            if (fixed ? !pipeline : pipeline != nil) {
                NSLog(@"Unexpected pipeline result fixed=%d error=%@", fixed, error); return 1;
            }
            if (!fixed && !([error.localizedDescription containsString:@"signed integer type"]
                    || ([error.localizedDescription containsString:@"int3"]
                        && [error.localizedDescription containsString:@"MTLAttributeFormatUShort4"])))
                { NSLog(@"Unexpected failure %@", error); return 1; }
            NSLog(@"METAL_INTEGER_ATTRIBUTE_PASS fixed=%d error=%@", fixed, error);
            if (fixed) {
                const NSUInteger count = 65536;
                id<MTLBuffer> buffer = [device newBufferWithLength:count * 8 options:MTLResourceStorageModeShared];
                if (!buffer) return 1;
                uint16_t *values = buffer.contents;
                for (NSUInteger i = 0; i < count; i++) {
                    values[i*4] = i; values[i*4+1] = 65535-i;
                    values[i*4+2] = i ^ 0x8000; values[i*4+3] = 0x1234;
                }
                MTLTextureDescriptor *textureDescriptor = [MTLTextureDescriptor
                    texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA32Sint width:256 height:256 mipmapped:NO];
                textureDescriptor.storageMode = MTLStorageModeShared;
                textureDescriptor.usage = MTLTextureUsageRenderTarget;
                id<MTLTexture> texture = [device newTextureWithDescriptor:textureDescriptor];
                if (!buffer || !texture) return 1;
                MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
                pass.colorAttachments[0].texture = texture;
                pass.colorAttachments[0].loadAction = MTLLoadActionClear;
                pass.colorAttachments[0].storeAction = MTLStoreActionStore;
                id<MTLCommandQueue> queue = [device newCommandQueue];
                id<MTLCommandBuffer> commands = [queue commandBuffer];
                id<MTLRenderCommandEncoder> encoder = [commands renderCommandEncoderWithDescriptor:pass];
                [encoder setRenderPipelineState:pipeline];
                [encoder setVertexBuffer:buffer offset:0 atIndex:0];
                [encoder drawPrimitives:MTLPrimitiveTypePoint vertexStart:0 vertexCount:count];
                [encoder endEncoding]; [commands commit]; [commands waitUntilCompleted];
                if (commands.status != MTLCommandBufferStatusCompleted) { NSLog(@"%@", commands.error); return 1; }
                int32_t *pixels = calloc(count * 4, sizeof(int32_t));
                if (!pixels) return 1;
                [texture getBytes:pixels bytesPerRow:256*16 fromRegion:MTLRegionMake2D(0,0,256,256) mipmapLevel:0];
                for (NSUInteger i = 0; i < count; i++) {
                    if (pixels[i*4] != (int32_t)i || pixels[i*4+1] != (int32_t)(65535-i)
                            || pixels[i*4+2] != (int32_t)(i ^ 0x8000) || pixels[i*4+3] != 1) {
                        NSLog(@"Entity vertex fetch mismatch at %lu", (unsigned long)i); free(pixels); return 1;
                    }
                }
                free(pixels);
                NSLog(@"METAL_ENTITY_VERTEX_IDS_PASS exactIDs=65536");
            }
        }
    }
    return 0;
}
