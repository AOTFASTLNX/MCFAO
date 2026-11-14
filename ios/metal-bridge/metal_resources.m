#import "metal_resources.h"
#import <QuartzCore/CAMetalLayer.h>
#include <stdio.h>
#include <string.h>
#import <objc/runtime.h>

/* Owned by the command buffer, never owns the command buffer. Actions retain
 * resources only until its preinstalled completion handler drains the mailbox. */
@interface FAOTCompletionMailbox : NSObject
@property(nonatomic) BOOL completed;
@property(nonatomic,strong) NSMutableArray *actions;
- (void)enqueue:(dispatch_block_t)action;
- (void)finish;
@end
@implementation FAOTCompletionMailbox
- (instancetype)init {self=[super init];if(self)_actions=[NSMutableArray new];return self;}
- (void)enqueue:(dispatch_block_t)action {
    @synchronized(self){if(!_completed){[_actions addObject:[action copy]];return;}}
    action();
}
- (void)finish {
    NSArray *ready;
    @synchronized(self){_completed=YES;ready=[_actions copy];[_actions removeAllObjects];}
    for(dispatch_block_t action in ready)action();
}
@end

static char completionMailboxKey;
static FAOTCompletionMailbox *completionMailbox(id<MTLCommandBuffer> commands) {
    @synchronized(commands){
        FAOTCompletionMailbox *mailbox=objc_getAssociatedObject(commands,&completionMailboxKey);
        if(!mailbox){
            mailbox=[FAOTCompletionMailbox new];
            NSCAssert(commands.status<MTLCommandBufferStatusCommitted,
                      @"Resource completion mailbox must be installed before commit");
            objc_setAssociatedObject(commands,&completionMailboxKey,mailbox,OBJC_ASSOCIATION_RETAIN_NONATOMIC);
            [commands addCompletedHandler:^(id<MTLCommandBuffer> finished){(void)finished;[mailbox finish];}];
        }
        return mailbox;
    }
}

/* Hard ceiling for transient (non Java-owned) Metal allocations. 64 MiB is well
 * above one frame of cloud texel + vertex snapshots (~0.3 MiB) and below the
 * growth that exhausted the GPU on device. Exceeding it triggers one bounded
 * wait for GPU completion, never an unbounded retry. */
#define FAOT_TRANSIENT_BUDGET_BYTES ((NSUInteger)64 * 1024 * 1024)
#define FAOT_POOL_MAX_ENTRIES 64

static const char *categoryNames[FAOTResourceCategoryCount] = {
    "buffer", "texture", "snapshot", "texel_buffer", "texel_view", "staging", "pool"
};

@interface FAOTResourceTracker () {
    id<MTLDevice> _device;
    FAOTResourceCounters _counters[FAOTResourceCategoryCount];
    uint64_t _peakLiveBytes, _committed, _completed, _peakInFlight;
    uint64_t _allocFailures, _lastFailureBytes;
    FAOTResourceCategory _lastFailureCategory;
    NSMutableArray<id<MTLBuffer>> *_pool;
    NSUInteger _poolEntries, _poolBytes;
    NSUInteger _maxTransientBytes;
    NSUInteger _transientBytes; /* backing storage, including idle and GPU-held snapshots */
    double _started, _lastSummary;
    dispatch_group_t _drain;
    BOOL _closed;
    NSObject *_lock;
}
@property(nonatomic,readonly) NSObject *lock;
@end

@implementation FAOTResourceTracker
@synthesize lock=_lock;

- (instancetype)initWithDevice:(id<MTLDevice>)device maxTransientBytes:(NSUInteger)cap {
    self=[super init];
    if(!self)return nil;
    _device=device;
    _maxTransientBytes=cap?cap:FAOT_TRANSIENT_BUDGET_BYTES;
    _pool=[NSMutableArray arrayWithCapacity:FAOT_POOL_MAX_ENTRIES];
    _drain=dispatch_group_create();
    _lock=[NSObject new];
    _started=CACurrentMediaTime();_lastSummary=_started;
    _lastFailureCategory=FAOTResourceBuffer;
    return self;
}
- (id<MTLDevice>)device{return _device;}
- (NSUInteger)maxTransientBytes{return _maxTransientBytes;}
- (NSUInteger)transientAllocatedBytes {@synchronized(_lock){return _transientBytes;}}
- (void)prepareCommandBuffer:(id<MTLCommandBuffer>)commands {(void)completionMailbox(commands);}

