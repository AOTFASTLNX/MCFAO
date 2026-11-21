//
//  FAOTLauncherViewController.m
//  Landscape launcher shell: sidebar plus game, account, resource and settings pages.
//
#import "FAOTLauncherViewController.h"
#import "FAOTLauncherPages.h"
#import "FAOTLauncherTheme.h"
#import "FAOTAccountStore.h"
#include <unistd.h>
#import <QuartzCore/QuartzCore.h>
#import <CoreImage/CoreImage.h>

NSString *const FAOTPlayerNameDefaultsKey = @"FAOTPlayerName";
NSString *const FAOTMemoryGiBDefaultsKey = @"FAOTMemoryGiB";
NSString *const FAOTControlLayoutDefaultsKey = @"FAOTControlLayout";
NSString *const FAOTLanguageDefaultsKey = @"FAOTLanguage";

#pragma mark - Pojav default layout

/// Mirrors createButton() calls in Pojav's CustomControlsUtils.m (generateAndSaveDefaultControl).
NSString *FAOTPojavDefaultLayoutJSON(void) {
    struct { const char *name; NSInteger code; const char *dx; const char *dy; CGFloat w; CGFloat h; } rows[] = {
        {"Keyboard", -1, "${margin} * 3 + ${width} * 2", "${margin}", 80, 30},
        {"GUI", -2, "${margin}", "${bottom} - ${margin}", 50, 50},
        {"PRI", -3, "${margin}", "${screen_height} - ${margin} * 3 - ${height} * 3", 50, 50},
        {"SEC", -4, "${margin} * 3 + ${width} * 2", "${screen_height} - ${margin} * 3 - ${height} * 3", 50, 50},
        {"Mouse", -5, "${right} - ${margin}", "${margin}", 80, 30},
        {"Debug", 292, "${margin}", "${margin}", 80, 30},
        {"Chat", 'T', "${margin} * 2 + ${width}", "${margin}", 80, 30},
        {"Tab", 258, "${margin} * 4 + ${width} * 3", "${margin}", 80, 30},
        {"Opti-Zoom", 'C', "${margin} * 5 + ${width} * 4", "${margin}", 80, 30},
        {"Offhand", 'F', "${margin} * 6 + ${width} * 5", "${margin}", 80, 30},
        {"3rd", 294 /* F5 */, "${margin}", "${margin} * 2 + ${height}", 80, 30},
        {"Up", 'W', "${margin} * 2 + ${width}", "${bottom} - ${margin} * 3 - ${height} * 2", 50, 50},
        {"Left", 'A', "${margin}", "${bottom} - ${margin} * 2 - ${height}", 50, 50},
        {"Down", 'S', "${margin} * 2 + ${width}", "${bottom} - ${margin}", 50, 50},
        {"Right", 'D', "${margin} * 3 + ${width} * 2", "${bottom} - ${margin} * 2 - ${height}", 50, 50},
        {"Inventory", 'E', "${margin} * 3 + ${width} * 2", "${bottom} - ${margin}", 50, 50},
        {"Sneak", 340 /* left shift */, "${margin} * 2 + ${width}", "${screen_height} - ${margin} * 2 - ${height} * 2", 50, 50},
        {"Jump", 32 /* space */, "${right} - ${margin} * 2 - ${width}", "${bottom} - ${margin} * 2 - ${height}", 50, 50},
        {"Esc", 256, "${right} - ${margin}", "${bottom} - ${margin}", 80, 30},
    };
    NSMutableArray *list = [NSMutableArray array];
    for (unsigned i = 0; i < sizeof(rows) / sizeof(rows[0]); i++) {
        [list addObject:@{
            @"name": @(rows[i].name),
            @"keycodes": @[@(rows[i].code)],
            @"dynamicX": @(rows[i].dx),
            @"dynamicY": @(rows[i].dy),
            @"width": @(rows[i].w),
            @"height": @(rows[i].h),
            @"opacity": @1.0,
            @"cornerRadius": @0,
            @"bgColor": @(0x4d000000),
            @"displayInGame": @YES,
            @"displayInMenu": @YES,
        }];
    }
    NSDictionary *root = @{ @"version": @5, @"scaledAt": @100, @"mControlDataList": list };
    NSData *data = [NSJSONSerialization dataWithJSONObject:root options:0 error:nil];
    return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"{}";
}

#pragma mark - Sidebar item

@interface FAOTSidebarItem : UIControl
@property (nonatomic, strong) UIImageView *iconView;
@property (nonatomic, strong) UILabel *titleLabel;
- (instancetype)initWithTitle:(NSString *)title symbol:(NSString *)symbol;
- (void)setActive:(BOOL)active;
@end

