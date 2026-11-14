#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>
#import <GameController/GameController.h>
#import <os/lock.h>
#include <math.h>
#include <string.h>
#include "pointer_motion.h"
#include "glfw_lite.h"
#include "input_mapping.h"

enum { CONTROL_BREAK=-1, CONTROL_PLACE=-2, CONTROL_PREVIOUS=-3, CONTROL_NEXT=-4, CONTROL_PICK=-5,
       CONTROL_ESCAPE=256, CONTROL_DEBUG=292 /* GLFW_KEY_F3 */ };
/* Private special band, identical to FAOTControlLayout.h in C0Harness. */
enum { CONTROL_KEYBOARD=-101, CONTROL_TOGGLECTRL=-102, CONTROL_PRIMARY=-103, CONTROL_SECONDARY=-104,
       CONTROL_VIRTUALMOUSE=-105, CONTROL_MIDDLE=-106, CONTROL_SCROLLUP=-107, CONTROL_SCROLLDOWN=-108 };
static void onMain(dispatch_block_t block) {
    if (NSThread.isMainThread) block(); else dispatch_sync(dispatch_get_main_queue(),block);
}
static UIWindowScene *activeScene(void) {
    UIWindowScene *inactive=nil;
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
        if (![scene isKindOfClass:UIWindowScene.class]) continue;
        if (scene.activationState==UISceneActivationStateForegroundActive) return (UIWindowScene *)scene;
        // At cold launch the scene can still be inactive while the first frame is requested.
        if (!inactive && scene.activationState==UISceneActivationStateForegroundInactive) inactive=(UIWindowScene *)scene;
    }
    return inactive;
}

/* Documents/controlmap/<FAOTControlLayout>.json - the same file the launcher editor writes. */
static NSString *FAOTLayoutPath(void) {
    NSString *name = [NSUserDefaults.standardUserDefaults stringForKey:@"FAOTControlLayout"];
    if (!name.length) name = @"default";
    NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    return [[documents stringByAppendingPathComponent:@"controlmap"]
            stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"json"]];
}

/* The XCUITest suite addresses controls by these labels, so keep them stable for the keys the
   tests press even when a user renames or reorders a layout. */
static NSString *FAOTAccessibilityLabel(NSInteger code, NSString *fallback) {
    switch (code) {
        case 'W': return @"Move forward";
        case 'A': return @"Move left";
        case 'S': return @"Move backward";
        case 'D': return @"Move right";
        case CONTROL_ESCAPE: return @"Pause";
        case CONTROL_PRIMARY: case CONTROL_BREAK: return @"Break or attack";
        case CONTROL_SECONDARY: case CONTROL_PLACE: return @"Place or use";
        case CONTROL_MIDDLE: case CONTROL_PICK: return @"Pick block";
        case CONTROL_DEBUG: return @"Toggle debug screen";
        case 'E': return @"Inventory";
        case ' ': return @"Jump";
        case CONTROL_PREVIOUS: return @"Previous hotbar slot";
        case CONTROL_NEXT: return @"Next hotbar slot";
        default: return fallback.length ? fallback : [NSString stringWithFormat:@"key %ld", (long)code];
    }
}

/* Used when no layout file exists yet: the thirteen controls this surface shipped with. */
static NSArray<NSDictionary *> *FAOTBuiltinControlModels(void) {
    const CGFloat W = 844.0, H = 390.0, size = 44.0, step = 48.0, left = 8.0;
    const CGFloat right = W - size - 8.0, bottom = H - size - 32.0;
    struct { const char *title; const char *label; NSInteger code; CGFloat x, y, s; } rows[] = {
        {"^", "Move forward", 'W', left + step, bottom - 2 * step, size},
        {"<", "Move left", 'A', left, bottom - step, size},
        {"v", "Move backward", 'S', left + step, bottom - step, size},
        {">", "Move right", 'D', left + 2 * step, bottom - step, size},
        {"Jump", "Jump", ' ', right, bottom - step, size},
        {"Items", "Inventory", 'E', right - step, bottom - step, size},
        {"Place", "Place or use", CONTROL_SECONDARY, right, bottom - 2 * step, size},
        {"Break", "Break or attack", CONTROL_PRIMARY, right - step, bottom - 2 * step, size},
        {"<", "Previous hotbar slot", CONTROL_PREVIOUS, right - step, bottom, size},
        {">", "Next hotbar slot", CONTROL_NEXT, right, bottom, size},
        {"Pick", "Pick block", CONTROL_MIDDLE, left, bottom, size},
        {"||", "Pause", CONTROL_ESCAPE, right, 8, size},
        {"F3", "Toggle debug screen", CONTROL_DEBUG, left, 8, 36},
    };
    NSMutableArray *models = [NSMutableArray array];
    for (unsigned i = 0; i < sizeof(rows) / sizeof(rows[0]); i++) {
        [models addObject:@{
            @"name": @(rows[i].title),
            @"label": @(rows[i].label),
            @"keycode": @(rows[i].code),
            @"x": @(rows[i].x / W), @"y": @(rows[i].y / H),
            @"width": @(rows[i].s / W), @"height": @(rows[i].s / W),
        }];
    }
    return models;
}

