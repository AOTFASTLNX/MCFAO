// Host-side lifecycle test for the native Metal resource manager.
// Drives the same transient-buffer pattern as bindTexelBuffer/cloneBuffer with
// real command buffers and asserts that live bytes and device allocations
// stabilize after warmup instead of growing with frame count.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <dispatch/dispatch.h>
#include <unistd.h>
#include "../ios/metal-bridge/metal_resources.h"

static int failures = 0;
static void check(BOOL condition, const char *message) {
    if (!condition) { fprintf(stderr, "FAIL: %s\n", message); failures++; }
}

int main(void) { @autoreleasepool {
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (!device) { fprintf(stderr, "SKIP: no Metal device\n"); return 77; }
    FAOTResourceTracker *tracker = [[FAOTResourceTracker alloc] initWithDevice:device maxTransientBytes:8 * 1024 * 1024];
    id<MTLCommandQueue> queue = [device newCommandQueue];
    dispatch_semaphore_t slots = dispatch_semaphore_create(2);

    const NSUInteger texelStride = 256 * 1024;   // one cloud texel snapshot
    const NSUInteger snapshotSize = 24 * 1024;   // one cloned vertex/uniform buffer
    const NSUInteger frames = 1200;
    NSUInteger peakLive = 0;

    for (NSUInteger frame = 1; frame <= frames; frame++) {
        @autoreleasepool {
            dispatch_semaphore_wait(slots, DISPATCH_TIME_FOREVER);
            id<MTLCommandBuffer> cb = [queue commandBuffer];

            // bindTexelBuffer: bounded transient + view held until GPU completion.
            id<MTLBuffer> staging = [tracker acquireTransientBufferOfLength:texelStride];
            check(staging != nil, "transient texel buffer must be available");
            memset(staging.contents, (int)(frame & 0xff), texelStride);
            MTLTextureDescriptor *desc = [MTLTextureDescriptor new];
            desc.textureType = MTLTextureTypeTextureBuffer;
            desc.pixelFormat = MTLPixelFormatR8Unorm;
            desc.width = texelStride; desc.height = 1;
            desc.storageMode = MTLStorageModeShared;
            desc.usage = MTLTextureUsageShaderRead;
            id<MTLTexture> view = [staging newTextureWithDescriptor:desc offset:0 bytesPerRow:texelStride];
            check(view != nil, "shared texture-buffer view must be available");
            [tracker track:FAOTResourceTexelTexture bytes:view.allocatedSize];
            [tracker deferUntilCompleted:cb object:view category:FAOTResourceTexelTexture bytes:view.allocatedSize];
            [tracker recycleTransientBuffer:staging commandBuffer:cb];

            // cloneBuffer: Java-owned replacement, released at GPU completion.
            id<MTLBuffer> replacement = [tracker acquireTransientBufferOfLength:snapshotSize];
            check(replacement != nil, "transient snapshot buffer must be available");
            memset(replacement.contents, (int)(frame & 0xff), snapshotSize);
            [tracker releaseTracked:FAOTResourceTexelBuffer bytes:replacement.allocatedSize];
            [tracker track:FAOTResourceSnapshot bytes:replacement.allocatedSize];
            /* Mirror MetalNative.release(): counters already released, move the
             * +1 retain into a completion handler that returns it to the pool. */
            [tracker releaseTracked:FAOTResourceSnapshot bytes:replacement.allocatedSize];
            [tracker recycleOwnedBuffer:replacement commandBuffer:cb];

            // Encode real GPU work that references the transient objects.
            MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
            id<MTLTexture> target = [device newTextureWithDescriptor:^{
                MTLTextureDescriptor *t = [MTLTextureDescriptor new];
                t.pixelFormat = MTLPixelFormatRGBA8Unorm; t.width = 32; t.height = 32;
                t.storageMode = MTLStorageModePrivate; t.usage = MTLTextureUsageRenderTarget;
                return t;
            }()];
            pass.colorAttachments[0].texture = target;
            pass.colorAttachments[0].loadAction = MTLLoadActionDontCare;
            pass.colorAttachments[0].storeAction = MTLStoreActionStore;
            id<MTLRenderCommandEncoder> encoder = [cb renderCommandEncoderWithDescriptor:pass];
            [encoder setFragmentTexture:view atIndex:0];
            [encoder setVertexBuffer:replacement offset:0 atIndex:0];
            [encoder endEncoding];

            [tracker noteCommandBufferCommitted];
            dispatch_semaphore_t localSlots = slots;
            [cb addCompletedHandler:^(id<MTLCommandBuffer> finished) {
                (void)finished;
                [tracker noteCommandBufferCompleted];
                dispatch_semaphore_signal(localSlots);
            }];
            [cb commit];

            NSUInteger live = [[tracker memorySnapshot] containsString:@"live_bytes="] ? 0 : 0;
            (void)live;
            NSString *summary = [tracker memorySnapshot];
            NSRange range = [summary rangeOfString:@"live_bytes="];
            if (range.location != NSNotFound) {
                NSScanner *scanner = [NSScanner scannerWithString:[summary substringFromIndex:NSMaxRange(range)]];
                unsigned long long value = 0;
                if ([scanner scanUnsignedLongLong:&value] && value > peakLive) peakLive = (NSUInteger)value;
            }
            if (frame % 200 == 0) {
                printf("frame=%lu device_bytes=%lu peak_live=%lu\n",
                       (unsigned long)frame, (unsigned long)[device currentAllocatedSize], (unsigned long)peakLive);
            }
        }
        usleep(200);
    }

    NSString *snapshot = [tracker memorySnapshot];
    fprintf(stderr, "%s\n", snapshot.UTF8String);
    NSUInteger deviceBytes = [device currentAllocatedSize];
    check(peakLive <= 8 * 1024 * 1024, "peak live bytes must stay under the transient cap");
    check(deviceBytes < 32 * 1024 * 1024, "device allocations must stabilize, not grow per frame");
    check([tracker inFlightCommandBuffers] <= 2, "in-flight command buffers must stay bounded");
    check([snapshot containsString:@"alloc_failures=0"], "no allocation failure expected within the cap");
    [tracker close];
    if (failures) { fprintf(stderr, "METAL_RESOURCE_LIFETIME_FAIL failures=%d\n", failures); return 1; }
    puts("METAL_RESOURCE_LIFETIME_PASS");
    return 0;
}}