static void FAOTUpdateLauncherBackdrop(CAGradientLayer *backdrop, UITraitCollection *traits) {
    BOOL dark = traits.userInterfaceStyle == UIUserInterfaceStyleDark;
    UIColor *start = dark ? FAOTRGBA(0.07, 0.08, 0.10, 1) : FAOTRGBA(0.94, 0.95, 0.97, 1);
    UIColor *middle = dark ? FAOTRGBA(0.13, 0.14, 0.17, 1) : FAOTRGBA(0.86, 0.87, 0.89, 1);
    UIColor *end = dark ? FAOTRGBA(0.06, 0.065, 0.08, 1) : FAOTRGBA(0.97, 0.97, 0.98, 1);
    backdrop.colors = @[(id)start.CGColor, (id)middle.CGColor, (id)end.CGColor];
}

@implementation FAOTSidebarItem

- (instancetype)initWithTitle:(NSString *)title symbol:(NSString *)symbol {
    self = [super initWithFrame:CGRectZero];
    if (!self) return nil;
    self.layer.cornerRadius = 10;

    UIImageSymbolConfiguration *configuration = [UIImageSymbolConfiguration configurationWithPointSize:14 weight:UIImageSymbolWeightMedium];
    self.iconView = [[UIImageView alloc] initWithImage:[UIImage systemImageNamed:symbol withConfiguration:configuration]];
    self.iconView.translatesAutoresizingMaskIntoConstraints = NO;
    self.iconView.contentMode = UIViewContentModeScaleAspectFit;
    [self.iconView.widthAnchor constraintEqualToConstant:18].active = YES;

    self.titleLabel = FAOTMakeLabel(title, 13, UIFontWeightSemibold, FAOTSecondaryTextColor());
    UIStackView *row = [[UIStackView alloc] initWithArrangedSubviews:@[self.iconView, self.titleLabel]];
    row.axis = UILayoutConstraintAxisHorizontal;
    row.alignment = UIStackViewAlignmentCenter;
    row.spacing = 10;
    row.userInteractionEnabled = NO;
    row.translatesAutoresizingMaskIntoConstraints = NO;
    [self addSubview:row];
    [NSLayoutConstraint activateConstraints:@[
        [row.leadingAnchor constraintEqualToAnchor:self.leadingAnchor constant:12],
        [row.trailingAnchor constraintLessThanOrEqualToAnchor:self.trailingAnchor constant:-8],
        [row.centerYAnchor constraintEqualToAnchor:self.centerYAnchor],
        [self.heightAnchor constraintEqualToConstant:42],
    ]];
    [self setActive:NO];
    return self;
}

- (void)setActive:(BOOL)active {
    self.backgroundColor = UIColor.clearColor;
    self.iconView.tintColor = active ? FAOTAccentColor() : FAOTMutedTextColor();
    self.titleLabel.textColor = active ? FAOTPrimaryTextColor() : FAOTSecondaryTextColor();
}

@end

#pragma mark - Launcher

@interface FAOTLauncherViewController () <FAOTLauncherPageHost>
@property (nonatomic, strong) CAGradientLayer *backdrop;
@property (nonatomic, strong) UIView *sidebar;
@property (nonatomic, strong) UIView *sidebarIndicator;
@property (nonatomic, strong) NSLayoutConstraint *sidebarIndicatorCenterY;
@property (nonatomic, strong) UIView *content;
@property (nonatomic, strong) UIImageView *transitionBlurView;
@property (nonatomic, strong) UIImage *transitionBlurSource;
@property (nonatomic, strong) CIContext *transitionBlurContext;
@property (nonatomic, strong) CADisplayLink *transitionBlurLink;
@property (nonatomic, assign) CFTimeInterval transitionBlurStart;
@property (nonatomic, strong) NSMutableArray<FAOTSidebarItem *> *sidebarItems;
@property (nonatomic, strong) NSDictionary<NSString *, UIViewController<FAOTLauncherPage> *> *pages;
@property (nonatomic, strong) UIViewController<FAOTLauncherPage> *visiblePage;
@property (nonatomic, copy) NSString *visibleKey;
@property (nonatomic, strong) FAOTGamePageController *gamePage;
@property (nonatomic, strong) UILabel *accountFooter;
@property (nonatomic, assign) BOOL launchedInThisProcess;
@property (nonatomic, assign) NSUInteger pageTransitionGeneration;
@end