@interface FAOTMetalView : UIView <UIKeyInput> {
    FAOTPointerMotion _hoverMotion;
}
@property(nonatomic,assign) GLFWwindow *handle;
@property(nonatomic,assign) BOOL textEnabled;
@property(nonatomic,assign) BOOL captured;
@property(nonatomic,assign) BOOL hasCapturedGame;
@property(nonatomic,assign) BOOL nativeMouseConnected;
@property(nonatomic,assign) BOOL pointerIsLocked;
@property(nonatomic,assign) unsigned heldNativeMouseButtons;
@property(nonatomic,strong) UIView *noKeyboard;
@property(nonatomic,strong) UITouch *primaryTouch;
@property(nonatomic,assign) int primaryButton;
@property(nonatomic,strong) NSMutableIndexSet *forwardedKeys;
@property(nonatomic,strong) NSArray<UIButton *> *controls;
@property(nonatomic,strong) NSArray<NSDictionary *> *controlModels;
@property(nonatomic,strong) NSMutableSet<NSNumber *> *heldControls;
- (void)installControls;
- (void)setGameCapture:(BOOL)captured;
- (void)releaseGameControls;
- (void)releaseNativeMouseButtons;
- (void)nativeMouseButton:(int)index pressed:(BOOL)pressed;
- (void)pointerHovered:(UIHoverGestureRecognizer *)recognizer;
- (void)resetHoverMotion;
- (void)controlDown:(UIButton *)button;
- (void)controlUp:(UIButton *)button;
- (BOOL)sendControl:(int)code pressed:(BOOL)pressed;
@end
@implementation FAOTMetalView
+ (Class)layerClass { return CAMetalLayer.class; }
- (BOOL)canBecomeFirstResponder { return YES; }
- (UIView *)inputView {
    if(self.textEnabled)return nil;
    if(!self.noKeyboard)self.noKeyboard=[[UIView alloc] initWithFrame:CGRectZero];
    return self.noKeyboard;
}
- (BOOL)forwardKeyPress:(UIPress *)press action:(int)action {
    if(!self.handle||!press.key||(action!=0&&self.textEnabled))return NO;
    UIKey *key=press.key;int code=faot_glfw_key_from_hid((unsigned)key.keyCode);if(code<0)return NO;
    if(!self.forwardedKeys)self.forwardedKeys=[NSMutableIndexSet indexSet];
    BOOL already=[self.forwardedKeys containsIndex:(NSUInteger)code];
    if(action==0&&!already)return NO;
    UIKeyModifierFlags flags=key.modifierFlags;
    int mods=((flags&UIKeyModifierShift)?1:0)|((flags&UIKeyModifierControl)?2:0)|((flags&UIKeyModifierAlternate)?4:0)|((flags&UIKeyModifierCommand)?8:0)|((flags&UIKeyModifierAlphaShift)?16:0);
    BOOL touchHeld=[self.heldControls containsObject:@(code)];
    if(!touchHeld&&!faot_glfw_enqueue(self.handle,FAOT_EVENT_KEY,code,key.keyCode,action==1&&already?2:action,mods))return NO;
    if(action)[self.forwardedKeys addIndex:(NSUInteger)code];else[self.forwardedKeys removeIndex:(NSUInteger)code];
    return YES;
}
- (void)pressesBegan:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event {
    NSMutableSet<UIPress *> *rest=[presses mutableCopy];
    for(UIPress *p in presses)if([self forwardKeyPress:p action:1])[rest removeObject:p];
    if(rest.count)[super pressesBegan:rest withEvent:event];
}
- (void)pressesEnded:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event {
    NSMutableSet<UIPress *> *rest=[presses mutableCopy];
    for(UIPress *p in presses)if([self forwardKeyPress:p action:0])[rest removeObject:p];
    if(rest.count)[super pressesEnded:rest withEvent:event];
}
- (void)pressesCancelled:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event {
    NSMutableSet<UIPress *> *rest=[presses mutableCopy];
    for(UIPress *p in presses)if([self forwardKeyPress:p action:0])[rest removeObject:p];
    if(rest.count)[super pressesCancelled:rest withEvent:event];
}
- (void)layoutSubviews {
    [super layoutSubviews];
    CGFloat scale=self.window.screen.scale ?: UIScreen.mainScreen.scale;
    self.contentScaleFactor=scale;
    CAMetalLayer *layer=(CAMetalLayer *)self.layer;
    layer.contentsScale=scale;
    layer.drawableSize=CGSizeMake(round(self.bounds.size.width*scale),round(self.bounds.size.height*scale));
    if(self.handle)faot_glfw_resize(self.handle,(int)self.bounds.size.width,(int)self.bounds.size.height,
                                  (int)layer.drawableSize.width,(int)layer.drawableSize.height);
    CGRect safe=UIEdgeInsetsInsetRect(self.bounds,self.safeAreaInsets);
    for(NSUInteger i=0;i<self.controls.count&&i<self.controlModels.count;i++){
        UIButton *button=self.controls[i];
        NSDictionary *model=self.controlModels[i];
        CGFloat width=MAX(28.0,[model[@"width"] doubleValue]*safe.size.width);
        CGFloat height=MAX(28.0,[model[@"height"] doubleValue]*safe.size.height);
        CGFloat x=safe.origin.x+[model[@"x"] doubleValue]*safe.size.width;
        CGFloat y=safe.origin.y+[model[@"y"] doubleValue]*safe.size.height;
        x=MIN(MAX(x,CGRectGetMinX(safe)),CGRectGetMaxX(safe)-width);
        y=MIN(MAX(y,CGRectGetMinY(safe)),CGRectGetMaxY(safe)-height);
        button.frame=CGRectMake(x,y,width,height);
        button.layer.cornerRadius=MIN(8.0,width/2);
    }
}
- (void)installControls {
    /* The launcher editor owns the layout. When its file is absent (fresh install, or a run
       started before the launcher ever saved one) fall back to the built-in thirteen. */
    NSMutableArray<NSDictionary *> *models=[NSMutableArray array];
    NSData *data=[NSData dataWithContentsOfFile:FAOTLayoutPath()];
    if(data){
        id root=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
        id list=[root isKindOfClass:NSDictionary.class]?((NSDictionary *)root)[@"controls"]:root;
        if([list isKindOfClass:NSArray.class]){
            for(id item in list)
                if([item isKindOfClass:NSDictionary.class]&&[item[@"keycode"] isKindOfClass:NSNumber.class])
                    [models addObject:item];
        }
    }
    if(models.count==0)models=[FAOTBuiltinControlModels() mutableCopy];
    self.controlModels=models;

    NSMutableArray<UIButton *> *controls=[NSMutableArray arrayWithCapacity:models.count];
    self.heldControls=[NSMutableSet set];
    for(NSDictionary *model in models){
        UIButton *button=[UIButton buttonWithType:UIButtonTypeSystem];
        button.tag=[model[@"keycode"] integerValue];
        NSString *title=model[@"name"];
        NSString *label=[model[@"label"] isKindOfClass:NSString.class]?model[@"label"]:title;
        button.accessibilityLabel=FAOTAccessibilityLabel(button.tag,label);
        button.accessibilityValue=title;
        [button setTitle:title forState:UIControlStateNormal];
        [button setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
        button.titleLabel.font=[UIFont systemFontOfSize:13 weight:UIFontWeightSemibold];
        button.backgroundColor=[UIColor colorWithWhite:0 alpha:([model[@"opacity"] doubleValue]?:0.55)];
        button.layer.cornerRadius=8;button.layer.borderWidth=1;
        button.layer.borderColor=[UIColor colorWithWhite:1 alpha:0.65].CGColor;
        button.hidden=YES;
        [button addTarget:self action:@selector(controlDown:) forControlEvents:UIControlEventTouchDown];
        [button addTarget:self action:@selector(controlUp:) forControlEvents:UIControlEventTouchUpInside|UIControlEventTouchUpOutside|UIControlEventTouchCancel];
        [self addSubview:button];[controls addObject:button];
    }
    self.controls=controls;
    // Menu pointer positions are independent of clicks. UIKit touches alone cannot track hover.
    UIHoverGestureRecognizer *hover=[[UIHoverGestureRecognizer alloc] initWithTarget:self action:@selector(pointerHovered:)];
    hover.cancelsTouchesInView=NO;
    [self addGestureRecognizer:hover];
}
- (BOOL)sendControl:(int)code pressed:(BOOL)pressed {
    if(!self.handle)return NO;
    if(code<0){
        if(code==CONTROL_SCROLLUP||code==CONTROL_SCROLLDOWN)
        return faot_glfw_enqueue(self.handle,FAOT_EVENT_SCROLL,0,code==CONTROL_SCROLLUP?1:-1,0,0)!=0;
    int mouseButton=(code==CONTROL_BREAK||code==CONTROL_PRIMARY)?0:(code==CONTROL_PLACE||code==CONTROL_SECONDARY)?1:(code==CONTROL_PICK||code==CONTROL_MIDDLE)?2:-1;
        return mouseButton>=0&&faot_glfw_enqueue(self.handle,FAOT_EVENT_BUTTON,mouseButton,pressed,0,0)!=0;
    }
    if([self.forwardedKeys containsIndex:(NSUInteger)code])return YES;
    return faot_glfw_enqueue(self.handle,FAOT_EVENT_KEY,code,0,pressed,0)!=0;
}
- (void)controlDown:(UIButton *)button {
    if(button.tag==CONTROL_DEBUG){
        NSNumber *debugKey=@(CONTROL_DEBUG);
        if(!self.captured||[self.heldControls containsObject:debugKey])return;
        if(![self sendControl:CONTROL_DEBUG pressed:YES])return;
        [self.heldControls addObject:debugKey];
        /* F3 is a toggle, not a held key: hold it across at least one game tick and let go
           automatically, so a quick tap is never swallowed by a press+release in one poll. */
        __weak FAOTMetalView *view=self;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,90*NSEC_PER_MSEC),dispatch_get_main_queue(),^{
            [view controlUp:button];
        });
        return;
    }
    if(self.captured&&(button.tag==CONTROL_PREVIOUS||button.tag==CONTROL_NEXT)){
        if(self.handle)faot_glfw_enqueue(self.handle,FAOT_EVENT_SCROLL,0,button.tag==CONTROL_PREVIOUS?1:-1,0,0);
        return;
    }
    NSNumber *key=@(button.tag);
    if((self.captured||button.tag==CONTROL_ESCAPE)&&![self.heldControls containsObject:key]&&[self sendControl:(int)button.tag pressed:YES])
        [self.heldControls addObject:key];
}
- (void)controlUp:(UIButton *)button {
    NSNumber *key=@(button.tag);
    if([self.heldControls containsObject:key]&&[self sendControl:(int)button.tag pressed:NO])
        [self.heldControls removeObject:key];
}
- (void)releaseNativeMouseButtons {
    if(self.handle)for(int i=0;i<3;i++)if(self.heldNativeMouseButtons&(1u<<i))
        faot_glfw_enqueue(self.handle,FAOT_EVENT_BUTTON,i,0,0,0);
    self.heldNativeMouseButtons=0;
}
- (void)nativeMouseButton:(int)index pressed:(BOOL)pressed {
    if(!self.handle||!self.captured||index<0||index>2)return;
    unsigned bit=1u<<index;
    if(((self.heldNativeMouseButtons&bit)!=0)==pressed)return;
    if(!faot_glfw_enqueue(self.handle,FAOT_EVENT_BUTTON,index,pressed,0,0))return;
    if(pressed)self.heldNativeMouseButtons|=bit;
    else self.heldNativeMouseButtons&=~bit;
}
- (void)releaseGameControls {
    [self releaseNativeMouseButtons];
    for(NSNumber *key in self.heldControls)[self sendControl:key.intValue pressed:NO];
    [self.heldControls removeAllObjects];
}
- (void)pointerHovered:(UIHoverGestureRecognizer *)recognizer {
    if(!self.handle)return;
    if(recognizer.state!=UIGestureRecognizerStateBegan&&recognizer.state!=UIGestureRecognizerStateChanged){
        [self resetHoverMotion];return;
    }
    CGPoint p=[recognizer locationInView:self];
    if(!self.captured){
        [self resetHoverMotion];
        faot_glfw_enqueue(self.handle,FAOT_EVENT_CURSOR,p.x,p.y,0,0);
    }else if(!self.pointerIsLocked){
        double dx,dy;
        if(faot_pointer_hover_delta(&_hoverMotion,p.x,p.y,&dx,&dy))
            faot_glfw_enqueue(self.handle,FAOT_EVENT_CURSOR_DELTA,dx,dy,0,0);
    }else [self resetHoverMotion];
}
- (void)resetHoverMotion { faot_pointer_reset(&_hoverMotion); }
- (void)setGameCapture:(BOOL)captured {
    if(self.captured==captured)return;
    [self resetHoverMotion];
    if(!captured)[self releaseGameControls];
    self.captured=captured;
    self.hasCapturedGame|=captured;
    // iPadOS may deny pointer lock (for example in Split View). Observe the actual lock state.
    [(UIViewController *)self.window.rootViewController setNeedsUpdateOfPrefersPointerLocked];
    for(UIButton *button in self.controls){
        if(button.tag==CONTROL_ESCAPE){
            button.hidden=!self.hasCapturedGame;
            button.accessibilityLabel=captured?@"Pause":@"Back to game";
            [button setTitle:captured?@"Ⅱ":@"×" forState:UIControlStateNormal];
        }else button.hidden=!captured;
    }
}
/* Absolute point coordinates match glfwGetWindowSize. Pixel scale belongs to framebuffer size. */
- (void)touchesBegan:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    if(!self.handle||self.primaryTouch)return;
    UITouch *touch=touches.anyObject;
    // GCMouse supplies hardware mouse clicks in game; do not forward UIKit duplicates.
    if(self.captured&&self.nativeMouseConnected&&touch.type==UITouchTypeIndirectPointer)return;
    self.primaryTouch=touch;
    CGPoint p=[touch locationInView:self];
    if(!self.captured)faot_glfw_enqueue(self.handle,FAOT_EVENT_CURSOR,p.x,p.y,0,0);
    // Finger drags look around without also attacking. A connected mouse retains both buttons.
    self.primaryButton=self.captured&&touch.type!=UITouchTypeIndirectPointer?-1:
        ((event.buttonMask&UIEventButtonMaskSecondary)?1:0);
    if(self.primaryButton>=0)faot_glfw_enqueue(self.handle,FAOT_EVENT_BUTTON,self.primaryButton,1,0,0);
}
- (void)touchesMoved:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    if(!self.handle)return;
    UITouch *touch=self.primaryTouch;if(!touch||![touches containsObject:touch])return;
    CGPoint p=[touch locationInView:self],old=[touch previousLocationInView:self];
    if(self.captured)faot_glfw_enqueue(self.handle,FAOT_EVENT_CURSOR_DELTA,p.x-old.x,p.y-old.y,0,0);
    else if(event.allTouches.count>1)faot_glfw_enqueue(self.handle,FAOT_EVENT_SCROLL,(p.x-old.x)/24.0,(old.y-p.y)/24.0,0,0);
    else faot_glfw_enqueue(self.handle,FAOT_EVENT_CURSOR,p.x,p.y,0,0);
}
- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    (void)event;
    if(self.primaryTouch&&[touches containsObject:self.primaryTouch]){
        if(self.handle&&self.primaryButton>=0)faot_glfw_enqueue(self.handle,FAOT_EVENT_BUTTON,self.primaryButton,0,0,0);
        self.primaryTouch=nil;
    }
}
- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self touchesEnded:touches withEvent:event]; }
- (BOOL)hasText { return YES; }
- (void)insertText:(NSString *)text {
    if(!self.handle||!self.textEnabled)return;
    /* Convert UTF-16 surrogate pairs to Unicode scalar values for GLFWCharCallback. */
    NSData *data=[text dataUsingEncoding:NSUTF32LittleEndianStringEncoding];
    const uint32_t *chars=data.bytes;
    for(NSUInteger i=0;i<data.length/4;i++)faot_glfw_enqueue(self.handle,FAOT_EVENT_CHAR,chars[i],0,0,0);
}
- (void)deleteBackward {
    if(!self.handle)return;
    faot_glfw_enqueue(self.handle,FAOT_EVENT_KEY,259,0,1,0);
    faot_glfw_enqueue(self.handle,FAOT_EVENT_KEY,259,0,0,0);
}
@end

