#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>
#import <GameController/GameController.h>
#include "glfw_lite.h"
#include "input_mapping.h"

enum { CONTROL_BREAK=-1, CONTROL_PLACE=-2, CONTROL_PREVIOUS=-3, CONTROL_NEXT=-4, CONTROL_PICK=-5,
       CONTROL_ESCAPE=256, CONTROL_DEBUG=292 /* GLFW_KEY_F3 */ };
static void onMain(dispatch_block_t block) {
    if (NSThread.isMainThread) block(); else dispatch_sync(dispatch_get_main_queue(),block);
}
static UIWindowScene *activeScene(void) {
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes)
        if ([scene isKindOfClass:UIWindowScene.class] && scene.activationState==UISceneActivationStateForegroundActive)
            return (UIWindowScene *)scene;
    return nil;
}

@interface FAOTMetalView : UIView <UIKeyInput>
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
@property(nonatomic,strong) NSMutableSet<NSNumber *> *heldControls;
- (void)installControls;
- (void)setGameCapture:(BOOL)captured;
- (void)releaseGameControls;
- (void)releaseNativeMouseButtons;
- (void)nativeMouseButton:(int)index pressed:(BOOL)pressed;
- (void)pointerHovered:(UIHoverGestureRecognizer *)recognizer;
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
    const CGFloat size=44,step=48,left=CGRectGetMinX(safe)+8,right=CGRectGetMaxX(safe)-size-8;
    const CGFloat bottom=CGRectGetMaxY(safe)-size-32;
    /* Debug toggle mirrors the pause button in the top-left corner: out of thumb reach and
       deliberately smaller, so it neither competes with combat controls nor hides much HUD. */
    const CGFloat debugSize=36,debugX=left,debugY=CGRectGetMinY(safe)+8+(size-debugSize)/2;
    CGPoint points[]={{left+step,bottom-2*step},{left,bottom-step},{left+step,bottom-step},{left+2*step,bottom-step},
                      {right,bottom-step},{right-step,bottom-step},{right,bottom-2*step},{right-step,bottom-2*step},
                      {right-step,bottom},{right,bottom},{left,bottom},{right,CGRectGetMinY(safe)+8},
                      {debugX,debugY}};
    for(NSUInteger i=0;i<self.controls.count;i++){
        UIButton *button=self.controls[i];
        CGFloat side=button.tag==CONTROL_DEBUG?debugSize:size;
        button.frame=CGRectMake(points[i].x,points[i].y,side,side);
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
    if(!self.handle||self.captured)return;
    if(recognizer.state!=UIGestureRecognizerStateBegan&&recognizer.state!=UIGestureRecognizerStateChanged)return;
    CGPoint p=[recognizer locationInView:self];
    faot_glfw_enqueue(self.handle,FAOT_EVENT_CURSOR,p.x,p.y,0,0);
}
- (void)setGameCapture:(BOOL)captured {
    if(self.captured==captured)return;
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
    input.scroll.valueChangedHandler=^(GCDeviceCursor *sender,float dx,float dy){
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
        layer.framebufferOnly=YES;
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
            (void)note;faot_glfw_enqueue(handle,FAOT_EVENT_FOCUS,1,0,0,0);
        }];
        __weak FAOTMetalView *inputView=surface.view;
        surface.backgroundToken=[nc addObserverForName:UISceneWillDeactivateNotification object:scene queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
            (void)note;FAOTMetalView *view=inputView;
            if(view.primaryTouch){if(view.primaryButton>=0)faot_glfw_enqueue(handle,FAOT_EVENT_BUTTON,view.primaryButton,0,0,0);view.primaryTouch=nil;}
            [view releaseGameControls];
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