@implementation FAOTLauncherViewController

+ (NSUserDefaults *)defaults { return NSUserDefaults.standardUserDefaults; }

+ (FAOTControlLayout *)activeLayout {
    NSString *name = [[self defaults] stringForKey:FAOTControlLayoutDefaultsKey];
    if (name.length == 0) name = @"default";
    FAOTControlLayout *layout = [FAOTControlLayout loadNamed:name];
    if (!layout) {
        layout = [FAOTControlLayout defaultLayout];
        [layout saveNamed:name error:nil];
    }
    return layout;
}

- (BOOL)prefersStatusBarHidden { return YES; }

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = FAOTBackgroundColor();
    [FAOTLogStore pruneToRetention:FAOTLauncherSettings.shared.logRetention];
    self.backdrop = [CAGradientLayer layer];
    FAOTUpdateLauncherBackdrop(self.backdrop, self.traitCollection);
    self.backdrop.startPoint = CGPointMake(0, 0);
    self.backdrop.endPoint = CGPointMake(1, 1);
    [self.view.layer insertSublayer:self.backdrop atIndex:0];

    [self buildSidebar];
    self.content = [UIView new];
    self.content.clipsToBounds = YES;
    self.content.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.content];
    [NSLayoutConstraint activateConstraints:@[
        [self.content.topAnchor constraintEqualToAnchor:self.view.topAnchor],
        [self.content.leadingAnchor constraintEqualToAnchor:self.sidebar.trailingAnchor],
        [self.content.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [self.content.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],
    ]];
    // A real gaussian blur that can be animated: the content is snapshotted, and
    // Core Image blurs that still image with a radius driven frame by frame.
    // UIVisualEffectView cannot animate its blur radius, and re-renders its
    // backdrop after the animation, which is what caused the late flash.
    self.transitionBlurView = [[UIImageView alloc] initWithFrame:CGRectZero];
    self.transitionBlurView.userInteractionEnabled = NO;
    self.transitionBlurView.contentMode = UIViewContentModeScaleToFill;
    self.transitionBlurView.clipsToBounds = YES;
    self.transitionBlurView.alpha = 0;
    self.transitionBlurView.hidden = YES;
    // Positioned by hand: it needs to be larger than the content area so the
    // drift at the end of the transition cannot expose the sharp page beneath.
    self.transitionBlurView.translatesAutoresizingMaskIntoConstraints = YES;
    [self.content addSubview:self.transitionBlurView];
    self.transitionBlurContext = [CIContext contextWithOptions:@{kCIContextUseSoftwareRenderer: @NO}];
    [self buildPages];
    [self showPage:@"game"];
}

