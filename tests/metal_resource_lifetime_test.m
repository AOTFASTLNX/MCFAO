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

static void testPersistentResourcesDoNotConsumeTransientBudget(id<MTLDevice> device) {
    @autoreleasepool {
        const NSUInteger cap = 1024 * 1024;
        FAOTResourceTracker *tracker = [[FAOTResourceTracker alloc] initWithDevice:device maxTransientBytes:cap];
        MTLTextureDescriptor *desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:1024 height:1024 mipmapped:NO];
        desc.storageMode = MTLStorageModePrivate;
        id<MTLTexture> persistent = [device newTextureWithDescriptor:desc];
        check(persistent != nil, "persistent startup texture must allocate");
        [tracker track:FAOTResourceTexture bytes:persistent.allocatedSize];
        check(persistent.allocatedSize > cap, "regression fixture must exceed transient budget with persistent storage");
        id<MTLBuffer> upload = [tracker acquireTransientBufferOfLength:cap];
        check(upload != nil, "persistent textures must not reject an in-budget startup upload");
        if (upload) {
            id<MTLCommandQueue> queue = [device newCommandQueue];
            id<MTLCommandBuffer> cb = [queue commandBuffer];
            [tracker recycleTransientBuffer:upload commandBuffer:cb];
            [cb commit]; [cb waitUntilCompleted];
            check(tracker.transientAllocatedBytes == cap, "recycling at the cap must preserve one backing allocation");
            check([[tracker memorySnapshot] containsString:@"pool_entries=1"], "full-budget buffer must be reusable");
            id<MTLBuffer> reused = [tracker acquireTransientBufferOfLength:cap];
            check(reused == upload, "exact-size reuse must not allocate or count bytes twice");
            [tracker releaseTracked:FAOTResourceTexelBuffer bytes:cap];
            [tracker recycleOwnedBuffer:reused commandBuffer:nil];
            id<MTLBuffer> smaller = [tracker acquireTransientBufferOfLength:cap / 2];
            check(smaller != nil, "idle storage must be evicted to satisfy a different size");
            check(tracker.transientAllocatedBytes == cap / 2, "trim must remove idle backing bytes");
            [tracker releaseTracked:FAOTResourceTexelBuffer bytes:cap / 2];
            [tracker recycleOwnedBuffer:smaller commandBuffer:nil];
        }
        [tracker releaseTracked:FAOTResourceTexture bytes:persistent.allocatedSize];
        [tracker close];
        check(tracker.transientAllocatedBytes == 0, "close must release all idle budget");
    }
}

static void testReleasedSnapshotStaysChargedUntilCompletion(id<MTLDevice> device) {
    @autoreleasepool {
        const NSUInteger cap = 1024 * 1024;
        FAOTResourceTracker *tracker = [[FAOTResourceTracker alloc] initWithDevice:device maxTransientBytes:cap];
        id<MTLBuffer> buffer = [tracker acquireTransientBufferOfLength:cap];
        check(buffer != nil, "snapshot fixture buffer must allocate");
        if (!buffer) { [tracker close]; return; }
        [tracker releaseTracked:FAOTResourceTexelBuffer bytes:cap];
        [tracker track:FAOTResourceSnapshot bytes:cap];
        [tracker releaseTracked:FAOTResourceSnapshot bytes:cap];
        id<MTLCommandQueue> queue = [device newCommandQueue];
        id<MTLSharedEvent> event = [device newSharedEvent];
        id<MTLCommandBuffer> cb = [queue commandBuffer];
        [cb encodeWaitForEvent:event value:1];
        [tracker recycleOwnedBuffer:buffer commandBuffer:cb];
        [cb commit];
        check(tracker.transientAllocatedBytes == cap, "released snapshot must remain charged while GPU work is delayed");
        check([[tracker memorySnapshot] containsString:@"pool_entries=0"], "in-flight storage must not enter the idle pool");
        event.signaledValue = 1;
        [cb waitUntilCompleted];
        check(tracker.transientAllocatedBytes == cap, "GPU completion transfers storage without double counting");
        [tracker close];
        check(tracker.transientAllocatedBytes == 0, "completed snapshot must be reclaimed");
    }
}

static void testLateConcurrentAndOutOfOrderCompletion(id<MTLDevice> device) {
    @autoreleasepool {
        const NSUInteger count=16, length=4096;
        FAOTResourceTracker *tracker=[[FAOTResourceTracker alloc] initWithDevice:device maxTransientBytes:count*length];
        id<MTLCommandQueue> slowQueue=[device newCommandQueue], fastQueue=[device newCommandQueue];
        id<MTLCommandBuffer> slow=[slowQueue commandBuffer], fast=[fastQueue commandBuffer];
        id<MTLSharedEvent> event=[device newSharedEvent];
        [slow encodeWaitForEvent:event value:1];
        [tracker prepareCommandBuffer:slow];[tracker prepareCommandBuffer:fast];
        NSMutableArray *buffers=[NSMutableArray new];
        for(NSUInteger i=0;i<count;i++)[buffers addObject:[tracker acquireTransientBufferOfLength:length]];
        [slow commit];[fast commit];[fast waitUntilCompleted];
        dispatch_apply(count,dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^(size_t i){
            [tracker releaseTracked:FAOTResourceTexelBuffer bytes:length];
            [tracker recycleOwnedBuffer:buffers[i] commandBuffer:(i%2?fast:slow)];
        });
        check([[tracker memorySnapshot] containsString:@"pool_entries=8"], "only completed queue resources may pool after late concurrent release");
        check(tracker.transientAllocatedBytes==count*length,"delayed queue storage must remain charged");
        event.signaledValue=1;[slow waitUntilCompleted];
        check([[tracker memorySnapshot] containsString:@"pool_entries=16"],"out-of-order queues must each reclaim exactly once");
        for(NSUInteger round=0;round<32;round++){
            id<MTLCommandBuffer> cb=[fastQueue commandBuffer];
            [tracker prepareCommandBuffer:cb];[cb commit];
            dispatch_apply(count,dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^(size_t i){
                (void)i;
                id<MTLBuffer> buffer=[tracker acquireTransientBufferOfLength:length];
                [tracker releaseTracked:FAOTResourceTexelBuffer bytes:length];
                [tracker recycleOwnedBuffer:buffer commandBuffer:cb];
            });
            [cb waitUntilCompleted];
        }
        [tracker close];
        check(tracker.transientAllocatedBytes==0,"completion races must drain without leaks or double recycling");
        puts("METAL_LATE_COMPLETION_PASS concurrent=16 queues=2 races=32");
    }
}

