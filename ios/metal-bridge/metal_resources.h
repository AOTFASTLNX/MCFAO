#ifndef FAOT_METAL_RESOURCES_H
#define FAOT_METAL_RESOURCES_H

#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#include <jni.h>
#include <stdint.h>

/* Native-side ownership for transient Metal objects.
 *
 * The JNI bridge hands ownership of every created MTLBuffer/MTLTexture to Java as
 * a jlong handle; Java releases it with MetalNative.release(). Per-frame objects
 * created inside bindTexelBuffer (staging buffer, texture view, private snapshot)
 * and cloneBuffer (renamed storage) have no Java owner. On iOS their lifetime was
 * left to an @autoreleasepool plus the command buffer's implicit resource table,
 * which is not a bounded or observable release point. This module makes those
 * releases explicit at GPU completion and keeps a hard cap on concurrent
 * transient bytes so a stalled queue cannot grow without bound.
 *
 * The tracker stores only NSUInteger byte counts, never Metal objects: diagnostics
 * must not add another strong reference to the resources it measures.
 */

typedef NS_ENUM(NSUInteger, FAOTResourceCategory) {
    FAOTResourceBuffer = 0,       /* Java-owned GpuBuffer */
    FAOTResourceTexture = 1,      /* Java-owned GpuTexture / view */
    FAOTResourceSnapshot = 2,     /* cloneBuffer replacement storage */
    FAOTResourceTexelBuffer = 3,  /* bindTexelBuffer staging */
    FAOTResourceTexelTexture = 4, /* bindTexelBuffer linear texture view */
    FAOTResourceStaging = 5,      /* texture upload/readback staging */
    FAOTResourcePool = 6,         /* transient pool recycle entries */
    FAOTResourceCategoryCount = 7
};

typedef struct {
    uint64_t allocatedCount, allocatedBytes, freedCount, freedBytes, liveBytes;
} FAOTResourceCounters;

@interface FAOTResourceTracker : NSObject
- (instancetype)initWithDevice:(id<MTLDevice>)device maxTransientBytes:(NSUInteger)cap;
@property(nonatomic,readonly) id<MTLDevice> device;
@property(nonatomic,readonly) NSUInteger maxTransientBytes;
/* Requested backing lengths, counted once across pool/Java/GPU ownership.
 * Separate from total live resources and MTLDevice.currentAllocatedSize. */
@property(nonatomic,readonly) NSUInteger transientAllocatedBytes;

/* Track a Java-owned allocation. Call releaseTracked:bytes: from the matching
 * MetalNative.release() so live bytes fall when ownership is dropped. */
- (void)track:(FAOTResourceCategory)category bytes:(NSUInteger)bytes;
- (void)releaseTracked:(FAOTResourceCategory)category bytes:(NSUInteger)bytes;

/* Record a failed allocation with the requested size and category. The returned
 * snapshot is a plain NSString and holds no Metal objects. */
- (NSString *)recordFailure:(FAOTResourceCategory)category bytes:(NSUInteger)bytes;

/* Install the completion mailbox before commit. Later Java releases may enqueue
 * reclamation after commit or completion without adding another Metal handler. */
- (void)prepareCommandBuffer:(id<MTLCommandBuffer>)commands;

/* Defer an owning reference until the GPU finishes the given command buffer.
 * A mailbox retains the reclamation action until its preinstalled handler runs.
 * Diagnostics retain no resources. */
- (void)deferUntilCompleted:(id<MTLCommandBuffer>)commands object:(id)object category:(FAOTResourceCategory)category bytes:(NSUInteger)bytes;

/* Bounded recycling of transient shared buffers. A miss allocates a new buffer
 * (tracked as texel), a hit reuses one without allocating. */
- (id<MTLBuffer>)acquireTransientBufferOfLength:(NSUInteger)length;
- (void)recycleTransientBuffer:(id<MTLBuffer>)buffer commandBuffer:(id<MTLCommandBuffer>)commands;
/* Recycle a buffer whose +1 retain comes from a released JNI handle. The
 * completion handler owns the object; counters were already released. A nil
 * command buffer means there is no pending GPU owner and recycles immediately. */
- (void)recycleOwnedBuffer:(id<MTLBuffer>)buffer commandBuffer:(id<MTLCommandBuffer>)commands;

- (NSUInteger)inFlightCommandBuffers;
- (void)noteCommandBufferCommitted;
- (void)noteCommandBufferCompleted;
- (NSUInteger)currentAllocatedBytes;
- (NSString *)memorySnapshot;   /* [MetalMemory] summary, no Metal objects retained */
- (void)maybeLogSummary;        /* at most once per 5 seconds */
- (void)close;                 /* drop pool; requires no GPU work in flight */
@end

#endif