- (void)buildSidebar {
    self.sidebar = [UIView new];
    self.sidebar.backgroundColor = FAOTDynamicColor(FAOTRGBA(0.90, 0.91, 0.93, 0.92), FAOTRGBA(0.035, 0.04, 0.05, 0.92));
    self.sidebar.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.sidebar];
    [NSLayoutConstraint activateConstraints:@[
        [self.sidebar.topAnchor constraintEqualToAnchor:self.view.topAnchor],
        [self.sidebar.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [self.sidebar.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],
        [self.sidebar.widthAnchor constraintEqualToConstant:190],
    ]];
    UIView *hairline = [UIView new];
    hairline.backgroundColor = FAOTHairlineColor();
    hairline.translatesAutoresizingMaskIntoConstraints = NO;
    [self.sidebar addSubview:hairline];
    [NSLayoutConstraint activateConstraints:@[
        [hairline.trailingAnchor constraintEqualToAnchor:self.sidebar.trailingAnchor],
        [hairline.topAnchor constraintEqualToAnchor:self.sidebar.topAnchor],
        [hairline.bottomAnchor constraintEqualToAnchor:self.sidebar.bottomAnchor],
        [hairline.widthAnchor constraintEqualToConstant:1],
    ]];

    UILabel *brand = FAOTMakeLabel(@"Native Craft Launcher", 17, UIFontWeightBold, FAOTPrimaryTextColor());
    UIStackView *heading = FAOTMakeStack(@[brand], 2);

    NSArray *titles = @[@"游戏", @"账号", @"资源", @"设置"];
    NSArray *symbols = @[@"gamecontroller", @"person.crop.circle", @"shippingbox", @"gearshape"];
    self.sidebarItems = [NSMutableArray array];
    UIStackView *nav = FAOTMakeStack(@[], 6);
    for (NSUInteger index = 0; index < titles.count; index++) {
        FAOTSidebarItem *item = [[FAOTSidebarItem alloc] initWithTitle:titles[index] symbol:symbols[index]];
        item.tag = (NSInteger)index;
        [item addTarget:self action:@selector(sidebarTapped:) forControlEvents:UIControlEventTouchUpInside];
        [self.sidebarItems addObject:item];
        [nav addArrangedSubview:item];
    }
    self.accountFooter = FAOTMakeLabel(@"", 10, UIFontWeightMedium, FAOTMutedTextColor());
    UIView *spacer = [UIView new];
    [spacer setContentHuggingPriority:1 forAxis:UILayoutConstraintAxisVertical];
    UIStackView *column = FAOTMakeStack(@[heading, nav, spacer, self.accountFooter], 20);
    column.translatesAutoresizingMaskIntoConstraints = NO;
    [self.sidebar addSubview:column];
    UILayoutGuide *safe = self.sidebar.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [column.topAnchor constraintEqualToAnchor:safe.topAnchor constant:22],
        [column.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:12],
        [column.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-12],
        [column.bottomAnchor constraintEqualToAnchor:self.sidebar.bottomAnchor constant:-16],
    ]];

    // The indicator shares the navigation item's geometry, so it must be built
    // only after the items are attached to the sidebar's view hierarchy.
    self.sidebarIndicator = [UIView new];
    self.sidebarIndicator.backgroundColor = FAOTDynamicColor(FAOTRGBA(0.10, 0.12, 0.15, 0.10), FAOTRGBA(1, 1, 1, 0.10));
    self.sidebarIndicator.layer.cornerRadius = 10;
    self.sidebarIndicator.userInteractionEnabled = NO;
    self.sidebarIndicator.translatesAutoresizingMaskIntoConstraints = NO;
    [self.sidebar insertSubview:self.sidebarIndicator atIndex:0];
    FAOTSidebarItem *firstItem = self.sidebarItems.firstObject;
    self.sidebarIndicatorCenterY = [self.sidebarIndicator.centerYAnchor constraintEqualToAnchor:firstItem.centerYAnchor];
    [NSLayoutConstraint activateConstraints:@[
        [self.sidebarIndicator.leadingAnchor constraintEqualToAnchor:firstItem.leadingAnchor],
        [self.sidebarIndicator.trailingAnchor constraintEqualToAnchor:firstItem.trailingAnchor],
        [self.sidebarIndicator.heightAnchor constraintEqualToAnchor:firstItem.heightAnchor],
        self.sidebarIndicatorCenterY,
    ]];
}

- (void)traitCollectionDidChange:(UITraitCollection *)previousTraitCollection {
    [super traitCollectionDidChange:previousTraitCollection];
    if (@available(iOS 13.0, *)) {
        if ([self.traitCollection hasDifferentColorAppearanceComparedToTraitCollection:previousTraitCollection]) {
            FAOTUpdateLauncherBackdrop(self.backdrop, self.traitCollection);
        }
    }
}

- (void)buildPages {
    self.gamePage = [[FAOTGamePageController alloc] initWithHost:self];
    FAOTAccountPageController *account = [[FAOTAccountPageController alloc] initWithHost:self];
    FAOTResourcesPageController *resources = [[FAOTResourcesPageController alloc] initWithHost:self];
    FAOTSettingsPageController *settings = [[FAOTSettingsPageController alloc] initWithHost:self];
    self.pages = @{@"game": self.gamePage, @"account": account, @"resources": resources, @"settings": settings};
    for (NSString *key in self.pages) {
        UIViewController<FAOTLauncherPage> *page = self.pages[key];
        [self addChildViewController:page];
        page.view.translatesAutoresizingMaskIntoConstraints = NO;
        page.view.hidden = YES;
        [self.content addSubview:page.view];
        [NSLayoutConstraint activateConstraints:@[
            [page.view.topAnchor constraintEqualToAnchor:self.content.topAnchor],
            [page.view.leadingAnchor constraintEqualToAnchor:self.content.leadingAnchor],
            [page.view.trailingAnchor constraintEqualToAnchor:self.content.trailingAnchor],
            [page.view.bottomAnchor constraintEqualToAnchor:self.content.bottomAnchor],
        ]];
        [page didMoveToParentViewController:self];
    }
    self.accountFooter.text = [NSString stringWithFormat:@"%@ · %@",
                               FAOTAccountStore.shared.activeAccount.name,
                               FAOTAccountStore.shared.activeAccount.kindTitle];
}

