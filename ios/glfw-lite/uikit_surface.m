#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>
#import <Metal/Metal.h>
#import <GameController/GameController.h>
#include <math.h>
#include <stdarg.h>
#include "glfw_lite.h"
#include "input_mapping.h"
#include "pointer_state.h"

enum { CONTROL_BREAK=-1, CONTROL_PLACE=-2, CONTROL_PREVIOUS=-3, CONTROL_NEXT=-4, CONTROL_PICK=-5,
       CONTROL_ESCAPE=256, CONTROL_DEBUG=292 /* GLFW_KEY_F3 */ };

static FILE *gInputLog;
static dispatch_once_t gInputLogOnce;

static void inputLogInit(void) {
    dispatch_once(&gInputLogOnce, ^{
        NSArray<NSString *> *directories =
            NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES);
        NSString *directory = [directories.firstObject stringByAppendingPathComponent:@"c0-logs"];
        [NSFileManager.defaultManager createDirectoryAtPath:directory
                               withIntermediateDirectories:YES attributes:nil error:nil];
        NSString *name = [NSString stringWithFormat:@"input-%.0f.log",
                          NSDate.date.timeIntervalSince1970 * 1000.0];
        NSString *path = [directory stringByAppendingPathComponent:name];
        gInputLog = fopen(path.fileSystemRepresentation, "a");
        fprintf(stderr, "[GLFW-lite] input diagnostics: %s\n", path.UTF8String);
    });
}

/* State changes and a bounded sample of motion events. Never called per touch move. */
static void inputLog(NSString *format, ...) {
    inputLogInit();
    va_list arguments;
    va_start(arguments, format);
    NSString *message = [[NSString alloc] initWithFormat:format arguments:arguments];
    va_end(arguments);
    fprintf(stderr, "[FAOTInput] %s\n", message.UTF8String);
    if (gInputLog) {
        fprintf(gInputLog, "%s\n", message.UTF8String);
        fflush(gInputLog);
    }
}

static void onMain(dispatch_block_t block) {
    if (NSThread.isMainThread) block(); else dispatch_sync(dispatch_get_main_queue(),block);
}
static UIWindowScene *activeScene(void) {
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes)
        if ([scene isKindOfClass:UIWindowScene.class] && scene.activationState==UISceneActivationStateForegroundActive)
            return (UIWindowScene *)scene;
    return nil;
}
static CGSize sceneSize(UIWindowScene *scene) {
    if (!scene) return CGSizeZero;
    if (@available(iOS 26.0, *)) return scene.effectiveGeometry.coordinateSpace.bounds.size;
    return scene.coordinateSpace.bounds.size;
}
/* iPadOS grants pointer lock only to a foreground scene that fills its screen. */
static BOOL sceneFillsScreen(UIWindowScene *scene) {
    if (!scene || scene.activationState != UISceneActivationStateForegroundActive) return NO;
    CGSize visible = sceneSize(scene);
    CGSize screen = scene.screen.bounds.size;
    if (visible.width <= 0 || visible.height <= 0 || screen.width <= 0 || screen.height <= 0) return NO;
    const CGFloat epsilon = 1.0;
    BOOL direct = fabs(visible.width - screen.width) <= epsilon &&
                  fabs(visible.height - screen.height) <= epsilon;
    BOOL rotated = fabs(visible.width - screen.height) <= epsilon &&
                   fabs(visible.height - screen.width) <= epsilon;
    return direct || rotated;
}