- (uint64_t)totalLiveBytes {
    uint64_t total=0;for(NSUInteger i=0;i<FAOTResourceCategoryCount;i++)total+=_counters[i].liveBytes;return total;
}
- (void)notePeak {
    uint64_t live=[self totalLiveBytes];if(live>_peakLiveBytes)_peakLiveBytes=live;
}
- (void)track:(FAOTResourceCategory)category bytes:(NSUInteger)bytes {
    @synchronized(_lock){
        FAOTResourceCounters *c=&_counters[category];
        c->allocatedCount++;c->allocatedBytes+=bytes;c->liveBytes+=bytes;[self notePeak];
    }
}
- (void)releaseTracked:(FAOTResourceCategory)category bytes:(NSUInteger)bytes {
    @synchronized(_lock){
        FAOTResourceCounters *c=&_counters[category];
        c->freedCount++;c->freedBytes+=bytes;
        c->liveBytes=(bytes>c->liveBytes)?0:c->liveBytes-bytes;
    }
}
- (NSString *)recordFailure:(FAOTResourceCategory)category bytes:(NSUInteger)bytes {
    NSString *snapshot;
    @synchronized(_lock){
        _allocFailures++;_lastFailureBytes=bytes;_lastFailureCategory=category;
        snapshot=[self memorySnapshotLocked];
    }
    fprintf(stderr,"[MetalAllocFailure] category=%s requested_bytes=%lu %s\n",
            categoryNames[category],(unsigned long)bytes,snapshot.UTF8String);
    return snapshot;
}

- (void)deferUntilCompleted:(id<MTLCommandBuffer>)commands object:(id)object category:(FAOTResourceCategory)category bytes:(NSUInteger)bytes {
    if(!object)return;
    __block id held=object;
    dispatch_group_enter(_drain);
    [completionMailbox(commands) enqueue:^{
        held=nil;                       /* release exactly at GPU completion */
        [self releaseTracked:category bytes:bytes];
        dispatch_group_leave(self->_drain);
    }];
}

- (id<MTLBuffer>)acquireTransientBufferOfLength:(NSUInteger)length {
    if(!length)return nil;
    @synchronized(_lock){
        if(_closed)return nil;
        NSUInteger found=NSNotFound;
        for(NSUInteger i=0;i<_pool.count;i++)if(_pool[i].length==length){found=i;break;}
        if(found!=NSNotFound){
            id<MTLBuffer> reused=_pool[found];[_pool removeObjectAtIndex:found];
            _poolEntries--;_poolBytes-=length;
            _counters[FAOTResourcePool].freedCount++;_counters[FAOTResourcePool].freedBytes+=length;
            _counters[FAOTResourcePool].liveBytes-=length;
            /* The buffer stays allocated; it moves from the pool back to the
             * texel category without a new allocation or a free. */
            _counters[FAOTResourceTexelBuffer].liveBytes+=length;
            return reused;
        }
    }
    /* Persistent textures and buffers are not part of this transient cap.
     * Reserve backing bytes under the lock, including while newBuffer runs,
     * so concurrent misses cannot each claim the same remaining capacity. */
    BOOL reserved=NO;
    for(NSUInteger attempt=0;attempt<2 && length<=_maxTransientBytes;attempt++){
        @synchronized(_lock){
            if(_closed)return nil;
            if(length>_maxTransientBytes-_transientBytes){
                /* Only idle buffers can be discarded; GPU-held storage remains
                 * charged until its own completion handler releases it. */
                _counters[FAOTResourcePool].freedCount+=_poolEntries;
                _counters[FAOTResourcePool].freedBytes+=_poolBytes;
                _counters[FAOTResourcePool].liveBytes=0;
                _transientBytes-=_poolBytes;
                [_pool removeAllObjects];_poolEntries=0;_poolBytes=0;
            }
            if(length<=_maxTransientBytes-_transientBytes){
                _transientBytes+=length;reserved=YES;
            }
        }
        if(reserved)break;
        if(attempt==0)dispatch_group_wait(_drain,dispatch_time(DISPATCH_TIME_NOW,(int64_t)1*NSEC_PER_SEC));
    }
    if(!reserved){[self recordFailure:FAOTResourceTexelBuffer bytes:length];return nil;}
    id<MTLBuffer> buffer=[_device newBufferWithLength:length options:MTLResourceStorageModeShared];
    if(!buffer){
        @synchronized(_lock){_transientBytes-=length;}
        [self recordFailure:FAOTResourceTexelBuffer bytes:length];return nil;
    }
    [self track:FAOTResourceTexelBuffer bytes:length];
    return buffer;
}

- (void)recycleTransientBuffer:(id<MTLBuffer>)buffer commandBuffer:(id<MTLCommandBuffer>)commands {
    if(!buffer)return;
    NSUInteger length=buffer.length;
    __block id held=buffer;
    dispatch_group_enter(_drain);
    [completionMailbox(commands) enqueue:^{
        id<MTLBuffer> value=held;held=nil;
        @synchronized(self->_lock){
            FAOTResourceCounters *c=&self->_counters[FAOTResourceTexelBuffer];
            c->liveBytes=(length>c->liveBytes)?0:c->liveBytes-length;
            if(!self->_closed && self->_pool.count<FAOT_POOL_MAX_ENTRIES){
                [self->_pool addObject:value];self->_poolEntries++;self->_poolBytes+=length;
                self->_counters[FAOTResourcePool].allocatedCount++;
                self->_counters[FAOTResourcePool].allocatedBytes+=length;
                self->_counters[FAOTResourcePool].liveBytes+=length;
                [self notePeak];
            }else self->_transientBytes-=length;
        }
        dispatch_group_leave(self->_drain);
    }];
}