- (void)showPage:(NSString *)key {
    UIViewController<FAOTLauncherPage> *page = self.pages[key];
    if (!page) return;
    NSArray *keys = @[@"game", @"account", @"resources", @"settings"];
    NSUInteger newIndex = [keys indexOfObject:key];
    if (newIndex == NSNotFound) return;
    if (page == self.visiblePage) {
        [self moveSidebarIndicatorToIndex:newIndex animated:YES];
        [page refreshPage];
        return;
    }

    NSUInteger oldIndex = self.visibleKey ? [keys indexOfObject:self.visibleKey] : newIndex;
    // Moving further down the sidebar lifts the content up, the way scrolling a
    // vertical list does; moving back up drops the content down again.
    CGFloat direction = (oldIndex == NSNotFound || newIndex >= oldIndex) ? 1.0 : -1.0;

    UIView *oldView = self.visiblePage.view;
    NSUInteger generation = ++self.pageTransitionGeneration;
    for (UIViewController<FAOTLauncherPage> *candidate in self.pages.allValues) {
        UIView *view = candidate.view;
        if (view == page.view || view == oldView) continue;
        view.hidden = YES;
        view.alpha = 1;
        view.transform = CGAffineTransformIdentity;
    }

    BOOL animated = oldView != nil;
    // Reduce Motion skips the frozen-frame blur and keeps the slide, so the
    // page change is still readable without the extra motion.
    BOOL blurring = animated && !FAOTLauncherSettings.shared.reduceLauncherMotion
        ? [self startTransitionBlur]
        : NO;

    // Prepare the incoming page while it is still hidden so no opaque frame is
    // committed before the transition begins.
    page.view.alpha = animated ? 0 : 1;
    page.view.transform = animated
        ? CGAffineTransformMakeTranslation(0, direction * 46)
        : CGAffineTransformIdentity;
    page.view.hidden = NO;
    if (page.view.superview != self.content) {
        [self.content addSubview:page.view];
        [NSLayoutConstraint activateConstraints:@[
            [page.view.topAnchor constraintEqualToAnchor:self.content.topAnchor],
            [page.view.leadingAnchor constraintEqualToAnchor:self.content.leadingAnchor],
            [page.view.trailingAnchor constraintEqualToAnchor:self.content.trailingAnchor],
            [page.view.bottomAnchor constraintEqualToAnchor:self.content.bottomAnchor],
        ]];
    }
    [self.content bringSubviewToFront:page.view];
    // The frozen snapshot covers the content while it blurs and drifts, then
    // dissolves to reveal the incoming page that is sliding in underneath.
    if (blurring) {
        oldView.hidden = YES;
        [self.content bringSubviewToFront:self.transitionBlurView];
    }

    self.visiblePage = page;
    self.visibleKey = key;
    for (NSUInteger index = 0; index < self.sidebarItems.count; index++) {
        [self.sidebarItems[index] setActive:[keys[index] isEqual:key]];
    }
    [self moveSidebarIndicatorToIndex:newIndex animated:YES];
    [page refreshPage];

    if (!animated) {
        [self stopTransitionBlur];
        return;
    }

    if (oldView.alpha != 1) oldView.alpha = 1;
    if (!CGAffineTransformEqualToTransform(oldView.transform, CGAffineTransformIdentity)) {
        oldView.transform = CGAffineTransformIdentity;
    }
    // Without the frozen snapshot the outgoing page is what the user sees, so
    // it is dismissed first. Letting both pages animate at once made them
    // overlap through each other's translucent cards.
    void (^slideIn)(void) = ^{
        [UIView animateWithDuration:0.42
                          delay:0
         usingSpringWithDamping:0.82
          initialSpringVelocity:0.5
                        options:UIViewAnimationOptionBeginFromCurrentState | UIViewAnimationOptionAllowUserInteraction
                     animations:^{
        page.view.alpha = 1;
        page.view.transform = CGAffineTransformIdentity;
        if (blurring) {
            // Move the frozen page up (or down) and stretch it by the same amount
            // so its leading edge stays flush with the content edge. Moving it
            // alone left a strip of the sharp incoming page visible.
            CGFloat drift = -direction * kTransitionBlurDrift;
            CGFloat height = MAX(1.0, CGRectGetHeight(self.content.bounds));
            CGFloat scaleY = (height + ABS(drift)) / height;
            self.transitionBlurView.transform = CGAffineTransformConcat(
                CGAffineTransformMakeTranslation(0, drift),
                CGAffineTransformMakeScale(1.0, scaleY));
        }
    } completion:^(BOOL finished) {
        if (generation != self.pageTransitionGeneration) return;
        // Take the outgoing view out of the hierarchy instead of toggling
        // hidden/alpha on it. Property changes on a view that is still mounted
        // schedule extra layout and drawing passes, which repainted the content
        // about a second after the transition had finished.
        if (oldView.superview == self.content) [oldView removeFromSuperview];
        [self stopTransitionBlur];
    }];
    };

    if (blurring) {
        slideIn();
        return;
    }

    // Reduce Motion: fade the outgoing page out first, then start the slide
    // slightly before the fade ends so the content area is never left blank.
    [UIView animateWithDuration:0.12
                          delay:0
                        options:UIViewAnimationOptionCurveEaseIn
                     animations:^{
        oldView.alpha = 0;
        oldView.transform = CGAffineTransformMakeTranslation(0, -direction * 16);
    } completion:^(BOOL finished) {
        if (generation != self.pageTransitionGeneration) return;
    }];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.09 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        if (generation != self.pageTransitionGeneration) return;
        slideIn();
    });
}