@interface FAOTMetalView : UIView <UIKeyInput, UIGestureRecognizerDelegate, UIPointerInteractionDelegate>
@property(nonatomic,assign) GLFWwindow *handle;
@property(nonatomic,assign) BOOL textEnabled;
@property(nonatomic,assign) BOOL captured;
@property(nonatomic,assign) BOOL active;
@property(nonatomic,assign) BOOL hasCapturedGame;
@property(nonatomic,assign) BOOL nativeMouseConnected;
@property(nonatomic,assign) BOOL pointerIsLocked;
@property(nonatomic,assign) BOOL sceneFullScreen;
@property(nonatomic,assign) BOOL pointerLockRequested;
@property(nonatomic,assign) NSTimeInterval lastPointerLockRequest;
@property(nonatomic,assign) NSTimeInterval lastMouseMotion;
@property(nonatomic,assign) NSTimeInterval lastMouseScroll;
@property(nonatomic,assign) NSUInteger motionEvents;
@property(nonatomic,assign) NSUInteger diagnosticsGeneration;
@property(nonatomic,assign) CGPoint lastHover;
@property(nonatomic,assign) BOOL hasLastHover;
@property(nonatomic,assign) BOOL lastDrawableSizeValid;
@property(nonatomic,assign) CGSize lastDrawableSize;
@property(nonatomic,assign) CGSize lastPointSize;
@property(nonatomic,assign) FAOTPointerState pointerState;
@property(nonatomic,assign) unsigned heldNativeMouseButtons;
@property(nonatomic,strong) UIView *noKeyboard;
@property(nonatomic,strong) UITouch *primaryTouch;
@property(nonatomic,assign) int primaryButton;
@property(nonatomic,strong) NSMutableIndexSet *forwardedKeys;
@property(nonatomic,strong) NSArray<UIButton *> *controls;
@property(nonatomic,strong) NSMutableSet<NSNumber *> *heldControls;
@property(nonatomic,strong) UILabel *diagnostics;
@property(nonatomic,strong) UIPanGestureRecognizer *scrollGesture;
@property(nonatomic,strong) UIPointerInteraction *pointerInteraction;
- (void)installControls;
- (void)setGameCapture:(BOOL)captured;
- (void)setSceneActive:(BOOL)active;
- (void)refreshSceneState;
- (void)requestPointerLock;
- (BOOL)wantsPointerLock;
- (void)pointerLockChanged:(BOOL)locked;
- (void)releaseGameControls;
- (void)releaseNativeMouseButtons;
- (void)nativeMouseButton:(int)index pressed:(BOOL)pressed;
- (void)mouseMovedDX:(double)dx dy:(double)dy;
- (void)pointerHovered:(UIHoverGestureRecognizer *)recognizer;
- (void)scrollPanned:(UIPanGestureRecognizer *)recognizer;
- (void)sendScrollX:(double)dx y:(double)dy source:(NSString *)source;
- (void)sendRelativeX:(double)dx y:(double)dy source:(NSString *)source;
- (void)showDiagnostics:(NSString *)reason;
- (void)logInputState:(NSString *)reason;
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
    if(scale<=0)scale=1;
    self.contentScaleFactor=scale;
    CAMetalLayer *layer=(CAMetalLayer *)self.layer;
    layer.contentsScale=scale;
    CGSize points=self.bounds.size;
    CGSize drawable=CGSizeMake(round(points.width*scale),round(points.height*scale));
    BOOL drawableChanged=!self.lastDrawableSizeValid||!CGSizeEqualToSize(self.lastDrawableSize,drawable);
    BOOL pointsChanged=!self.lastDrawableSizeValid||!CGSizeEqualToSize(self.lastPointSize,points);
    if(drawableChanged)layer.drawableSize=drawable;
    if(self.handle&&(drawableChanged||pointsChanged)){
        faot_glfw_resize(self.handle,(int)points.width,(int)points.height,
                         (int)drawable.width,(int)drawable.height);
        inputLog(@"geometry points=%.0fx%.0f drawable=%.0fx%.0f scale=%.1f sceneFullScreen=%d",
                 points.width,points.height,drawable.width,drawable.height,scale,self.sceneFullScreen);
    }
    self.lastDrawableSize=drawable;self.lastPointSize=points;self.lastDrawableSizeValid=YES;
    CGRect safe=UIEdgeInsetsInsetRect(self.bounds,self.safeAreaInsets);
    const CGFloat size=44,step=48,left=CGRectGetMinX(safe)+8,right=CGRectGetMaxX(safe)-size-8;
    const CGFloat bottom=CGRectGetMaxY(safe)-size-32;
    /* Debug toggle mirrors the pause button in the top-left corner: out of thumb reach and
       deliberately smaller, so it neither competes with combat controls nor hides much HUD. */
    const CGFloat debugSize=36,debugX=left,debugY=CGRectGetMinY(safe)+8+(size-debugSize)/2;
    CGPoint pointsForControls[]={{left+step,bottom-2*step},{left,bottom-step},{left+step,bottom-step},{left+2*step,bottom-step},
                      {right,bottom-step},{right-step,bottom-step},{right,bottom-2*step},{right-step,bottom-2*step},
                      {right-step,bottom},{right,bottom},{left,bottom},{right,CGRectGetMinY(safe)+8},
                      {debugX,debugY}};
    for(NSUInteger i=0;i<self.controls.count;i++){
        UIButton *button=self.controls[i];
        CGFloat side=button.tag==CONTROL_DEBUG?debugSize:size;
        button.frame=CGRectMake(pointsForControls[i].x,pointsForControls[i].y,side,side);
    }
    if(self.diagnostics){
        CGSize fit=[self.diagnostics sizeThatFits:CGSizeMake(MAX(220.0,self.bounds.size.width-48.0),CGFLOAT_MAX)];
        CGFloat width=MIN(self.bounds.size.width-32.0,MAX(220.0,fit.width+18.0));
        CGFloat height=MAX(30.0,fit.height+8.0);
        self.diagnostics.frame=CGRectMake(round((self.bounds.size.width-width)/2.0),
                                          CGRectGetMinY(safe)+8.0,width,height);
    }
}
- (void)installControls {
    NSArray<NSString *> *titles=@[@"↑",@"←",@"↓",@"→",@"Jump",@"Items",@"Place",@"Break",@"◀",@"▶",@"Pick",@"Ⅱ",@"F3"];
    NSArray<NSString *> *labels=@[@"Move forward",@"Move left",@"Move backward",@"Move right",
                                   @"Jump",@"Inventory",@"Place or use",@"Break or attack",
                                   @"Previous hotbar slot",@"Next hotbar slot",@"Pick block",@"Pause",
                                   @"Toggle debug screen"];
    const int codes[]={'W','A','S','D',' ','E',CONTROL_PLACE,CONTROL_BREAK,CONTROL_PREVIOUS,CONTROL_NEXT,CONTROL_PICK,CONTROL_ESCAPE,CONTROL_DEBUG};
    NSMutableArray<UIButton *> *controls=[NSMutableArray arrayWithCapacity:titles.count];
    self.heldControls=[NSMutableSet set];
    for(NSUInteger i=0;i<titles.count;i++){
        UIButton *button=[UIButton buttonWithType:UIButtonTypeSystem];
        button.tag=codes[i];button.accessibilityLabel=labels[i];
        [button setTitle:titles[i] forState:UIControlStateNormal];
        [button setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
        button.titleLabel.font=[UIFont systemFontOfSize:12 weight:UIFontWeightSemibold];
        button.backgroundColor=[UIColor colorWithWhite:0 alpha:0.55];
        button.layer.cornerRadius=8;button.layer.borderWidth=1;
        button.layer.borderColor=[UIColor colorWithWhite:1 alpha:0.65].CGColor;
        if(codes[i]==CONTROL_DEBUG)button.backgroundColor=[UIColor colorWithWhite:0 alpha:0.4];
        button.hidden=YES;
        [button addTarget:self action:@selector(controlDown:) forControlEvents:UIControlEventTouchDown];
        [button addTarget:self action:@selector(controlUp:) forControlEvents:UIControlEventTouchUpInside|UIControlEventTouchUpOutside|UIControlEventTouchCancel];
        [self addSubview:button];[controls addObject:button];
    }
    self.controls=controls;
    // Menu pointer positions are independent of clicks. UIKit touches alone cannot track hover.
    UIHoverGestureRecognizer *hover=[[UIHoverGestureRecognizer alloc] initWithTarget:self action:@selector(pointerHovered:)];
    [self addGestureRecognizer:hover];
    // Trackpad scroll arrives as a scroll/transform event, not as touches. The delegate below
    // rejects finger pans so this recognizer cannot compete with touch-look.
    self.scrollGesture=[[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(scrollPanned:)];
    self.scrollGesture.allowedScrollTypesMask=UIScrollTypeMaskAll;
    self.scrollGesture.cancelsTouchesInView=NO;
    self.scrollGesture.delaysTouchesBegan=NO;
    self.scrollGesture.delegate=self;
    [self addGestureRecognizer:self.scrollGesture];
    // Fallback for a scene that cannot obtain pointer lock: hide the system pointer while
    // capture is active and let the hover-delta path drive the camera.
    self.pointerInteraction=[[UIPointerInteraction alloc] initWithDelegate:self];
    [self addInteraction:self.pointerInteraction];
    self.diagnostics=[[UILabel alloc] initWithFrame:CGRectZero];
    self.diagnostics.numberOfLines=2;
    self.diagnostics.textAlignment=NSTextAlignmentCenter;
    self.diagnostics.font=[UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightMedium];
    self.diagnostics.textColor=UIColor.whiteColor;
    self.diagnostics.backgroundColor=[UIColor colorWithWhite:0 alpha:0.62];
    self.diagnostics.layer.cornerRadius=7;
    self.diagnostics.clipsToBounds=YES;
    self.diagnostics.userInteractionEnabled=NO;
    self.diagnostics.hidden=YES;
    [self addSubview:self.diagnostics];
}
- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gestureRecognizer shouldReceiveEvent:(UIEvent *)event {
    if(gestureRecognizer==self.scrollGesture)
        return event.type==UIEventTypeScroll||event.type==UIEventTypeTransform;
    return YES;
}
- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gestureRecognizer
        shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer *)other {
    return gestureRecognizer==self.scrollGesture||other==self.scrollGesture;
}
- (UIPointerRegion *)pointerInteraction:(UIPointerInteraction *)interaction
                       regionForRequest:(UIPointerRegionRequest *)request
                          defaultRegion:(UIPointerRegion *)defaultRegion {
    (void)interaction;(void)request;
    return defaultRegion;
}
- (UIPointerStyle *)pointerInteraction:(UIPointerInteraction *)interaction
                        styleForRegion:(UIPointerRegion *)region {
    (void)interaction;(void)region;
    return self.captured?[UIPointerStyle hiddenPointerStyle]:nil;
}
- (BOOL)sendControl:(int)code pressed:(BOOL)pressed {
    if(!self.handle)return NO;
    if(code<0){
        int mouseButton=code==CONTROL_BREAK?0:code==CONTROL_PLACE?1:code==CONTROL_PICK?2:-1;
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
    if(self.heldNativeMouseButtons)inputLog(@"buttons released held=0x%x",self.heldNativeMouseButtons);
    self.heldNativeMouseButtons=0;
}
- (void)nativeMouseButton:(int)index pressed:(BOOL)pressed {
    if(!self.handle||index<0||index>2)return;
    [self refreshSceneState];
    if(!faot_pointer_should_forward_button(&_pointerState)){
        inputLog(@"button ignored index=%d pressed=%d captured=%d active=%d",index,pressed,self.captured,self.active);
        return;
    }
    unsigned bit=1u<<index;
    if(((self.heldNativeMouseButtons&bit)!=0)==pressed)return;
    if(!faot_glfw_enqueue(self.handle,FAOT_EVENT_BUTTON,index,pressed,0,0))return;
    if(pressed)self.heldNativeMouseButtons|=bit;
    else self.heldNativeMouseButtons&=~bit;
    faot_pointer_note_button(&_pointerState,pressed);
    inputLog(@"button source=gcmouse index=%d pressed=%d locked=%d",index,pressed,self.pointerIsLocked);
}
- (void)releaseGameControls {
    [self releaseNativeMouseButtons];
    for(NSNumber *key in self.heldControls)[self sendControl:key.intValue pressed:NO];
    [self.heldControls removeAllObjects];
    if(self.forwardedKeys.count){
        NSMutableIndexSet *keys=[self.forwardedKeys mutableCopy];
        [self.forwardedKeys removeAllIndexes];
        [keys enumerateIndexesUsingBlock:^(NSUInteger code,BOOL *stop){
            (void)stop;
            if(self.handle)faot_glfw_enqueue(self.handle,FAOT_EVENT_KEY,(int)code,0,0,0);
        }];
    }
    self.hasLastHover=NO;
}
- (void)refreshSceneState {
    UIWindowScene *scene=self.window.windowScene ?: activeScene();
    self.sceneFullScreen=sceneFillsScreen(scene);
    faot_pointer_set_captured(&_pointerState,self.captured);
    faot_pointer_set_active(&_pointerState,self.active);
    faot_pointer_set_scene_full_screen(&_pointerState,self.sceneFullScreen);
    faot_pointer_set_locked(&_pointerState,self.pointerIsLocked);
    faot_pointer_set_mouse_connected(&_pointerState,self.nativeMouseConnected);
}
- (BOOL)wantsPointerLock {
    [self refreshSceneState];
    return faot_pointer_prefers_lock(&_pointerState)?YES:NO;
}
- (void)requestPointerLock {
    [self refreshSceneState];
    UIViewController *controller=self.window.rootViewController;
    if(!controller)return;
    BOOL wants=faot_pointer_prefers_lock(&_pointerState);
    BOOL changed=self.pointerLockRequested!=wants;
    NSTimeInterval now=CACurrentMediaTime();
    if(wants&&!changed&&(self.pointerIsLocked||now-self.lastPointerLockRequest<0.35))return;
    self.pointerLockRequested=wants;
    if(wants){
        self.lastPointerLockRequest=now;
        faot_pointer_note_lock_request(&_pointerState);
    }
    [controller setNeedsUpdateOfPrefersPointerLocked];
    if(changed||wants)
        inputLog(@"lock-%@ wanted=%d approved=%d active=%d fullScreen=%d captured=%d",
                 wants?@"request":@"release",wants,self.pointerIsLocked,self.active,
                 self.sceneFullScreen,self.captured);
}
- (void)pointerLockChanged:(BOOL)locked {
    BOOL changed=self.pointerIsLocked!=locked;
    self.pointerIsLocked=locked;
    faot_pointer_set_locked(&_pointerState,locked);
    if(!changed)return;
    [self.pointerInteraction invalidate];
    [self logInputState:@"pointer-lock"];
    [self showDiagnostics:@"pointer-lock"];
    if(!locked&&self.captured&&self.sceneFullScreen&&self.active){
        NSTimeInterval now=CACurrentMediaTime();
        if(now-self.lastPointerLockRequest>0.75){
            __weak FAOTMetalView *weakSelf=self;
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW,250*NSEC_PER_MSEC),dispatch_get_main_queue(),^{
                FAOTMetalView *view=weakSelf;
                if(view&&view.captured&&!view.pointerIsLocked)[view requestPointerLock];
            });
        }
    }
}
- (void)setSceneActive:(BOOL)active {
    if(self.active==active)return;
    self.active=active;
    faot_pointer_set_active(&_pointerState,active);
    if(!active){
        self.pointerIsLocked=NO;
        faot_pointer_set_locked(&_pointerState,NO);
        self.hasLastHover=NO;
    }
    [self logInputState:active?@"scene-active":@"scene-inactive"];
    [self requestPointerLock];
}
- (void)logInputState:(NSString *)reason {
    UIWindowScene *scene=self.window.windowScene ?: activeScene();
    CGSize visible=sceneSize(scene);
    CGSize screen=scene?scene.screen.bounds.size:CGSizeZero;
    CAMetalLayer *layer=(CAMetalLayer *)self.layer;
    NSString *mouseName=GCMouse.current.vendorName ?: [GCMouse mice].firstObject.vendorName ?: @"-";
    inputLog(@"state reason=%@ captured=%d active=%d fullScreen=%d locked=%d lockRequested=%d "
             @"gcmouse=%d gcmouseCount=%lu mouseName=%@ scene=%.0fx%.0f screen=%.0fx%.0f "
             @"drawable=%.0fx%.0f scale=%.1f firstResponder=%d lockRequests=%llu "
             @"motionForwarded=%llu motionDropped=%llu",
             reason,self.captured,self.active,self.sceneFullScreen,self.pointerIsLocked,
             self.pointerLockRequested,self.nativeMouseConnected,(unsigned long)[GCMouse mice].count,
             mouseName,visible.width,visible.height,screen.width,screen.height,
             layer.drawableSize.width,layer.drawableSize.height,layer.contentsScale,
             self.isFirstResponder,(unsigned long long)_pointerState.lock_requests,
             (unsigned long long)_pointerState.motion_forwarded,
             (unsigned long long)_pointerState.motion_dropped);
}
- (void)showDiagnostics:(NSString *)reason {
    if(UIDevice.currentDevice.userInterfaceIdiom!=UIUserInterfaceIdiomPad||!self.diagnostics)return;
    UIWindowScene *scene=self.window.windowScene ?: activeScene();
    CGSize visible=sceneSize(scene);
    CGSize screen=scene?scene.screen.bounds.size:CGSizeZero;
    CAMetalLayer *layer=(CAMetalLayer *)self.layer;
    NSString *lock;
    if(!self.captured)lock=@"menu pointer";
    else if(self.pointerIsLocked)lock=@"pointer LOCKED";
    else if(self.sceneFullScreen)lock=@"pointer lock requested/unapproved";
    else lock=@"NO LOCK: scene windowed";
    NSString *mouse=self.nativeMouseConnected?
        [NSString stringWithFormat:@"GCMouse %@",GCMouse.current.vendorName ?: @"connected"]:
        @"no GCMouse: hover fallback";
    self.diagnostics.text=[NSString stringWithFormat:
        @"iPad native %.0f×%.0f pt · %.0f×%.0f px · scene %.0f×%.0f\n%@ · %@ (%@)",
        visible.width,visible.height,layer.drawableSize.width,layer.drawableSize.height,
        screen.width,screen.height,lock,mouse,reason];
    self.diagnostics.hidden=NO;
    NSUInteger generation=++self.diagnosticsGeneration;
    __weak FAOTMetalView *weakSelf=self;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,6*NSEC_PER_SEC),dispatch_get_main_queue(),^{
        FAOTMetalView *view=weakSelf;
        if(view&&view.diagnosticsGeneration==generation)view.diagnostics.hidden=YES;
    });
}
- (void)sendRelativeX:(double)dx y:(double)dy source:(NSString *)source {
    if(!self.handle)return;
    [self refreshSceneState];
    if(!faot_pointer_should_forward_motion(&_pointerState)){
        faot_pointer_note_motion(&_pointerState,0);
        return;
    }
    if(!isfinite(dx)||!isfinite(dy))return;
    if(fabs(dx)<0.0001&&fabs(dy)<0.0001)return;
    if(!faot_glfw_enqueue(self.handle,FAOT_EVENT_CURSOR_DELTA,dx,dy,0,0)){
        faot_pointer_note_motion(&_pointerState,0);
        return;
    }
    faot_pointer_note_motion(&_pointerState,1);
    self.motionEvents++;
    if(self.motionEvents<=8||self.motionEvents%120==0)
        inputLog(@"motion source=%@ dx=%.2f dy=%.2f events=%lu locked=%d hoverFallback=%d",
                 source,dx,dy,(unsigned long)self.motionEvents,self.pointerIsLocked,
                 !self.nativeMouseConnected);
}
- (void)sendScrollX:(double)dx y:(double)dy source:(NSString *)source {
    if(!self.handle||!isfinite(dx)||!isfinite(dy))return;
    if(fabs(dx)<0.0001&&fabs(dy)<0.0001)return;
    if(self.nativeMouseConnected&&CACurrentMediaTime()-self.lastMouseScroll<0.15)return;
    if(faot_glfw_enqueue(self.handle,FAOT_EVENT_SCROLL,dx,dy,0,0)){
        self.lastMouseScroll=CACurrentMediaTime();
        inputLog(@"scroll source=%@ dx=%.2f dy=%.2f captured=%d",source,dx,dy,self.captured);
    }
}
- (void)mouseMovedDX:(double)dx dy:(double)dy {
    self.lastMouseMotion=CACurrentMediaTime();
    /* GCMouse reports raw deltas with Y increasing up; GLFW cursor coordinates increase down. */
    [self sendRelativeX:dx y:-dy source:@"gcmouse"];
}
- (void)pointerHovered:(UIHoverGestureRecognizer *)recognizer {
    if(!self.handle)return;
    CGPoint p=[recognizer locationInView:self];
    if(!self.captured){
        if(recognizer.state==UIGestureRecognizerStateBegan||
           recognizer.state==UIGestureRecognizerStateChanged)
            faot_glfw_enqueue(self.handle,FAOT_EVENT_CURSOR,p.x,p.y,0,0);
        self.lastHover=p;self.hasLastHover=YES;
        return;
    }
    if(recognizer.state==UIGestureRecognizerStateBegan){
        self.lastHover=p;self.hasLastHover=YES;
        return;
    }
    if(recognizer.state!=UIGestureRecognizerStateChanged)return;
    /* Prefer GCMouse when it is actively delivering motion. */
    if(self.nativeMouseConnected&&CACurrentMediaTime()-self.lastMouseMotion<0.15)return;
    if(!faot_pointer_should_forward_hover_delta(&_pointerState))return;
    if(!self.hasLastHover){self.lastHover=p;self.hasLastHover=YES;return;}
    CGPoint delta=CGPointMake(p.x-self.lastHover.x,p.y-self.lastHover.y);
    self.lastHover=p;
    [self sendRelativeX:delta.x y:delta.y source:@"hover"];
}
- (void)scrollPanned:(UIPanGestureRecognizer *)recognizer {
    if(recognizer.state==UIGestureRecognizerStateBegan){
        [recognizer setTranslation:CGPointZero inView:self];
        return;
    }
    if(recognizer.state!=UIGestureRecognizerStateChanged)return;
    CGPoint translation=[recognizer translationInView:self];
    [recognizer setTranslation:CGPointZero inView:self];
    /* Trackpad scroll is reported in points; GLFW's wheel convention is positive = up. */
    [self sendScrollX:translation.x/12.0 y:-translation.y/12.0 source:@"trackpad-pan"];
}
- (void)setGameCapture:(BOOL)captured {
    if(self.captured==captured){[self requestPointerLock];return;}
    if(!captured)[self releaseGameControls];
    self.captured=captured;
    self.hasCapturedGame|=captured;
    self.hasLastHover=NO;
    [self refreshSceneState];
    if(captured)[self becomeFirstResponder];
    [self requestPointerLock];
    for(UIButton *button in self.controls){
        if(button.tag==CONTROL_ESCAPE){
            button.hidden=!self.hasCapturedGame;
            button.accessibilityLabel=captured?@"Pause":@"Back to game";
            [button setTitle:captured?@"Ⅱ":@"×" forState:UIControlStateNormal];
        }else button.hidden=!captured;
    }
    [self.pointerInteraction invalidate];
    [self logInputState:@"capture-change"];
    [self showDiagnostics:@"capture-change"];
}
/* Absolute point coordinates match glfwGetWindowSize. Pixel scale belongs to framebuffer size. */
- (void)touchesBegan:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    if(!self.handle||self.primaryTouch)return;
    [self refreshSceneState];
    UITouch *touch=touches.anyObject;
    BOOL indirect=touch.type==UITouchTypeIndirectPointer;
    // GCMouse supplies hardware mouse/trackpad clicks in game; do not forward UIKit duplicates.
    // If GCMouse is absent, the indirect touch is the only click channel and is kept.
    if(self.captured&&indirect&&self.nativeMouseConnected)return;
    self.primaryTouch=touch;
    CGPoint p=[touch locationInView:self];
    if(!self.captured)faot_glfw_enqueue(self.handle,FAOT_EVENT_CURSOR,p.x,p.y,0,0);
    // Finger drags look around without also attacking. Indirect pointer clicks keep their button.
    self.primaryButton=self.captured&&!indirect?-1:
        ((event.buttonMask&UIEventButtonMaskSecondary)?1:0);
    if(self.primaryButton>=0&&faot_glfw_enqueue(self.handle,FAOT_EVENT_BUTTON,self.primaryButton,1,0,0)){
        faot_pointer_note_button(&_pointerState,1);
        inputLog(@"button source=%@ index=%d pressed=1 captured=%d",
                 indirect?@"uikit-indirect":@"uikit-touch",self.primaryButton,self.captured);
    }
}
- (void)touchesMoved:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    if(!self.handle)return;
    UITouch *touch=self.primaryTouch;if(!touch||![touches containsObject:touch])return;
    CGPoint p=[touch locationInView:self],old=[touch previousLocationInView:self];
    if(self.captured){
        if(touch.type==UITouchTypeIndirectPointer&&self.nativeMouseConnected)return;
        if(self.nativeMouseConnected&&CACurrentMediaTime()-self.lastMouseMotion<0.15)return;
        [self sendRelativeX:p.x-old.x y:p.y-old.y source:@"touch-drag"];
    }
    else if(event.allTouches.count>1)faot_glfw_enqueue(self.handle,FAOT_EVENT_SCROLL,(p.x-old.x)/24.0,(old.y-p.y)/24.0,0,0);
    else faot_glfw_enqueue(self.handle,FAOT_EVENT_CURSOR,p.x,p.y,0,0);
}
- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    (void)event;
    if(self.primaryTouch&&[touches containsObject:self.primaryTouch]){
        if(self.handle&&self.primaryButton>=0){
            if(faot_glfw_enqueue(self.handle,FAOT_EVENT_BUTTON,self.primaryButton,0,0,0))
                inputLog(@"button source=uikit index=%d pressed=0",self.primaryButton);
        }
        self.primaryTouch=nil;
        self.primaryButton=-1;
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
- (BOOL)prefersPointerLocked { return ((FAOTMetalView *)self.view).wantsPointerLock; }
- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    FAOTMetalView *view=(FAOTMetalView *)self.view;
    [view setSceneActive:YES];
    [view refreshSceneState];
    [view requestPointerLock];
    [view showDiagnostics:@"appear"];
}
- (void)viewWillDisappear:(BOOL)animated {
    [super viewWillDisappear:animated];
    [(FAOTMetalView *)self.view setSceneActive:NO];
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
@property(nonatomic,strong) id mouseCurrentToken;
@property(nonatomic,strong) id mouseNotCurrentToken;
@property(nonatomic,strong) GCMouse *mouse;
- (void)attachMouse:(GCMouse *)mouse;
- (void)attachCurrentMouse;
@end
@implementation FAOTSurface
- (void)attachCurrentMouse {
    [self attachMouse:GCMouse.current ?: [GCMouse mice].firstObject];
}
- (void)attachMouse:(GCMouse *)mouse {
    if(self.mouse==mouse){
        if(mouse)self.view.nativeMouseConnected=YES;
        [self.view refreshSceneState];
        [self.view requestPointerLock];
        return;
    }
    if(mouse&&!mouse.mouseInput){
        [self.view logInputState:@"mouse-without-input"];
        return;
    }
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
    [self.view refreshSceneState];
    [self.view logInputState:mouse?@"mouse-connect":@"mouse-disconnect"];
    if(!mouse)return;

    __weak FAOTMetalView *weakView=self.view;
    GCMouseInput *input=mouse.mouseInput;
    // GameController reports unaccelerated raw deltas. The view applies pointer-lock policy.
    input.mouseMovedHandler=^(GCMouseInput *sender,float dx,float dy){
        (void)sender;
        dispatch_block_t forward=^{
            FAOTMetalView *view=weakView;
            if(view)[view mouseMovedDX:dx dy:dy];
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
            if(view)[view sendScrollX:dx y:dy source:@"gcmouse"];
        };
        if(NSThread.isMainThread)forward();else dispatch_async(dispatch_get_main_queue(),forward);
    };
    [self.view logInputState:@"mouse-attached"];
}

@end

void faot_surface_screen(GLFWvidmode *mode) {
    onMain(^{
        UIWindowScene *scene=activeScene();
        CGSize size=sceneSize(scene);
        UIScreen *screen=scene.screen ?: UIScreen.mainScreen;
        if(size.width<=0||size.height<=0)size=screen.bounds.size;
        *mode=(GLFWvidmode){(int)size.width,(int)size.height,8,8,8,(int)screen.maximumFramesPerSecond};
    });
}
void *faot_surface_create(GLFWwindow *handle,int *width,int *height,int *pw,int *ph) {
    __block FAOTSurface *surface=nil;
    onMain(^{
        UIWindowScene *scene=activeScene();
        if(!scene)return;
        id<MTLDevice> device=MTLCreateSystemDefaultDevice();
        if(!device)return;
        CGSize visible=sceneSize(scene);
        CGRect frame=CGRectMake(0,0,visible.width,visible.height);
        surface=[FAOTSurface new];
        for(UIWindow *window in scene.windows)if(window.isKeyWindow)surface.previous=window;
        surface.window=[[UIWindow alloc] initWithWindowScene:scene];
        surface.window.frame=frame;
        surface.window.backgroundColor=UIColor.blackColor;
        UIViewController *controller=[FAOTGameController new];
        surface.view=[[FAOTMetalView alloc] initWithFrame:frame];
        surface.view.handle=handle;
        surface.view.multipleTouchEnabled=YES;
        surface.view.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;
        surface.view.active=(scene.activationState==UISceneActivationStateForegroundActive);
        [surface.view installControls];
        CAMetalLayer *layer=(CAMetalLayer *)surface.view.layer;
        layer.device=device;
        layer.pixelFormat=MTLPixelFormatBGRA8Unorm;
        layer.framebufferOnly=YES;
        layer.opaque=YES;
        controller.view=surface.view;
        surface.window.rootViewController=controller;
        [surface.window makeKeyAndVisible];
        [surface.view becomeFirstResponder];
        [surface.view layoutIfNeeded];
        CGFloat scale=scene.screen.scale ?: UIScreen.mainScreen.scale;
        if(scale<=0)scale=1;
        layer.contentsScale=scale;
        layer.drawableSize=CGSizeMake(round(surface.view.bounds.size.width*scale),
                                       round(surface.view.bounds.size.height*scale));
        *width=(int)round(surface.view.bounds.size.width);
        *height=(int)round(surface.view.bounds.size.height);
        *pw=(int)layer.drawableSize.width;*ph=(int)layer.drawableSize.height;
        [surface.view refreshSceneState];
        [surface.view logInputState:@"surface-created"];
        [surface.view showDiagnostics:@"startup"];
        NSNotificationCenter *nc=NSNotificationCenter.defaultCenter;
        __weak FAOTSurface *weakSurface=surface;
        __weak FAOTMetalView *pointerView=surface.view;
        surface.pointerToken=[nc addObserverForName:UIPointerLockStateDidChangeNotification object:scene.pointerLockState queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            (void)note;
            [pointerView pointerLockChanged:scene.pointerLockState.isLocked];
        }];
        [surface.view pointerLockChanged:scene.pointerLockState.isLocked];
        surface.mouseConnectToken=[nc addObserverForName:GCMouseDidConnectNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            FAOTSurface *current=weakSurface;
            if(!current)return;
            if(!current.mouse||note.object==GCMouse.current)[current attachMouse:(GCMouse *)note.object];
            else [current attachCurrentMouse];
        }];
        surface.mouseDisconnectToken=[nc addObserverForName:GCMouseDidDisconnectNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            FAOTSurface *current=weakSurface;
            if(current&&current.mouse==note.object)[current attachCurrentMouse];
        }];
        surface.mouseCurrentToken=[nc addObserverForName:GCMouseDidBecomeCurrentNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            FAOTSurface *current=weakSurface;
            if(current)[current attachMouse:(GCMouse *)note.object];
        }];
        surface.mouseNotCurrentToken=[nc addObserverForName:GCMouseDidStopBeingCurrentNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            (void)note;
            FAOTSurface *current=weakSurface;
            if(current)[current attachCurrentMouse];
        }];
        [surface attachCurrentMouse];
        // A Magic Keyboard trackpad can be enumerated after the scene connects.
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,1*NSEC_PER_SEC),dispatch_get_main_queue(),^{
            [weakSurface attachCurrentMouse];
        });
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
            [weakSurface attachCurrentMouse];
        });
        surface.foregroundToken=[nc addObserverForName:UISceneDidActivateNotification object:scene queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            (void)note;
            FAOTMetalView *view=pointerView;
            [view setSceneActive:YES];
            [view refreshSceneState];
            [view requestPointerLock];
            [weakSurface attachCurrentMouse];
            [view showDiagnostics:@"foreground"];
            faot_glfw_enqueue(handle,FAOT_EVENT_FOCUS,1,0,0,0);
        }];
        __weak FAOTMetalView *inputView=surface.view;
        surface.backgroundToken=[nc addObserverForName:UISceneWillDeactivateNotification object:scene queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            (void)note;FAOTMetalView *view=inputView;
            [view setSceneActive:NO];
            if(view.primaryTouch){if(view.primaryButton>=0)faot_glfw_enqueue(handle,FAOT_EVENT_BUTTON,view.primaryButton,0,0,0);view.primaryTouch=nil;view.primaryButton=-1;}
            [view releaseGameControls];
            [view.forwardedKeys removeAllIndexes];
            faot_glfw_enqueue(handle,FAOT_EVENT_FOCUS,0,0,0,0);
        }];
    });
    return (__bridge_retained void *)surface;
}
void faot_surface_destroy(void *raw) {
    if(!raw)return;
    onMain(^{
        FAOTSurface *surface=(__bridge_transfer FAOTSurface *)raw;
        surface.view.handle=NULL;
        NSNotificationCenter *nc=NSNotificationCenter.defaultCenter;
        if(surface.foregroundToken)[nc removeObserver:surface.foregroundToken];
        if(surface.backgroundToken)[nc removeObserver:surface.backgroundToken];
        if(surface.pointerToken)[nc removeObserver:surface.pointerToken];
        if(surface.mouseConnectToken)[nc removeObserver:surface.mouseConnectToken];
        if(surface.mouseDisconnectToken)[nc removeObserver:surface.mouseDisconnectToken];
        if(surface.mouseCurrentToken)[nc removeObserver:surface.mouseCurrentToken];
        if(surface.mouseNotCurrentToken)[nc removeObserver:surface.mouseNotCurrentToken];
        [surface.view logInputState:@"surface-destroy"];
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