static void testConcurrentReservations(id<MTLDevice> device) {
    @autoreleasepool {
        const NSUInteger cap = 1024 * 1024, length = cap / 8;
        FAOTResourceTracker *tracker = [[FAOTResourceTracker alloc] initWithDevice:device maxTransientBytes:cap];
        NSMutableArray<id<MTLBuffer>> *buffers = [NSMutableArray array];
        dispatch_apply(16, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^(size_t index) {
            (void)index;
            @autoreleasepool {
                id<MTLBuffer> buffer = [tracker acquireTransientBufferOfLength:length];
                if (buffer) { @synchronized(buffers) { [buffers addObject:buffer]; } }
            }
        });
        check(buffers.count == 8, "concurrent requests must reserve no more than the cap");
        check(tracker.transientAllocatedBytes == cap, "all concurrent reservations must be accounted");
        for (id<MTLBuffer> buffer in buffers) {
            [tracker releaseTracked:FAOTResourceTexelBuffer bytes:length];
            [tracker recycleOwnedBuffer:buffer commandBuffer:nil];
        }
        [tracker close];
        check(tracker.transientAllocatedBytes == 0, "concurrent allocations must be reclaimable");
    }
}

static void testThreeFramesSplitOnSameQueue(id<MTLDevice> device) {
    @autoreleasepool {
        FAOTResourceTracker *tracker=[[FAOTResourceTracker alloc] initWithDevice:device maxTransientBytes:1024*1024];
        id<MTLCommandQueue> queue=[device newCommandQueue];
        id<MTLSharedEvent> gate=[device newSharedEvent];
        NSMutableArray<id<MTLBuffer>> *outputs=[NSMutableArray new];
        NSMutableArray<id<MTLCommandBuffer>> *tails=[NSMutableArray new];
        // Delay all GPU work until three complete frame pairs have been queued.
        // CPU submission must not need a completion wait to order either pass.
        for(NSUInteger frame=0;frame<3;frame++){
            id<MTLBuffer> source=[tracker acquireTransientBufferOfLength:256];
            memset(source.contents,(int)(frame+1),256);
            id<MTLBuffer> intermediate=[device newBufferWithLength:256 options:MTLResourceStorageModePrivate];
            id<MTLBuffer> output=[device newBufferWithLength:256 options:MTLResourceStorageModeShared];
            id<MTLCommandBuffer> render=[queue commandBuffer];
            [tracker prepareCommandBuffer:render];
            if(frame==0)[render encodeWaitForEvent:gate value:1];
            id<MTLBlitCommandEncoder> first=[render blitCommandEncoder];
            [first copyFromBuffer:source sourceOffset:0 toBuffer:intermediate destinationOffset:0 size:256];
            [first endEncoding];[render commit];
            [tracker releaseTracked:FAOTResourceTexelBuffer bytes:source.allocatedSize];
            [tracker recycleOwnedBuffer:source commandBuffer:render];
            id<MTLCommandBuffer> present=[queue commandBuffer];
            [tracker prepareCommandBuffer:present];
            id<MTLBlitCommandEncoder> second=[present blitCommandEncoder];
            [second copyFromBuffer:intermediate sourceOffset:0 toBuffer:output destinationOffset:0 size:256];
            [second endEncoding];[present commit];
            [outputs addObject:output];[tails addObject:present];
        }
        check([[tracker memorySnapshot] containsString:@"pool_entries=0"],
              "three delayed frames must not recycle GPU-held backing");
        gate.signaledValue=1;
        for(NSUInteger frame=0;frame<3;frame++){
            id<MTLCommandBuffer> tail=tails[frame];[tail waitUntilCompleted];
            check(tail.status==MTLCommandBufferStatusCompleted,
                  "same-queue split presentation must complete");
            const uint8_t *bytes=[outputs[frame] contents];
            for(NSUInteger i=0;i<256;i++)if(bytes[i]!=frame+1){
                check(NO,"split presentation must observe its own rendered data");break;
            }
        }
        [tracker close];
        check(tracker.transientAllocatedBytes==0,
              "three-frame split submission must release all backing on close");
    }
}

int main(void) { @autoreleasepool {
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (!device) { fprintf(stderr, "SKIP: no Metal device\n"); return 77; }
    testPersistentResourcesDoNotConsumeTransientBudget(device);
    testReleasedSnapshotStaysChargedUntilCompletion(device);
    testConcurrentReservations(device);
    testLateConcurrentAndOutOfOrderCompletion(device);
    testThreeFramesSplitOnSameQueue(device);
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