#pragma mark - Animated gaussian blur

/// How far the snapshot layer drifts while it blurs. The layer is scaled up by
/// exactly enough that the leading edge stays on the content edge, because the
/// content is pinned to the view's edges and cannot be snapshotted with padding.
static const CGFloat kTransitionBlurDrift = 22.0;

/// Freezes the content area and returns YES when the blur overlay is up.
///
/// The snapshot is taken synchronously, before any page view is touched, and
/// the display link starts in the same run loop pass as the page animation.
/// Taking the snapshot on a later pass (with afterScreenUpdates:YES) forced a
/// second full render of the already-transitioned hierarchy, so the blur ended
/// up playing after the transition had finished and read as a repeated fade.
- (BOOL)startTransitionBlur {
    [self stopTransitionBlur];
    CGRect bounds = self.content.bounds;
    if (bounds.size.width < 1 || bounds.size.height < 1) return NO;

    // Snapshot the whole launcher and crop to the content area. The backdrop is
    // a CAGradientLayer, so drawing the root view is what captures it exactly;
    // the result is opaque, which stops the sharp incoming page from showing
    // through the transparent stretches of the blurred copy.
    UIGraphicsImageRendererFormat *format = [UIGraphicsImageRendererFormat defaultFormat];
    format.opaque = YES;
    // 1x is enough: the snapshot is only ever shown while blurred, and the
    // smaller bitmap keeps a full-screen Core Image blur inside the frame
    // budget. Radius is expressed in the image's pixels, which maps back to the
    // same number of points on screen.
    format.scale = 1.0;
    CGRect rootBounds = self.view.bounds;
    UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithSize:rootBounds.size format:format];
    UIImage *full = [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) {
        [self.view drawViewHierarchyInRect:rootBounds afterScreenUpdates:NO];
    }];
    // The renderer is 1x, so the content's frame in points is also its crop
    // rectangle in pixels.
    CGRect cropRect = self.content.frame;
    CGImageRef cropped = full.CGImage ? CGImageCreateWithImageInRect(full.CGImage, cropRect) : NULL;
    if (!cropped) return NO;
    UIImage *snapshot = [UIImage imageWithCGImage:cropped scale:1.0 orientation:UIImageOrientationUp];
    CGImageRelease(cropped);

    self.transitionBlurSource = snapshot;
    self.transitionBlurView.image = snapshot;
    self.transitionBlurView.frame = self.content.bounds;
    self.transitionBlurView.center = CGPointMake(CGRectGetMidX(bounds), CGRectGetMidY(bounds));
    self.transitionBlurView.alpha = 1;
    self.transitionBlurView.hidden = NO;
    self.transitionBlurView.transform = CGAffineTransformIdentity;
    [self.content bringSubviewToFront:self.transitionBlurView];

    self.transitionBlurStart = CACurrentMediaTime();
    self.transitionBlurLink = [CADisplayLink displayLinkWithTarget:self selector:@selector(stepTransitionBlur:)];
    [self.transitionBlurLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
    return YES;
}