@interface FAOTGameController : UIViewController
@end
@implementation FAOTGameController
- (BOOL)prefersStatusBarHidden { return YES; }
- (BOOL)prefersPointerLocked { return ((FAOTMetalView *)self.view).captured; }
- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    [self setNeedsUpdateOfPrefersPointerLocked];
}
@end

@interface FAOTPresentSlot : NSObject
@property(nonatomic,strong) id<MTLTexture> texture;
@property(nonatomic,strong) dispatch_semaphore_t freeSlot;
@end
@implementation FAOTPresentSlot
@end

/* MTLDrawable callbacks may run on different threads. Only timestamps and counters
   are protected; printing happens after the lock is released. */
@interface FAOTPresentStats : NSObject {
    os_unfair_lock _lock;
    double _last, _start;
    unsigned _intervals, _longFrames, _drops;
    unsigned _buckets[101];
}
- (void)dropped;
- (void)presented:(double)time;
@end

@implementation FAOTPresentStats
- (instancetype)init {
    if((self=[super init]))_lock=OS_UNFAIR_LOCK_INIT;
    return self;
}
- (void)dropped {
    os_unfair_lock_lock(&_lock);
    _drops++;
    os_unfair_lock_unlock(&_lock);
}
- (void)presented:(double)time {
    if(time<=0){[self dropped];return;}
    double fps=0;
    unsigned p95=0,longFrames=0,drops=0;
    os_unfair_lock_lock(&_lock);
    if(!_last || time-_last>1.0){
        _start=_last=time;
        _intervals=_longFrames=_drops=0;
        memset(_buckets,0,sizeof _buckets);
    }else if(time>_last){
        double ms=(time-_last)*1000.0;
        unsigned bin=ms>=100.0?100:(unsigned)ceil(ms);
        _buckets[bin]++;
        _intervals++;
        if(ms>34.0)_longFrames++;
        _last=time;
        if(time-_start>=5.0){
            fps=_intervals/(time-_start);
            unsigned rank=(_intervals*95+99)/100, seen=0;
            for(;p95<100;p95++){
                seen+=_buckets[p95];
                if(seen>=rank)break;
            }
            longFrames=_longFrames;
            drops=_drops;
            _start=time;
            _intervals=_longFrames=_drops=0;
            memset(_buckets,0,sizeof _buckets);
        }
    }
    os_unfair_lock_unlock(&_lock);
    if(fps>0)fprintf(stderr,"[GL41] display fps=%.1f p95=%ums long34=%u drops=%u\n",
                     fps,p95,longFrames,drops);
}
@end