- (void)recycleOwnedBuffer:(id<MTLBuffer>)buffer commandBuffer:(id<MTLCommandBuffer>)commands {
    if(!buffer)return;
    NSUInteger length=buffer.length;
    __block id held=buffer;
    dispatch_group_enter(_drain);
    void (^recycle)(id<MTLCommandBuffer>)=^(id<MTLCommandBuffer> finished){
        (void)finished;
        id<MTLBuffer> value=held;held=nil;
        @synchronized(self->_lock){
            if(!self->_closed && self->_pool.count<FAOT_POOL_MAX_ENTRIES){
                [self->_pool addObject:value];self->_poolEntries++;self->_poolBytes+=length;
                self->_counters[FAOTResourcePool].allocatedCount++;
                self->_counters[FAOTResourcePool].allocatedBytes+=length;
                self->_counters[FAOTResourcePool].liveBytes+=length;
                [self notePeak];
            }else self->_transientBytes-=length;
        }
        dispatch_group_leave(self->_drain);
    };
    if(commands)[completionMailbox(commands) enqueue:^{recycle(nil);}];else recycle(nil);
}

- (void)noteCommandBufferCommitted {
    @synchronized(_lock){
        _committed++;uint64_t inFlight=_committed-_completed;
        if(inFlight>_peakInFlight)_peakInFlight=inFlight;
    }
}
- (void)noteCommandBufferCompleted {
    @synchronized(_lock){_completed++;}
}
- (NSUInteger)inFlightCommandBuffers {
    @synchronized(_lock){return (NSUInteger)(_committed>_completed?_committed-_completed:0);}
}
- (NSUInteger)currentAllocatedBytes {return (NSUInteger)[_device currentAllocatedSize];}

- (NSString *)memorySnapshotLocked {
    NSMutableString *line=[NSMutableString stringWithFormat:
        @"[MetalMemory] elapsed_s=%.1f live_bytes=%llu peak_live_bytes=%llu device_bytes=%llu in_flight=%llu peak_in_flight=%llu alloc_failures=%llu last_failure_category=%s last_failure_bytes=%llu",
        CACurrentMediaTime()-_started,(unsigned long long)[self totalLiveBytes],
        (unsigned long long)_peakLiveBytes,(unsigned long long)[self currentAllocatedBytes],
        (unsigned long long)(_committed>_completed?_committed-_completed:0),
        (unsigned long long)_peakInFlight,(unsigned long long)_allocFailures,
        categoryNames[_lastFailureCategory],(unsigned long long)_lastFailureBytes];
    for(NSUInteger i=0;i<FAOTResourceCategoryCount;i++){
        FAOTResourceCounters *c=&_counters[i];
        [line appendFormat:@" %s_alloc_count=%llu %s_alloc_bytes=%llu %s_free_count=%llu %s_free_bytes=%llu %s_live_bytes=%llu",
            categoryNames[i],(unsigned long long)c->allocatedCount,categoryNames[i],(unsigned long long)c->allocatedBytes,
            categoryNames[i],(unsigned long long)c->freedCount,categoryNames[i],(unsigned long long)c->freedBytes,
            categoryNames[i],(unsigned long long)c->liveBytes];
    }
    [line appendFormat:@" pool_entries=%lu pool_bytes=%lu transient_budget_bytes=%lu transient_allocated_bytes=%lu",
        (unsigned long)_poolEntries,(unsigned long)_poolBytes,(unsigned long)_maxTransientBytes,(unsigned long)_transientBytes];
    return line;
}
- (NSString *)memorySnapshot {
    @synchronized(_lock){return [self memorySnapshotLocked];}
}
- (void)maybeLogSummary {
    NSString *line=nil;
    @synchronized(_lock){
        double now=CACurrentMediaTime();
        if(now-_lastSummary<5.0)return;
        _lastSummary=now;line=[self memorySnapshotLocked];
    }
    fprintf(stderr,"%s\n",line.UTF8String);
}
- (void)close {
    @synchronized(_lock){
        if(_closed)return;_closed=YES;
        _counters[FAOTResourcePool].freedCount+=_poolEntries;
        _counters[FAOTResourcePool].freedBytes+=_poolBytes;
        _counters[FAOTResourcePool].liveBytes=0;
        _transientBytes-=_poolBytes;
        [_pool removeAllObjects];_poolEntries=0;_poolBytes=0;
    }
    fprintf(stderr,"%s\n",[self memorySnapshot].UTF8String);
}
@end