- (void)stepTransitionBlur:(CADisplayLink *)link {
    if (!self.transitionBlurSource.CGImage) {
        [self stopTransitionBlur];
        return;
    }
    // The blur clears 0.15s before the page slide finishes, so the incoming
    // page is still visibly moving while the frozen frame dissolves. Matching
    // the slide's duration made the page appear to land first and then sit still
    // while the blur faded.
    static const CFTimeInterval kDuration = 0.27;
    static const CGFloat kPeakRadius = 16.0;
    CFTimeInterval elapsed = CACurrentMediaTime() - self.transitionBlurStart;
    CGFloat progress = (CGFloat)(elapsed / kDuration);
    if (progress >= 1.0) {
        [self stopTransitionBlur];
        return;
    }
    // Radius rises to the peak at 45% of the transition and falls back after,
    // smoothstepped so neither end of the ramp shows a step.
    CGFloat ramp = progress < 0.45 ? progress / 0.45 : (1.0 - progress) / 0.55;
    CGFloat shaped = ramp * ramp * (3.0 - 2.0 * ramp);
    // Hold the snapshot opaque while the blur builds, then dissolve it out so it
    // reaches zero exactly when the transition ends and removal cannot jump.
    CGFloat rawFade = progress < 0.28 ? 1.0 : (1.0 - progress) / 0.72;
    self.transitionBlurView.alpha = rawFade * rawFade * (3.0 - 2.0 * rawFade);
    self.transitionBlurView.image = [self blurredImage:self.transitionBlurSource radius:kPeakRadius * shaped];
}

- (UIImage *)blurredImage:(UIImage *)image radius:(CGFloat)radius {
    if (radius <= 0.5 || !image.CGImage) return image;
    CIImage *input = [CIImage imageWithCGImage:image.CGImage];
    // Clamp first so the edges do not fade to transparent under the blur.
    CIFilter *clamp = [CIFilter filterWithName:@"CIAffineClamp"];
    [clamp setValue:input forKey:kCIInputImageKey];
    [clamp setValue:[NSValue valueWithCGAffineTransform:CGAffineTransformIdentity] forKey:kCIInputTransformKey];
    CIImage *clamped = clamp.outputImage ?: input;

    CIFilter *blur = [CIFilter filterWithName:@"CIGaussianBlur"];
    [blur setValue:clamped forKey:kCIInputImageKey];
    [blur setValue:@(radius * image.scale) forKey:kCIInputRadiusKey];
    CIImage *output = blur.outputImage;
    if (!output) return image;

    CGRect extent = CGRectMake(0, 0, CGImageGetWidth(image.CGImage), CGImageGetHeight(image.CGImage));
    CGImageRef rendered = [self.transitionBlurContext createCGImage:output fromRect:extent];
    if (!rendered) return image;
    UIImage *result = [UIImage imageWithCGImage:rendered scale:image.scale orientation:image.imageOrientation];
    CGImageRelease(rendered);
    return result;
}

- (void)stopTransitionBlur {
    [self.transitionBlurLink invalidate];
    self.transitionBlurLink = nil;
    self.transitionBlurView.hidden = YES;
    self.transitionBlurView.alpha = 0;
    self.transitionBlurView.image = nil;
    self.transitionBlurView.transform = CGAffineTransformIdentity;
    self.transitionBlurSource = nil;
}

- (void)moveSidebarIndicatorToIndex:(NSUInteger)index animated:(BOOL)animated {
    if (index >= self.sidebarItems.count || !self.sidebarIndicator) return;
    FAOTSidebarItem *item = self.sidebarItems[index];
    [self.sidebar layoutIfNeeded];
    self.sidebarIndicatorCenterY.active = NO;
    self.sidebarIndicatorCenterY = [self.sidebarIndicator.centerYAnchor constraintEqualToAnchor:item.centerYAnchor];
    self.sidebarIndicatorCenterY.active = YES;
    if (!animated) {
        [self.sidebar layoutIfNeeded];
        return;
    }
    [UIView animateWithDuration:0.46
                          delay:0
         usingSpringWithDamping:0.62
          initialSpringVelocity:0.5
                        options:UIViewAnimationOptionBeginFromCurrentState | UIViewAnimationOptionAllowUserInteraction
                     animations:^{
        [self.sidebar layoutIfNeeded];
    } completion:nil];
}

- (void)sidebarTapped:(FAOTSidebarItem *)sender {
    NSArray *keys = @[@"game", @"account", @"resources", @"settings"];
    if (sender.tag < 0 || sender.tag >= (NSInteger)keys.count) return;
    [self showPage:keys[(NSUInteger)sender.tag]];
}

- (void)viewWillAppear:(BOOL)animated {
    [super viewWillAppear:animated];
    [self.visiblePage refreshPage];
}

- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    [CATransaction begin];
    [CATransaction setDisableActions:YES];
    self.backdrop.frame = self.view.bounds;
    [CATransaction commit];
}

#pragma mark - Page host