@interface FAOTSurface : NSObject
@property(nonatomic,strong) UIWindow *window;
@property(nonatomic,weak) UIWindow *previous;
@property(nonatomic,strong) FAOTMetalView *view;
@property(nonatomic,strong) id foregroundToken;
@property(nonatomic,strong) id backgroundToken;
@property(nonatomic,strong) id pointerToken;
@property(nonatomic,strong) id mouseConnectToken;
@property(nonatomic,strong) id mouseDisconnectToken;
@property(nonatomic,strong) GCMouse *mouse;
@property(nonatomic,strong) id<MTLCommandQueue> presentQueue;
@property(nonatomic,strong) NSArray<FAOTPresentSlot *> *presentSlots;
@property(nonatomic,strong) dispatch_queue_t presentWorker;
@property(nonatomic,strong) FAOTPresentStats *presentStats;
@property(atomic,assign) BOOL canPresent;
@property(nonatomic,assign) NSUInteger presentSlot;
@property(nonatomic,assign) int presentWidth, presentHeight;
@property(nonatomic,strong) id<MTLRenderPipelineState> presentPipeline;
@property(nonatomic,strong) id<MTLSamplerState> presentSampler;
- (void)attachMouse:(GCMouse *)mouse;
@end
@implementation FAOTSurface
- (void)attachMouse:(GCMouse *)mouse {
    if(self.mouse==mouse)return;
    if(self.mouse){
        GCMouseInput *old=self.mouse.mouseInput;
        old.mouseMovedHandler=nil;
        old.leftButton.valueChangedHandler=nil;
        old.rightButton.valueChangedHandler=nil;
        old.middleButton.valueChangedHandler=nil;
        old.scroll.valueChangedHandler=nil;
    }
    [self.view releaseNativeMouseButtons];
    self.mouse=mouse;
    self.view.nativeMouseConnected=mouse!=nil;
    if(!mouse)return;

    __weak FAOTMetalView *weakView=self.view;
    GCMouseInput *input=mouse.mouseInput;
    // GameController reports unaccelerated relative motion; GLFW expects Y increasing down.
    input.mouseMovedHandler=^(GCMouseInput *sender,float dx,float dy){
        (void)sender;
        dispatch_block_t forward=^{
            FAOTMetalView *view=weakView;
            if(view&&view.handle&&view.captured&&view.pointerIsLocked)
                faot_glfw_enqueue(view.handle,FAOT_EVENT_CURSOR_DELTA,dx,-dy,0,0);
        };
        if(NSThread.isMainThread)forward();else dispatch_async(dispatch_get_main_queue(),forward);
    };
    void (^bindButton)(GCControllerButtonInput *,int)=^(GCControllerButtonInput *button,int index){
        if(!button)return;
        button.valueChangedHandler=^(GCControllerButtonInput *sender,float value,BOOL pressed){
            (void)sender;(void)value;
            dispatch_block_t forward=^{ FAOTMetalView *view=weakView; if(view)[view nativeMouseButton:index pressed:pressed]; };
            if(NSThread.isMainThread)forward();else dispatch_async(dispatch_get_main_queue(),forward);
        };
    };
    bindButton(input.leftButton,0);
    bindButton(input.rightButton,1);
    bindButton(input.middleButton,2);
    input.scroll.valueChangedHandler=^(GCControllerDirectionPad *sender,float dx,float dy){
        (void)sender;
        dispatch_block_t forward=^{
            FAOTMetalView *view=weakView;
            if(view&&view.handle)
                faot_glfw_enqueue(view.handle,FAOT_EVENT_SCROLL,dx,dy,0,0);
        };
        if(NSThread.isMainThread)forward();else dispatch_async(dispatch_get_main_queue(),forward);
    };
}
@end

void faot_surface_screen(GLFWvidmode *mode) {
    onMain(^{
        UIScreen *screen=activeScene().screen ?: UIScreen.mainScreen;
        *mode=(GLFWvidmode){(int)screen.bounds.size.width,(int)screen.bounds.size.height,8,8,8,(int)screen.maximumFramesPerSecond};
    });
}
void *faot_surface_create(GLFWwindow *handle,int *width,int *height,int *pw,int *ph) {
    __block FAOTSurface *surface=nil;
    onMain(^{
        UIWindowScene *scene=activeScene();
        if(!scene)return;
        id<MTLDevice> device=MTLCreateSystemDefaultDevice();
        if(!device)return;
        surface=[FAOTSurface new];
        surface.canPresent=YES;
        for(UIWindow *window in scene.windows)if(window.isKeyWindow)surface.previous=window;
        surface.window=[[UIWindow alloc] initWithWindowScene:scene];
        UIViewController *controller=[FAOTGameController new];
        surface.view=[[FAOTMetalView alloc] initWithFrame:scene.coordinateSpace.bounds];
        surface.view.handle=handle;
        surface.view.multipleTouchEnabled=YES;
        [surface.view installControls];
        CAMetalLayer *layer=(CAMetalLayer *)surface.view.layer;
        layer.device=device;
        layer.pixelFormat=MTLPixelFormatBGRA8Unorm;
        layer.framebufferOnly=NO;
        layer.maximumDrawableCount=3;
        layer.opaque=YES;
        controller.view=surface.view;
        surface.window.rootViewController=controller;
        [surface.window makeKeyAndVisible];
        [surface.view becomeFirstResponder];
        [surface.view layoutIfNeeded];
        CGFloat scale=scene.screen.scale;
        layer.contentsScale=scale;
        layer.drawableSize=CGSizeMake(round(surface.view.bounds.size.width*scale),round(surface.view.bounds.size.height*scale));
        *width=(int)surface.view.bounds.size.width;*height=(int)surface.view.bounds.size.height;
        *pw=(int)layer.drawableSize.width;*ph=(int)layer.drawableSize.height;
        NSNotificationCenter *nc=NSNotificationCenter.defaultCenter;
        __weak FAOTSurface *weakSurface=surface;
        __weak FAOTMetalView *pointerView=surface.view;
        surface.pointerToken=[nc addObserverForName:UIPointerLockStateDidChangeNotification object:scene.pointerLockState queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            (void)note;
            FAOTMetalView *view=pointerView;
            [view resetHoverMotion];
            view.pointerIsLocked=scene.pointerLockState.isLocked;
            fprintf(stderr,"[GLFW-lite] iPad pointer lock: %s\\n",view.pointerIsLocked?"locked":"unlocked");
        }];
        surface.view.pointerIsLocked=scene.pointerLockState.isLocked;
        surface.mouseConnectToken=[nc addObserverForName:GCMouseDidConnectNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            [weakSurface attachMouse:(GCMouse *)note.object];
        }];
        surface.mouseDisconnectToken=[nc addObserverForName:GCMouseDidDisconnectNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            FAOTSurface *current=weakSurface;
            if(current.mouse==note.object)[current attachMouse:[GCMouse mice].firstObject];
        }];
        [surface attachMouse:[GCMouse mice].firstObject];
        surface.foregroundToken=[nc addObserverForName:UISceneDidActivateNotification object:scene queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            (void)note;weakSurface.canPresent=YES;
            faot_glfw_enqueue(handle,FAOT_EVENT_FOCUS,1,0,0,0);
        }];
        __weak FAOTMetalView *inputView=surface.view;
        surface.backgroundToken=[nc addObserverForName:UISceneWillDeactivateNotification object:scene queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            (void)note;weakSurface.canPresent=NO;FAOTMetalView *view=inputView;
            if(view.primaryTouch){if(view.primaryButton>=0)faot_glfw_enqueue(handle,FAOT_EVENT_BUTTON,view.primaryButton,0,0,0);view.primaryTouch=nil;}
            [view releaseGameControls];
            [view resetHoverMotion];
            view.pointerIsLocked=NO;
            [view.forwardedKeys removeAllIndexes];faot_glfw_enqueue(handle,FAOT_EVENT_FOCUS,0,0,0,0);
        }];
    });
    return (__bridge_retained void *)surface;
}
void faot_surface_destroy(void *raw) {
    if(!raw)return;
    onMain(^{
        FAOTSurface *surface=(__bridge_transfer FAOTSurface *)raw;
        surface.canPresent=NO;
        surface.view.handle=NULL;
        NSNotificationCenter *nc=NSNotificationCenter.defaultCenter;
        if(surface.foregroundToken)[nc removeObserver:surface.foregroundToken];
        if(surface.backgroundToken)[nc removeObserver:surface.backgroundToken];
        if(surface.pointerToken)[nc removeObserver:surface.pointerToken];
        if(surface.mouseConnectToken)[nc removeObserver:surface.mouseConnectToken];
        if(surface.mouseDisconnectToken)[nc removeObserver:surface.mouseDisconnectToken];
        [surface attachMouse:nil];
        [surface.view resignFirstResponder];
        surface.window.hidden=YES;
        [surface.previous makeKeyAndVisible];
    });
}
void *faot_surface_layer(void *raw) {
    __block CAMetalLayer *layer=nil;
    onMain(^{layer=(CAMetalLayer *)((__bridge FAOTSurface *)raw).view.layer;});
    return (__bridge void *)layer;
}
static int FAOTEnsureUpscalePipeline(FAOTSurface *surface,id<MTLDevice> device) {
    if(surface.presentPipeline&&surface.presentSampler)return 1;
    static NSString *const source=
        @"#include <metal_stdlib>\n"
         "using namespace metal;\n"
         "struct VOut { float4 pos [[position]]; float2 uv; };\n"
         "vertex VOut v_main(uint vid [[vertex_id]]) {\n"
         "  float2 p[3] = { float2(-1.0,-1.0), float2(3.0,-1.0), float2(-1.0,3.0) };\n"
         "  VOut o; o.pos=float4(p[vid],0.0,1.0);\n"
         "  o.uv=float2((p[vid].x+1.0)*0.5,1.0-(p[vid].y+1.0)*0.5); return o;\n"
         "}\n"
         "fragment float4 f_main(VOut in [[stage_in]], texture2d<float> tex [[texture(0)]], sampler samp [[sampler(0)]]) {\n"
         "  return tex.sample(samp,in.uv);\n"
         "}\n";
    NSError *error=nil;
    id<MTLLibrary> library=[device newLibraryWithSource:source options:nil error:&error];
    if(!library){
        fprintf(stderr,"[GL41] Metal upscale shader failed: %s\n",error.localizedDescription.UTF8String ?: "unknown");
        return 0;
    }
    MTLRenderPipelineDescriptor *descriptor=[MTLRenderPipelineDescriptor new];
    descriptor.vertexFunction=[library newFunctionWithName:@"v_main"];
    descriptor.fragmentFunction=[library newFunctionWithName:@"f_main"];
    descriptor.colorAttachments[0].pixelFormat=MTLPixelFormatBGRA8Unorm;
    surface.presentPipeline=[device newRenderPipelineStateWithDescriptor:descriptor error:&error];
    if(!surface.presentPipeline){
        fprintf(stderr,"[GL41] Metal upscale pipeline failed: %s\n",error.localizedDescription.UTF8String ?: "unknown");
        return 0;
    }
    MTLSamplerDescriptor *sampler=[MTLSamplerDescriptor new];
    sampler.minFilter=MTLSamplerMinMagFilterLinear;
    sampler.magFilter=MTLSamplerMinMagFilterLinear;
    sampler.sAddressMode=MTLSamplerAddressModeClampToEdge;
    sampler.tAddressMode=MTLSamplerAddressModeClampToEdge;
    surface.presentSampler=[device newSamplerStateWithDescriptor:sampler];
    return surface.presentSampler!=nil;
}
/* Drawable acquisition and GPU submission stay off the game thread. The slot's
   reservation lasts through GPU completion, including when the surface resizes. */