- (void)pageRequestedLaunch {
    // A second tap while the runtime is already starting is ignored; the button
    // is disabled and shows a spinner, so it never needs a restart label.
    if (self.launchedInThisProcess) return;
    FAOTAccount *account = FAOTAccountStore.shared.activeAccount;
    FAOTLauncherSettings *settings = FAOTLauncherSettings.shared;
    NSString *name = account.name.length ? account.name : settings.offlineName;
    if (account.kind == FAOTAccountKindOffline) settings.offlineName = name;
    if (!self.onLaunch) {
        [self.gamePage showStatus:@"没有连接运行宿主：main.m 必须设置 onLaunch。"];
        return;
    }
    self.launchedInThisProcess = YES;
    [self.gamePage showStatus:@"正在启动 NCL…"];
    self.onLaunch(name, settings.memoryGiB, settings.layoutName, settings.languageCode);
    [self.gamePage refreshPage];
}

- (void)pageRequestedLayoutEditor {
    NSString *layoutName = FAOTLauncherSettings.shared.layoutName;
    FAOTControlLayout *layout = [FAOTLauncherViewController activeLayout];
    __weak typeof(self) weakSelf = self;
    FAOTControlEditorViewController *editor =
        [[FAOTControlEditorViewController alloc] initWithLayout:layout
                                                     layoutName:layoutName
                                                     completion:^(FAOTControlLayout *updated, BOOL saved) {
        if (saved) {
            FAOTLauncherSettings.shared.layoutName = layoutName;
            [(id<FAOTLauncherPage>)weakSelf.pages[@"settings"] refreshPage];
        }
    }];
    editor.modalPresentationStyle = UIModalPresentationFullScreen;
    [self presentViewController:editor animated:YES completion:nil];
}

- (void)pageRequestedLayoutImport {
    UIAlertController *sheet = [UIAlertController alertControllerWithTitle:@"导入控制布局"
                                                                  message:@"支持 Pojav 的 mControlDataList 结构"
                                                           preferredStyle:UIAlertControllerStyleActionSheet];
    [sheet addAction:[UIAlertAction actionWithTitle:@"Pojav 默认布局" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        [self importLayoutJSON:FAOTPojavDefaultLayoutJSON() source:@"pojav-default"];
    }]];
    [sheet addAction:[UIAlertAction actionWithTitle:@"粘贴 JSON" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        [self promptLayoutPaste];
    }]];
    [sheet addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
    sheet.popoverPresentationController.sourceView = self.view;
    sheet.popoverPresentationController.sourceRect = CGRectMake(CGRectGetMidX(self.view.bounds), CGRectGetMidY(self.view.bounds), 1, 1);
    [self presentViewController:sheet animated:YES completion:nil];
}

- (void)promptLayoutPaste {
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"粘贴布局 JSON"
                                                                  message:@"mControlDataList / control / 裸数组"
                                                           preferredStyle:UIAlertControllerStyleAlert];
    [alert addTextFieldWithConfigurationHandler:^(UITextField *field) {
        field.placeholder = @"{\"mControlDataList\":[...]}";
    }];
    [alert addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"导入" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        [self importLayoutJSON:alert.textFields.firstObject.text source:@"pasted"];
    }]];
    [self presentViewController:alert animated:YES completion:nil];
}

- (void)importLayoutJSON:(NSString *)json source:(NSString *)source {
    NSError *error = nil;
    FAOTControlLayout *layout = [FAOTControlLayout layoutFromPojavData:[json dataUsingEncoding:NSUTF8StringEncoding]
                                                                 error:&error];
    if (!layout) {
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"导入失败"
                                                                      message:error.localizedDescription ?: @"格式无法识别"
                                                               preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"好" style:UIAlertActionStyleDefault handler:nil]];
        [self presentViewController:alert animated:YES completion:nil];
        return;
    }
    NSString *name = [NSString stringWithFormat:@"imported-%@", source];
    [layout saveNamed:name error:nil];
    FAOTLauncherSettings.shared.layoutName = name;
    [(id<FAOTLauncherPage>)self.pages[@"settings"] refreshPage];
}

- (void)pageAccountsChanged {
    FAOTAccount *account = FAOTAccountStore.shared.activeAccount;
    self.accountFooter.text = [NSString stringWithFormat:@"%@ · %@", account.name, account.kindTitle];
    [self.gamePage refreshPage];
}

- (BOOL)pageGameHasLaunched { return self.launchedInThisProcess; }

- (void)pageSetGameStatus:(NSString *)status {
    [self.gamePage showStatus:status];
}

@end