static BOOL FAOTSubmitPresent(FAOTSurface *surface,CAMetalLayer *layer,FAOTPresentSlot *slot) {
    if(!surface.canPresent)return NO;
    id<CAMetalDrawable> drawable=[layer nextDrawable];
    if(!drawable||!surface.canPresent)return NO;
    id<MTLCommandBuffer> command=[surface.presentQueue commandBuffer];
    if(!command)return NO;
    id<MTLTexture> texture=slot.texture;
    if(texture.width==drawable.texture.width&&texture.height==drawable.texture.height){
        id<MTLBlitCommandEncoder> blit=[command blitCommandEncoder];
        if(!blit)return NO;
        [blit copyFromTexture:texture sourceSlice:0 sourceLevel:0
            sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(texture.width,texture.height,1)
            toTexture:drawable.texture destinationSlice:0 destinationLevel:0 destinationOrigin:MTLOriginMake(0,0,0)];
        [blit endEncoding];
    }else if(FAOTEnsureUpscalePipeline(surface,layer.device)){
        MTLRenderPassDescriptor *pass=[MTLRenderPassDescriptor renderPassDescriptor];
        pass.colorAttachments[0].texture=drawable.texture;
        pass.colorAttachments[0].loadAction=MTLLoadActionDontCare;
        pass.colorAttachments[0].storeAction=MTLStoreActionStore;
        id<MTLRenderCommandEncoder> encoder=[command renderCommandEncoderWithDescriptor:pass];
        if(!encoder)return NO;
        [encoder setViewport:(MTLViewport){0,0,drawable.texture.width,drawable.texture.height,0,1}];
        [encoder setRenderPipelineState:surface.presentPipeline];
        [encoder setFragmentTexture:texture atIndex:0];
        [encoder setFragmentSamplerState:surface.presentSampler atIndex:0];
        [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
        [encoder endEncoding];
    }else return NO;
    FAOTPresentStats *stats=surface.presentStats;
    [drawable addPresentedHandler:^(id<MTLDrawable> displayed){[stats presented:displayed.presentedTime];}];
    [command presentDrawable:drawable];
    [command addCompletedHandler:^(id<MTLCommandBuffer> completed){
        (void)completed;
        dispatch_semaphore_signal(slot.freeSlot);
    }];
    [command commit];
    return YES;
}

void faot_surface_present_bgra(void *raw,const void *pixels,int width,int height) {
    if(!raw||!pixels||width<=0||height<=0)return;
    @autoreleasepool {
        FAOTSurface *surface=(__bridge FAOTSurface *)raw;
        if(!surface.canPresent)return;
        CAMetalLayer *layer=(CAMetalLayer *)surface.view.layer;
        id<MTLDevice> device=layer.device;
        if(!device)return;
        if(!surface.presentWorker){
            surface.presentQueue=[device newCommandQueue];
            if(!surface.presentQueue)return;
            surface.presentStats=[FAOTPresentStats new];
            surface.presentWorker=dispatch_queue_create("org.fabricaot.gl41.present",
                dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL,QOS_CLASS_USER_INTERACTIVE,0));
        }
        if(!surface.presentSlots||surface.presentWidth!=width||surface.presentHeight!=height){
            MTLTextureDescriptor *descriptor=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm
                width:(NSUInteger)width height:(NSUInteger)height mipmapped:NO];
            descriptor.usage=MTLTextureUsageShaderRead;
            descriptor.storageMode=MTLStorageModeShared;
            NSMutableArray<FAOTPresentSlot *> *slots=[NSMutableArray arrayWithCapacity:3];
            for(int i=0;i<3;i++){
                FAOTPresentSlot *slot=[FAOTPresentSlot new];
                slot.texture=[device newTextureWithDescriptor:descriptor];
                if(!slot.texture)return;
                slot.freeSlot=dispatch_semaphore_create(1);
                [slots addObject:slot];
            }
            surface.presentSlots=slots;
            surface.presentSlot=0;
            surface.presentWidth=width;surface.presentHeight=height;
        }
        NSUInteger count=surface.presentSlots.count;
        FAOTPresentSlot *slot=nil;
        for(NSUInteger i=0;i<count;i++){
            NSUInteger index=(surface.presentSlot+i)%count;
            FAOTPresentSlot *candidate=surface.presentSlots[index];
            if(dispatch_semaphore_wait(candidate.freeSlot,DISPATCH_TIME_NOW)==0){
                slot=candidate;
                surface.presentSlot=(index+1)%count;
                break;
            }
        }
        if(!slot){[surface.presentStats dropped];return;}
        // OSMesa will overwrite its frame on the next swap. Copy before returning to it.
        [slot.texture replaceRegion:MTLRegionMake2D(0,0,(NSUInteger)width,(NSUInteger)height)
            mipmapLevel:0 withBytes:pixels bytesPerRow:(NSUInteger)width*4];
        dispatch_async(surface.presentWorker,^{
            @autoreleasepool {
                if(!FAOTSubmitPresent(surface,layer,slot)){
                    [surface.presentStats dropped];
                    dispatch_semaphore_signal(slot.freeSlot);
                }
            }
        });
    }
}
void faot_surface_title(void *raw,const char *title) {
    NSString *text=title?[NSString stringWithUTF8String:title]:@"";
    onMain(^{((__bridge FAOTSurface *)raw).window.rootViewController.title=text;});
}
void faot_surface_input(void *raw,int mode,int value) {
    onMain(^{
        FAOTMetalView *view=((__bridge FAOTSurface *)raw).view;
        if(mode==GLFW_IME){view.textEnabled=!!value;[view reloadInputViews];}
        else if(mode==GLFW_CURSOR)[view setGameCapture:value==GLFW_CURSOR_DISABLED];
    });
}
void faot_surface_ime_rect(void *raw,int x,int y,int width,int height) {
    (void)raw;(void)x;(void)y;(void)width;(void)height;
    fprintf(stderr,"[GLFW-lite] IME preedit requires UITextInput; UIKeyInput currently provides committed text only\n");
}
void faot_surface_clipboard_set(const char *value) {
    NSString *text=[NSString stringWithUTF8String:value];
    onMain(^{UIPasteboard.generalPasteboard.string=text;});
}
char *faot_surface_clipboard_copy(void) {
    __block char *value=NULL;
    onMain(^{value=strdup((UIPasteboard.generalPasteboard.string?:@"").UTF8String);});
    return value;
}
