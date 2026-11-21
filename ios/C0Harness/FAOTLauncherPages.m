//
//  FAOTLauncherPages.m
//
#import "FAOTLauncherPages.h"
#import "FAOTLauncherTheme.h"
#import "FAOTAccountStore.h"
#import "FAOTAuthService.h"
#import "FAOTSkinView.h"
#import "FAOTLauncherViewController.h"
#import <math.h>

static NSString *const FAOTYggdrasilServerKey = @"FAOTYggdrasilServer";

#pragma mark - Shared builders

static UIScrollView *FAOTInstallScroll(UIViewController *controller, UIStackView *stack) {
    UIScrollView *scroll = [UIScrollView new];
    scroll.alwaysBounceVertical = YES;
    scroll.showsVerticalScrollIndicator = NO;
    scroll.translatesAutoresizingMaskIntoConstraints = NO;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [controller.view addSubview:scroll];
    [scroll addSubview:stack];
    UILayoutGuide *safe = controller.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [scroll.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [scroll.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [scroll.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [scroll.bottomAnchor constraintEqualToAnchor:controller.view.bottomAnchor],
        [stack.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:22],
        [stack.leadingAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.leadingAnchor constant:24],
        [stack.trailingAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.trailingAnchor constant:-24],
        [stack.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-22],
    ]];
    return scroll;
}

static UIStackView *FAOTPageHeader(NSString *title, NSString *subtitle) {
    UILabel *heading = FAOTMakeLabel(title, 26, UIFontWeightBold, FAOTPrimaryTextColor());
    if (subtitle.length == 0) return FAOTMakeStack(@[heading], 3);
    UILabel *detail = FAOTMakeLabel(subtitle, 13, UIFontWeightRegular, FAOTSecondaryTextColor());
    return FAOTMakeStack(@[heading, detail], 3);
}

static UIView *FAOTPaddedCard(UIView *content, CGFloat padding) {
    UIView *card = FAOTMakeCard();
    content.translatesAutoresizingMaskIntoConstraints = NO;
    [card addSubview:content];
    [NSLayoutConstraint activateConstraints:@[
        [content.topAnchor constraintEqualToAnchor:card.topAnchor constant:padding],
        [content.leadingAnchor constraintEqualToAnchor:card.leadingAnchor constant:padding],
        [content.trailingAnchor constraintEqualToAnchor:card.trailingAnchor constant:-padding],
        [content.bottomAnchor constraintEqualToAnchor:card.bottomAnchor constant:-padding],
    ]];
    return card;
}

/// A metric tile that keeps the caption above the value when the card is tall,
/// and switches to a single row when the card is short. The cards now always
/// split the column in half, so on phone-sized layouts a vertical pair would be
/// clipped.
@interface FAOTMetricTileView : UIView
@property (nonatomic, strong) UILabel *captionLabel;
@property (nonatomic, strong) UILabel *valueLabel;
@property (nonatomic, strong) UIStackView *stack;
@property (nonatomic, assign) BOOL horizontal;
@end

@implementation FAOTMetricTileView

- (instancetype)initWithCaption:(NSString *)caption value:(UILabel *)value {
    self = [super initWithFrame:CGRectZero];
    if (!self) return nil;
    self.backgroundColor = FAOTDynamicColor(FAOTRGBA(0.93, 0.94, 0.95, 1), FAOTRGBA(1, 1, 1, 0.045));
    self.layer.cornerRadius = 12;
    // Custom views have no intrinsic height. A low-priority floor lets the tile
    // grow with the card while still keeping the text from being crushed.
    NSLayoutConstraint *tileFloor = [self.heightAnchor constraintGreaterThanOrEqualToConstant:54];
    tileFloor.priority = UILayoutPriorityDefaultHigh;
    tileFloor.active = YES;
    _captionLabel = FAOTMakeLabel(caption, 11, UIFontWeightMedium, FAOTMutedTextColor());
    _captionLabel.numberOfLines = 1;
    value.font = [UIFont systemFontOfSize:17 weight:UIFontWeightSemibold];
    value.textColor = FAOTPrimaryTextColor();
    value.numberOfLines = 1;
    _valueLabel = value;
    _stack = [[UIStackView alloc] initWithArrangedSubviews:@[_captionLabel, _valueLabel]];
    _stack.axis = UILayoutConstraintAxisVertical;
    _stack.alignment = UIStackViewAlignmentLeading;
    _stack.spacing = 2;
    _stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self addSubview:_stack];
    // The stack fills the tile's width so both labels can use the full row.
    // With a trailing `lessThanOrEqual` constraint it collapsed to its content
    // width and the value truncated to an ellipsis on compact rows.
    [NSLayoutConstraint activateConstraints:@[
        [_stack.leadingAnchor constraintEqualToAnchor:self.leadingAnchor constant:12],
        [_stack.trailingAnchor constraintEqualToAnchor:self.trailingAnchor constant:-12],
        [_stack.centerYAnchor constraintEqualToAnchor:self.centerYAnchor],
    ]];
    [_captionLabel setContentCompressionResistancePriority:UILayoutPriorityDefaultLow forAxis:UILayoutConstraintAxisHorizontal];
    [_valueLabel setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    [self setContentCompressionResistancePriority:UILayoutPriorityDefaultLow forAxis:UILayoutConstraintAxisVertical];
    return self;
}

- (void)layoutSubviews {
    [super layoutSubviews];
    BOOL compact = CGRectGetHeight(self.bounds) < 52.0;
    if (compact == self.horizontal) return;
    self.horizontal = compact;
    // Keep the caption above the value in both modes. Side by side they do not
    // both fit on a compact tile, and truncating either one loses information.
    // Compact tiles only tighten the gap so the two lines fit the shorter card.
    self.stack.spacing = compact ? 1.0 : 2.0;
    [self setNeedsLayout];
}

@end

static UIView *FAOTMetricTile(NSString *caption, UILabel *value) {
    return [[FAOTMetricTileView alloc] initWithCaption:caption value:value];
}

static NSString *FAOTSizeText(unsigned long long bytes) {
    if (bytes >= 1024ULL * 1024 * 1024) return [NSString stringWithFormat:@"%.1f GB", bytes / 1073741824.0];
    if (bytes >= 1024ULL * 1024) return [NSString stringWithFormat:@"%.1f MB", bytes / 1048576.0];
    if (bytes >= 1024) return [NSString stringWithFormat:@"%.0f KB", bytes / 1024.0];
    return [NSString stringWithFormat:@"%llu B", bytes];
}

static UIStackView *FAOTRow(NSString *title, NSString *detail) {
    UILabel *left = FAOTMakeLabel(title, 13, UIFontWeightMedium, FAOTPrimaryTextColor());
    UILabel *right = FAOTMakeLabel(detail, 12, UIFontWeightRegular, FAOTSecondaryTextColor());
    right.textAlignment = NSTextAlignmentRight;
    UIStackView *row = [[UIStackView alloc] initWithArrangedSubviews:@[left, right]];
    row.axis = UILayoutConstraintAxisHorizontal;
    row.alignment = UIStackViewAlignmentFirstBaseline;
    row.spacing = 12;
    [left setContentCompressionResistancePriority:UILayoutPriorityDefaultLow forAxis:UILayoutConstraintAxisHorizontal];
    [right setContentHuggingPriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    return row;
}

static UIStackView *FAOTValueRow(NSString *title, UILabel *value) {
    UILabel *left = FAOTMakeLabel(title, 13, UIFontWeightMedium, FAOTPrimaryTextColor());
    value.textAlignment = NSTextAlignmentRight;
    UIStackView *row = [[UIStackView alloc] initWithArrangedSubviews:@[left, value]];
    row.axis = UILayoutConstraintAxisHorizontal;
    row.alignment = UIStackViewAlignmentFirstBaseline;
    row.spacing = 12;
    [left setContentCompressionResistancePriority:UILayoutPriorityDefaultLow forAxis:UILayoutConstraintAxisHorizontal];
    [value setContentHuggingPriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    return row;
}

static BOOL FAOTValidOfflineName(NSString *name) {
    if (name.length < 1 || name.length > 16) return NO;
    for (NSUInteger index = 0; index < name.length; index++) {
        unichar c = [name characterAtIndex:index];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_')) return NO;
    }
    return YES;
}

#pragma mark - Game

@interface FAOTGamePageController ()
@property (nonatomic, weak) id<FAOTLauncherPageHost> host;
@property (nonatomic, strong) FAOTSkinView *skinView;
@property (nonatomic, strong) FAOTSkinView *previewSkinView;
@property (nonatomic, strong) UILabel *nameLabel;
@property (nonatomic, strong) UILabel *accountLabel;
@property (nonatomic, strong) UILabel *memoryValue;
@property (nonatomic, strong) UILabel *modsValue;
@property (nonatomic, strong) UILabel *packsValue;
@property (nonatomic, strong) UILabel *shadersValue;
@property (nonatomic, strong) UILabel *statusLabel;
@property (nonatomic, strong) UIButton *launchButton;
@property (nonatomic, strong) UIStackView *savesStack;
@property (nonatomic, strong) UILabel *savesEmptyLabel;
@property (nonatomic, assign) CGFloat panStartYaw;
@property (nonatomic, assign) CGFloat panStartPitch;
@property (nonatomic, strong) UIScrollView *savesScrollView;
@end

#pragma mark - Resources

@interface FAOTResourcesPageController ()
@property (nonatomic, weak) id<FAOTLauncherPageHost> host;
@property (nonatomic, strong) UIStackView *sectionsStack;
@property (nonatomic, strong) UILabel *summaryLabel;
@end

@implementation FAOTResourcesPageController

- (instancetype)initWithHost:(id<FAOTLauncherPageHost>)host {
    self = [super initWithNibName:nil bundle:nil];
    if (self) _host = host;
    return self;
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.clearColor;
    UIStackView *stack = FAOTMakeStack(@[], 14);
    FAOTInstallScroll(self, stack);

    UIStackView *header = FAOTPageHeader(@"资源", @"");
    UIButton *refresh = FAOTMakeButton(@"刷新", FAOTFieldColor(), FAOTPrimaryTextColor());
    refresh.titleLabel.font = [UIFont systemFontOfSize:13 weight:UIFontWeightSemibold];
    [refresh addTarget:self action:@selector(refreshPage) forControlEvents:UIControlEventTouchUpInside];
    [refresh.widthAnchor constraintEqualToConstant:72].active = YES;
    [refresh.heightAnchor constraintEqualToConstant:32].active = YES;
    UIView *spacer = [UIView new];
    [spacer setContentHuggingPriority:1 forAxis:UILayoutConstraintAxisHorizontal];
    UIStackView *headerRow = [[UIStackView alloc] initWithArrangedSubviews:@[header, spacer, refresh]];
    headerRow.axis = UILayoutConstraintAxisHorizontal;
    headerRow.alignment = UIStackViewAlignmentCenter;
    headerRow.spacing = 12;
    [stack addArrangedSubview:headerRow];

    self.summaryLabel = FAOTMakeLabel(@"", 12, UIFontWeightRegular, FAOTSecondaryTextColor());
    [stack addArrangedSubview:self.summaryLabel];
    self.sectionsStack = FAOTMakeStack(@[], 12);
    [stack addArrangedSubview:self.sectionsStack];
    UILabel *note = FAOTMakeLabel(@"AOT 构建会在编译期把 Mod 转换进原生镜像，因此游戏目录不一定保留 JAR。资源包与光影包放在 Documents/game 对应目录即可被游戏读取；此处同时列出构建内置内容。",
                                   11, UIFontWeightRegular, FAOTMutedTextColor());
    [stack addArrangedSubview:note];
}

- (void)refreshPage {
    NSArray *mods = FAOTContentCatalog.mods;
    NSArray *packs = FAOTContentCatalog.resourcePacks;
    NSArray *shaders = FAOTContentCatalog.shaderPacks;
    self.summaryLabel.text = [NSString stringWithFormat:@"%lu 个 Mod · %lu 个资源包 · %lu 个光影包",
                              (unsigned long)mods.count, (unsigned long)packs.count, (unsigned long)shaders.count];
    for (UIView *view in self.sectionsStack.arrangedSubviews.copy) {
        [self.sectionsStack removeArrangedSubview:view];
        [view removeFromSuperview];
    }
    [self.sectionsStack addArrangedSubview:[self sectionWithTitle:@"Mod" items:mods
                                                           empty:@"没有发现可列出的 Mod JAR。当前构建若使用整合包，Mod 已在构建期转换。"]];
    [self.sectionsStack addArrangedSubview:[self sectionWithTitle:@"资源包" items:packs
                                                           empty:@"没有资源包。将 .zip 或解压目录放入 Documents/game/resourcepacks。"]];
    [self.sectionsStack addArrangedSubview:[self sectionWithTitle:@"光影包" items:shaders
                                                           empty:@"没有光影包。将 .zip 或解压目录放入 Documents/game/shaderpacks。"]];
}

- (UIView *)sectionWithTitle:(NSString *)title items:(NSArray<NSDictionary *> *)items empty:(NSString *)empty {
    UILabel *heading = FAOTMakeLabel(title, 16, UIFontWeightBold, FAOTPrimaryTextColor());
    UILabel *count = FAOTMakeLabel([NSString stringWithFormat:@"%lu 项", (unsigned long)items.count],
                                   12, UIFontWeightMedium, FAOTMutedTextColor());
    count.textAlignment = NSTextAlignmentRight;
    UIView *spacer = [UIView new];
    [spacer setContentHuggingPriority:1 forAxis:UILayoutConstraintAxisHorizontal];
    UIStackView *headingRow = [[UIStackView alloc] initWithArrangedSubviews:@[heading, spacer, count]];
    headingRow.axis = UILayoutConstraintAxisHorizontal;
    headingRow.alignment = UIStackViewAlignmentFirstBaseline;
    UIStackView *content = FAOTMakeStack(@[headingRow], 8);
    if (items.count == 0) {
        UILabel *placeholder = FAOTMakeLabel(empty, 12, UIFontWeightRegular, FAOTMutedTextColor());
        [content addArrangedSubview:placeholder];
    } else {
        NSUInteger shown = MIN(items.count, 12);
        for (NSUInteger index = 0; index < shown; index++) {
            NSDictionary *item = items[index];
            NSString *detail = [NSString stringWithFormat:@"%@ · %@", FAOTSizeText([item[@"bytes"] unsignedLongLongValue]), item[@"source"]];
            [content addArrangedSubview:FAOTRow(item[@"name"], detail)];
        }
        if (items.count > shown) {
            UILabel *more = FAOTMakeLabel([NSString stringWithFormat:@"还有 %lu 项未显示", (unsigned long)(items.count - shown)],
                                          11, UIFontWeightRegular, FAOTMutedTextColor());
            [content addArrangedSubview:more];
        }
    }
    return FAOTPaddedCard(content, 14);
}

@end

#pragma mark - Settings

@interface FAOTSettingsPageController ()
@property (nonatomic, weak) id<FAOTLauncherPageHost> host;
@property (nonatomic, strong) UILabel *layoutLabel;
@property (nonatomic, strong) UILabel *memoryCaption;
@property (nonatomic, strong) UISegmentedControl *memoryPicker;
@property (nonatomic, strong) UILabel *retentionCaption;
@property (nonatomic, strong) UISegmentedControl *retentionPicker;
@property (nonatomic, strong) UISegmentedControl *languagePicker;
@property (nonatomic, strong) UISwitch *motionSwitch;
@property (nonatomic, strong) UIScrollView *settingsScroll;
@property (nonatomic, strong) UILabel *versionLabel;
@property (nonatomic, strong) UILabel *buildLabel;
@property (nonatomic, strong) UILabel *testVersionLabel;
@property (nonatomic, strong) UILabel *bundleLabel;
@property (nonatomic, strong) UILabel *statusLabel;
@property (nonatomic, copy) NSArray<NSNumber *> *retentionOptions;
@end

@implementation FAOTSettingsPageController

- (instancetype)initWithHost:(id<FAOTLauncherPageHost>)host {
    self = [super initWithNibName:nil bundle:nil];
    if (self) _host = host;
    return self;
}

- (UISegmentedControl *)segmentedWithItems:(NSArray *)items action:(SEL)action {
    UISegmentedControl *control = [[UISegmentedControl alloc] initWithItems:items];
    control.selectedSegmentTintColor = FAOTAccentColor();
    control.backgroundColor = FAOTFieldColor();
    [control setTitleTextAttributes:@{NSForegroundColorAttributeName: FAOTDynamicColor(UIColor.whiteColor, UIColor.blackColor)} forState:UIControlStateSelected];
    [control setTitleTextAttributes:@{NSForegroundColorAttributeName: FAOTSecondaryTextColor()} forState:UIControlStateNormal];
    [control addTarget:self action:action forControlEvents:UIControlEventValueChanged];
    return control;
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.clearColor;
    UIStackView *stack = FAOTMakeStack(@[], 14);
    self.settingsScroll = FAOTInstallScroll(self, stack);
    [stack addArrangedSubview:FAOTPageHeader(@"设置", @"")];

    self.layoutLabel = FAOTMakeLabel(@"default", 14, UIFontWeightMedium, FAOTPrimaryTextColor());
    UIButton *edit = FAOTMakeButton(@"编辑按键", FAOTFieldColor(), FAOTPrimaryTextColor());
    UIButton *import = FAOTMakeButton(@"导入布局", FAOTFieldColor(), FAOTPrimaryTextColor());
    [edit addTarget:self action:@selector(editLayoutTapped) forControlEvents:UIControlEventTouchUpInside];
    [import addTarget:self action:@selector(importLayoutTapped) forControlEvents:UIControlEventTouchUpInside];
    for (UIButton *button in @[edit, import]) [button.heightAnchor constraintEqualToConstant:38].active = YES;
    UIStackView *layoutActions = [[UIStackView alloc] initWithArrangedSubviews:@[edit, import]];
    layoutActions.axis = UILayoutConstraintAxisHorizontal;
    layoutActions.distribution = UIStackViewDistributionFillEqually;
    layoutActions.spacing = 8;
    UILabel *layoutCaption = FAOTMakeLabel(@"控制布局", 12, UIFontWeightMedium, FAOTMutedTextColor());
    [stack addArrangedSubview:FAOTPaddedCard(FAOTMakeStack(@[layoutCaption, self.layoutLabel, layoutActions], 8), 14)];

    self.memoryCaption = FAOTMakeLabel(FAOTLauncherSettings.shared.deviceMemoryCaption, 12, UIFontWeightRegular, FAOTSecondaryTextColor());
    NSMutableArray *memoryItems = [NSMutableArray array];
    for (NSNumber *value in FAOTLauncherSettings.shared.memoryOptions) [memoryItems addObject:[NSString stringWithFormat:@"%@G", value]];
    self.memoryPicker = [self segmentedWithItems:memoryItems action:@selector(memoryChanged)];
    UILabel *memoryTitle = FAOTMakeLabel(@"Java 内存", 12, UIFontWeightMedium, FAOTMutedTextColor());
    [stack addArrangedSubview:FAOTPaddedCard(FAOTMakeStack(@[memoryTitle, self.memoryPicker, self.memoryCaption], 8), 14)];

    self.retentionOptions = @[@5, @10, @20, @50, @100];
    NSMutableArray *retentionItems = [NSMutableArray array];
    for (NSNumber *value in self.retentionOptions) [retentionItems addObject:[NSString stringWithFormat:@"%@", value]];
    self.retentionPicker = [self segmentedWithItems:retentionItems action:@selector(retentionChanged)];
    self.retentionCaption = FAOTMakeLabel(@"", 12, UIFontWeightRegular, FAOTSecondaryTextColor());
    UIButton *clean = FAOTMakeButton(@"立即清理旧日志", FAOTFieldColor(), FAOTPrimaryTextColor());
    [clean.heightAnchor constraintEqualToConstant:38].active = YES;
    [clean addTarget:self action:@selector(cleanLogsTapped) forControlEvents:UIControlEventTouchUpInside];
    UILabel *logTitle = FAOTMakeLabel(@"日志保留份数", 12, UIFontWeightMedium, FAOTMutedTextColor());
    [stack addArrangedSubview:FAOTPaddedCard(FAOTMakeStack(@[logTitle, self.retentionPicker, self.retentionCaption, clean], 8), 14)];

    self.languagePicker = [self segmentedWithItems:@[@"简体中文", @"English", @"日本語"] action:@selector(languageChanged)];
    UILabel *languageTitle = FAOTMakeLabel(@"游戏语言", 12, UIFontWeightMedium, FAOTMutedTextColor());
    [stack addArrangedSubview:FAOTPaddedCard(FAOTMakeStack(@[languageTitle, self.languagePicker], 8), 14)];

    UILabel *motionTitle = FAOTMakeLabel(@"减弱启动器动态效果", 14, UIFontWeightMedium, FAOTPrimaryTextColor());
    UILabel *motionCaption = FAOTMakeLabel(@"关闭切换页面时的高斯模糊过渡，保留页面滑入。", 12, UIFontWeightRegular, FAOTSecondaryTextColor());
    self.motionSwitch = [[UISwitch alloc] initWithFrame:CGRectZero];
    self.motionSwitch.onTintColor = FAOTAccentColor();
    [self.motionSwitch addTarget:self action:@selector(reduceMotionChanged) forControlEvents:UIControlEventValueChanged];
    [self.motionSwitch setContentHuggingPriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    UIView *motionSpacer = [UIView new];
    [motionSpacer setContentHuggingPriority:1 forAxis:UILayoutConstraintAxisHorizontal];
    UIStackView *motionRow = [[UIStackView alloc] initWithArrangedSubviews:@[motionTitle, motionSpacer, self.motionSwitch]];
    motionRow.axis = UILayoutConstraintAxisHorizontal;
    motionRow.alignment = UIStackViewAlignmentCenter;
    motionRow.spacing = 10;
    [stack addArrangedSubview:FAOTPaddedCard(FAOTMakeStack(@[motionRow, motionCaption], 6), 14)];

    self.versionLabel = FAOTMakeLabel(@"", 13, UIFontWeightMedium, FAOTPrimaryTextColor());
    self.buildLabel = FAOTMakeLabel(@"", 13, UIFontWeightMedium, FAOTPrimaryTextColor());
    self.testVersionLabel = FAOTMakeLabel(@"", 13, UIFontWeightMedium, FAOTPrimaryTextColor());
    self.bundleLabel = FAOTMakeLabel(@"", 13, UIFontWeightMedium, FAOTPrimaryTextColor());
    UILabel *aboutTitle = FAOTMakeLabel(@"关于", 12, UIFontWeightMedium, FAOTMutedTextColor());
    [stack addArrangedSubview:FAOTPaddedCard(FAOTMakeStack(@[aboutTitle,
        FAOTValueRow(@"应用版本", self.versionLabel), FAOTValueRow(@"构建号", self.buildLabel),
        FAOTValueRow(@"测试版本", self.testVersionLabel), FAOTValueRow(@"Bundle ID", self.bundleLabel)], 9), 14)];

    self.statusLabel = FAOTMakeLabel(@"", 11, UIFontWeightRegular, FAOTMutedTextColor());
    [stack addArrangedSubview:self.statusLabel];
}

- (void)refreshPage {
    FAOTLauncherSettings *settings = FAOTLauncherSettings.shared;
    FAOTControlLayout *layout = [FAOTLauncherViewController activeLayout];
    self.layoutLabel.text = [NSString stringWithFormat:@"%@ · %lu 个按键", settings.layoutName, (unsigned long)layout.controls.count];
    NSInteger memory = settings.memoryGiB;
    NSArray<NSNumber *> *options = settings.memoryOptions;
    NSUInteger memoryIndex = 0;
    for (NSUInteger index = 0; index < options.count; index++) {
        if (options[index].integerValue <= memory) memoryIndex = index;
    }
    self.memoryPicker.selectedSegmentIndex = (NSInteger)memoryIndex;
    self.memoryCaption.text = settings.deviceMemoryCaption;
    NSInteger retention = settings.logRetention;
    NSUInteger best = 0;
    for (NSUInteger index = 0; index < self.retentionOptions.count; index++) {
        if (self.retentionOptions[index].integerValue <= retention) best = index;
    }
    self.retentionPicker.selectedSegmentIndex = (NSInteger)best;
    NSUInteger logs = FAOTLogStore.files.count;
    self.retentionCaption.text = [NSString stringWithFormat:@"当前 %lu 份日志，新日志产生后自动保留最近 %ld 份",
                                  (unsigned long)logs, (long)retention];
    NSString *language = settings.languageCode;
    self.languagePicker.selectedSegmentIndex = [language isEqual:@"zh_cn"] ? 0 : [language isEqual:@"ja_jp"] ? 2 : 1;
    self.motionSwitch.on = settings.reduceLauncherMotion;

    NSDictionary *info = NSBundle.mainBundle.infoDictionary;
    self.versionLabel.text = info[@"CFBundleShortVersionString"] ?: @"—";
    self.buildLabel.text = info[@"CFBundleVersion"] ?: @"—";
    NSString *test = info[@"FAOTTestVersion"];
    self.testVersionLabel.text = [test isKindOfClass:NSString.class] && test.length ? test : @"未标记";
    self.bundleLabel.text = NSBundle.mainBundle.bundleIdentifier ?: @"—";
}

- (void)memoryChanged {
    NSArray<NSNumber *> *options = FAOTLauncherSettings.shared.memoryOptions;
    NSInteger index = self.memoryPicker.selectedSegmentIndex;
    if (index < 0 || index >= (NSInteger)options.count) return;
    FAOTLauncherSettings.shared.memoryGiB = options[(NSUInteger)index].integerValue;
    self.statusLabel.text = [NSString stringWithFormat:@"已完成设置：Java 内存 %ld GB（下次启动生效）",
                             (long)FAOTLauncherSettings.shared.memoryGiB];
}

- (void)retentionChanged {
    NSInteger index = self.retentionPicker.selectedSegmentIndex;
    if (index < 0 || index >= (NSInteger)self.retentionOptions.count) return;
    FAOTLauncherSettings.shared.logRetention = self.retentionOptions[(NSUInteger)index].integerValue;
    [self refreshPage];
    self.statusLabel.text = @"日志保留份数已更新";
}

- (void)cleanLogsTapped {
    [FAOTLogStore pruneToRetention:FAOTLauncherSettings.shared.logRetention];
    [self refreshPage];
    self.statusLabel.text = @"已清理旧日志";
}

- (void)languageChanged {
    NSInteger index = self.languagePicker.selectedSegmentIndex;
    NSArray *codes = @[@"zh_cn", @"en_us", @"ja_jp"];
    if (index < 0 || index >= (NSInteger)codes.count) return;
    FAOTLauncherSettings.shared.languageCode = codes[(NSUInteger)index];
    self.statusLabel.text = @"游戏语言已更新（下次启动生效）";
}

- (void)reduceMotionChanged {
    FAOTLauncherSettings.shared.reduceLauncherMotion = self.motionSwitch.isOn;
    self.statusLabel.text = self.motionSwitch.isOn ? @"已减弱启动器动态效果" : @"已恢复启动器动态效果";
}

- (void)editLayoutTapped { [self.host pageRequestedLayoutEditor]; }
- (void)importLayoutTapped { [self.host pageRequestedLayoutImport]; }

@end

#pragma mark - Account

@interface FAOTAccountPageController () <UITextFieldDelegate>
@property (nonatomic, weak) id<FAOTLauncherPageHost> host;
@property (nonatomic, strong) UISegmentedControl *segmented;
@property (nonatomic, strong) UIStackView *paneContainer;
@property (nonatomic, strong) UIStackView *microsoftPane;
@property (nonatomic, strong) UIStackView *yggdrasilPane;
@property (nonatomic, strong) UIStackView *offlinePane;

@property (nonatomic, strong) FAOTSkinView *activeSkin;
@property (nonatomic, strong) UISegmentedControl *skinModelPicker;
@property (nonatomic, strong) UILabel *skinModelCaption;
@property (nonatomic, strong) UILabel *activeName;
@property (nonatomic, strong) UILabel *activeKind;
@property (nonatomic, strong) UILabel *activeDetail;
@property (nonatomic, strong) UIButton *refreshButton;
@property (nonatomic, strong) UIButton *logoutButton;
@property (nonatomic, strong) UIStackView *activeActions;

@property (nonatomic, strong) UIButton *microsoftLoginButton;
@property (nonatomic, strong) UILabel *microsoftStatus;
@property (nonatomic, strong) UIView *challengeCard;
@property (nonatomic, strong) UILabel *codeLabel;
@property (nonatomic, strong) UILabel *challengeURL;
@property (nonatomic, strong) UIButton *pollButton;
@property (nonatomic, strong) NSDictionary<NSString *, id> *challenge;
@property (nonatomic, strong, nullable) NSTimer *pollTimer;
@property (nonatomic, assign) NSTimeInterval pollInterval;
@property (nonatomic, assign) BOOL polling;

@property (nonatomic, strong) UITextField *serverField;
@property (nonatomic, strong) UITextField *usernameField;
@property (nonatomic, strong) UITextField *passwordField;
@property (nonatomic, strong) UIButton *yggdrasilLoginButton;
@property (nonatomic, strong) UILabel *yggdrasilStatus;
@property (nonatomic, assign) BOOL yggdrasilBusy;

@property (nonatomic, strong) UITextField *offlineField;
@property (nonatomic, strong) UILabel *offlineStatus;
@property (nonatomic, strong) UIScrollView *scrollView;
@property (nonatomic, weak) UITextField *activeField;
@property (nonatomic, assign) BOOL refreshing;
@property (nonatomic, assign) NSTimeInterval lastRefreshAttempt;
@end

@implementation FAOTAccountPageController

- (instancetype)initWithHost:(id<FAOTLauncherPageHost>)host {
    self = [super initWithNibName:nil bundle:nil];
    if (self) _host = host;
    return self;
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.clearColor;
    UIStackView *stack = FAOTMakeStack(@[], 16);
    self.scrollView = FAOTInstallScroll(self, stack);
    self.scrollView.keyboardDismissMode = UIScrollViewKeyboardDismissModeInteractive;
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(keyboardWillChangeFrame:)
                                               name:UIKeyboardWillChangeFrameNotification object:nil];

    [stack addArrangedSubview:FAOTPageHeader(@"账号", @"")];
    [stack addArrangedSubview:[self buildActiveCard]];
    self.segmented = [[UISegmentedControl alloc] initWithItems:@[@"微软正版", @"外置登录", @"离线"]];
    self.segmented.selectedSegmentIndex = 0;
    self.segmented.selectedSegmentTintColor = FAOTAccentColor();
    [self.segmented setTitleTextAttributes:@{NSForegroundColorAttributeName: FAOTDynamicColor(UIColor.whiteColor, UIColor.blackColor)}
                                  forState:UIControlStateSelected];
    [self.segmented setTitleTextAttributes:@{NSForegroundColorAttributeName: FAOTSecondaryTextColor()}
                                  forState:UIControlStateNormal];
    self.segmented.backgroundColor = FAOTFieldColor();
    [self.segmented addTarget:self action:@selector(segmentChanged) forControlEvents:UIControlEventValueChanged];
    [stack addArrangedSubview:self.segmented];

    self.microsoftPane = [self buildMicrosoftPane];
    self.yggdrasilPane = [self buildYggdrasilPane];
    self.offlinePane = [self buildOfflinePane];
    self.paneContainer = FAOTMakeStack(@[], 0);
    for (UIStackView *pane in @[self.microsoftPane, self.yggdrasilPane, self.offlinePane]) {
        [self.paneContainer addArrangedSubview:pane];
    }
    self.yggdrasilPane.hidden = YES;
    self.offlinePane.hidden = YES;
    [stack addArrangedSubview:self.paneContainer];
    [self segmentChanged];
}

- (UIView *)buildActiveCard {
    self.activeSkin = [[FAOTSkinView alloc] initWithFrame:CGRectZero];
    self.activeSkin.headOnly = YES;
    self.activeSkin.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [self.activeSkin.widthAnchor constraintEqualToConstant:66],
        [self.activeSkin.heightAnchor constraintEqualToConstant:66],
    ]];
    self.activeName = FAOTMakeLabel(@"Dev", 20, UIFontWeightBold, FAOTPrimaryTextColor());
    self.activeKind = FAOTMakeLabel(@"离线账号", 12, UIFontWeightSemibold, FAOTAccentColor());
    self.activeDetail = FAOTMakeLabel(@"本地档案", 11, UIFontWeightRegular, FAOTMutedTextColor());
    UIStackView *identity = FAOTMakeStack(@[self.activeName, self.activeKind, self.activeDetail], 3);
    identity.alignment = UIStackViewAlignmentLeading;

    self.skinModelCaption = FAOTMakeLabel(@"皮肤模型", 11, UIFontWeightMedium, FAOTMutedTextColor());
    self.skinModelPicker = [[UISegmentedControl alloc] initWithItems:@[@"经典", @"纤细"]];
    self.skinModelPicker.selectedSegmentTintColor = FAOTAccentColor();
    self.skinModelPicker.backgroundColor = FAOTFieldColor();
    [self.skinModelPicker setTitleTextAttributes:@{NSForegroundColorAttributeName: FAOTDynamicColor(UIColor.whiteColor, UIColor.blackColor)}
                                        forState:UIControlStateSelected];
    [self.skinModelPicker setTitleTextAttributes:@{NSForegroundColorAttributeName: FAOTSecondaryTextColor()}
                                        forState:UIControlStateNormal];
    [self.skinModelPicker addTarget:self action:@selector(skinModelChanged) forControlEvents:UIControlEventValueChanged];
    [self.skinModelPicker.heightAnchor constraintEqualToConstant:30].active = YES;
    UIStackView *modelColumn = FAOTMakeStack(@[self.skinModelCaption, self.skinModelPicker], 4);
    [modelColumn.widthAnchor constraintEqualToConstant:150].active = YES;

    self.refreshButton = FAOTMakeButton(@"刷新", FAOTFieldColor(), FAOTPrimaryTextColor());
    self.refreshButton.titleLabel.font = [UIFont systemFontOfSize:13 weight:UIFontWeightSemibold];
    [self.refreshButton addTarget:self action:@selector(refreshActiveAccount) forControlEvents:UIControlEventTouchUpInside];
    [self.refreshButton.heightAnchor constraintEqualToConstant:34].active = YES;
    self.logoutButton = FAOTMakeButton(@"退出", FAOTRGBA(1, 0.35, 0.35, 0.14), FAOTRGBA(1, 0.62, 0.62, 1));
    self.logoutButton.titleLabel.font = [UIFont systemFontOfSize:13 weight:UIFontWeightSemibold];
    [self.logoutButton addTarget:self action:@selector(logoutTapped) forControlEvents:UIControlEventTouchUpInside];
    [self.logoutButton.heightAnchor constraintEqualToConstant:34].active = YES;
    UIStackView *actions = FAOTMakeStack(@[self.refreshButton, self.logoutButton], 8);
    [actions.widthAnchor constraintEqualToConstant:76].active = YES;
    self.activeActions = actions;

    UIView *spacer = [UIView new];
    [spacer setContentHuggingPriority:1 forAxis:UILayoutConstraintAxisHorizontal];
    UIStackView *row = [[UIStackView alloc] initWithArrangedSubviews:@[self.activeSkin, identity, modelColumn, spacer, actions]];
    row.axis = UILayoutConstraintAxisHorizontal;
    row.alignment = UIStackViewAlignmentCenter;
    row.spacing = 14;
    return FAOTPaddedCard(row, 14);
}

- (UIStackView *)buildMicrosoftPane {
    UILabel *intro = FAOTMakeLabel(@"使用 Microsoft 账号登录。设备码只在本机显示，授权在浏览器完成；登录后会验证 Minecraft Java 版资格并读取正版皮肤。",
                                   12, UIFontWeightRegular, FAOTSecondaryTextColor());
    self.microsoftLoginButton = FAOTMakeButton(@"使用 Microsoft 登录", FAOTAccentColor(), FAOTDynamicColor(UIColor.whiteColor, UIColor.blackColor));
    [self.microsoftLoginButton.heightAnchor constraintEqualToConstant:44].active = YES;
    [self.microsoftLoginButton addTarget:self action:@selector(microsoftLoginTapped) forControlEvents:UIControlEventTouchUpInside];

    self.challengeCard = FAOTMakeCard();
    UILabel *caption = FAOTMakeLabel(@"在浏览器打开并输入此代码", 12, UIFontWeightMedium, FAOTSecondaryTextColor());
    self.codeLabel = FAOTMakeLabel(@"--------", 30, UIFontWeightBold, FAOTAccentColor());
    self.codeLabel.font = [UIFont monospacedSystemFontOfSize:30 weight:UIFontWeightBold];
    self.challengeURL = FAOTMakeLabel(@"https://www.microsoft.com/link", 11, UIFontWeightRegular, FAOTMutedTextColor());
    UIButton *open = FAOTMakeButton(@"打开登录页", FAOTFieldColor(), FAOTPrimaryTextColor());
    [open addTarget:self action:@selector(openLoginPage) forControlEvents:UIControlEventTouchUpInside];
    UIButton *copy = FAOTMakeButton(@"复制代码", FAOTFieldColor(), FAOTPrimaryTextColor());
    [copy addTarget:self action:@selector(copyCode) forControlEvents:UIControlEventTouchUpInside];
    self.pollButton = FAOTMakeButton(@"我已完成登录", FAOTAccentColor(), FAOTDynamicColor(UIColor.whiteColor, UIColor.blackColor));
    [self.pollButton addTarget:self action:@selector(pollMicrosoftNow) forControlEvents:UIControlEventTouchUpInside];
    UIButton *cancel = FAOTMakeButton(@"取消", UIColor.clearColor, FAOTSecondaryTextColor());
    [cancel addTarget:self action:@selector(cancelMicrosoftLogin) forControlEvents:UIControlEventTouchUpInside];
    UIStackView *pair = [[UIStackView alloc] initWithArrangedSubviews:@[open, copy]];
    pair.axis = UILayoutConstraintAxisHorizontal;
    pair.distribution = UIStackViewDistributionFillEqually;
    pair.spacing = 8;
    UIStackView *pair2 = [[UIStackView alloc] initWithArrangedSubviews:@[self.pollButton, cancel]];
    pair2.axis = UILayoutConstraintAxisHorizontal;
    pair2.distribution = UIStackViewDistributionFillEqually;
    pair2.spacing = 8;
    for (UIButton *button in @[open, copy, self.pollButton, cancel]) {
        [button.heightAnchor constraintEqualToConstant:36].active = YES;
    }
    UIStackView *challengeContent = FAOTMakeStack(@[caption, self.codeLabel, self.challengeURL, pair, pair2], 8);
    [self.challengeCard addSubview:challengeContent];
    challengeContent.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [challengeContent.topAnchor constraintEqualToAnchor:self.challengeCard.topAnchor constant:14],
        [challengeContent.leadingAnchor constraintEqualToAnchor:self.challengeCard.leadingAnchor constant:14],
        [challengeContent.trailingAnchor constraintEqualToAnchor:self.challengeCard.trailingAnchor constant:-14],
        [challengeContent.bottomAnchor constraintEqualToAnchor:self.challengeCard.bottomAnchor constant:-14],
    ]];
    self.challengeCard.hidden = YES;
    self.microsoftStatus = FAOTMakeLabel(@"", 12, UIFontWeightRegular, FAOTSecondaryTextColor());
    return FAOTMakeStack(@[intro, self.challengeCard, self.microsoftLoginButton, self.microsoftStatus], 12);
}

- (UIStackView *)buildYggdrasilPane {
    UILabel *intro = FAOTMakeLabel(@"连接 authlib-injector 兼容的 Yggdrasil API（如 LittleSkin）。启动器会真实完成密码认证，读取角色档案与皮肤；游戏内联机认证仍取决于服务器与运行时支持。",
                                   12, UIFontWeightRegular, FAOTSecondaryTextColor());
    self.serverField = FAOTMakeField(@"https://littleskin.cn/api/yggdrasil", NO);
    self.serverField.keyboardType = UIKeyboardTypeURL;
    self.serverField.textContentType = UITextContentTypeURL;
    self.usernameField = FAOTMakeField(@"用户名 / 邮箱", NO);
    self.passwordField = FAOTMakeField(@"密码", YES);
    for (UITextField *field in @[self.serverField, self.usernameField, self.passwordField]) {
        field.delegate = self;
        [field.heightAnchor constraintEqualToConstant:42].active = YES;
    }
    self.yggdrasilLoginButton = FAOTMakeButton(@"登录外置账号", FAOTAccentColor(), FAOTDynamicColor(UIColor.whiteColor, UIColor.blackColor));
    [self.yggdrasilLoginButton.heightAnchor constraintEqualToConstant:44].active = YES;
    [self.yggdrasilLoginButton addTarget:self action:@selector(yggdrasilLoginTapped) forControlEvents:UIControlEventTouchUpInside];
    self.yggdrasilStatus = FAOTMakeLabel(@"", 12, UIFontWeightRegular, FAOTSecondaryTextColor());
    UILabel *privacy = FAOTMakeLabel(@"密码只用于本次认证请求，不会写入设置或日志；访问令牌保存在系统钥匙串。",
                                      11, UIFontWeightRegular, FAOTMutedTextColor());
    return FAOTMakeStack(@[intro, self.serverField, self.usernameField, self.passwordField,
                           self.yggdrasilLoginButton, self.yggdrasilStatus, privacy], 9);
}

- (UIStackView *)buildOfflinePane {
    UILabel *intro = FAOTMakeLabel(@"不连接账号服务，只使用本地玩家名进入单人世界。离线档案没有远程皮肤。",
                                   12, UIFontWeightRegular, FAOTSecondaryTextColor());
    self.offlineField = FAOTMakeField(@"玩家名", NO);
    self.offlineField.delegate = self;
    self.offlineField.autocapitalizationType = UITextAutocapitalizationTypeNone;
    [self.offlineField.heightAnchor constraintEqualToConstant:42].active = YES;
    UIButton *apply = FAOTMakeButton(@"使用离线账号", FAOTFieldColor(), FAOTPrimaryTextColor());
    [apply.heightAnchor constraintEqualToConstant:44].active = YES;
    [apply addTarget:self action:@selector(offlineLoginTapped) forControlEvents:UIControlEventTouchUpInside];
    self.offlineStatus = FAOTMakeLabel(@"", 12, UIFontWeightRegular, FAOTSecondaryTextColor());
    UILabel *rules = FAOTMakeLabel(@"1–16 位字母、数字或下划线。离线账号仅用于本地测试。", 11, UIFontWeightRegular, FAOTMutedTextColor());
    return FAOTMakeStack(@[intro, self.offlineField, apply, self.offlineStatus, rules], 10);
}

- (void)segmentChanged {
    NSInteger index = MAX(0, self.segmented.selectedSegmentIndex);
    self.microsoftPane.hidden = index != 0;
    self.yggdrasilPane.hidden = index != 1;
    self.offlinePane.hidden = index != 2;
}

- (void)skinModelChanged {
    FAOTAccount *account = FAOTAccountStore.shared.activeAccount;
    FAOTSkinModel model = self.skinModelPicker.selectedSegmentIndex == 1 ? FAOTSkinModelSlim : FAOTSkinModelClassic;
    [FAOTAccountStore.shared setSkinModel:model forAccount:account];
    [self applySkinModelToPreviews];
    [self.host pageAccountsChanged];
}

- (void)applySkinModelToPreviews {
    BOOL slim = [FAOTAccountStore.shared skinModelForAccount:FAOTAccountStore.shared.activeAccount] == FAOTSkinModelSlim;
    self.activeSkin.slim = slim;
    self.skinModelPicker.selectedSegmentIndex = slim ? 1 : 0;
}

- (void)refreshPage {
    FAOTAccount *account = FAOTAccountStore.shared.activeAccount;
    self.activeName.text = account.name.length ? account.name : FAOTLauncherSettings.shared.offlineName;
    self.activeKind.text = account.kindTitle;
    self.activeSkin.skin = [FAOTAccountStore.shared cachedSkinForAccount:account];
    [self applySkinModelToPreviews];
    if (account.kind == FAOTAccountKindOffline) {
        self.activeDetail.text = @"本地档案 · 无远程皮肤";
    } else if (account.kind == FAOTAccountKindMicrosoft) {
        self.activeDetail.text = [NSString stringWithFormat:@"UUID %@", account.uuid.length > 8 ? [account.uuid substringToIndex:8] : account.uuid];
    } else {
        self.activeDetail.text = account.server.length ? account.server : @"外置登录";
    }
    BOOL offline = account.kind == FAOTAccountKindOffline;
    self.refreshButton.hidden = offline;
    self.logoutButton.hidden = offline;
    self.activeActions.hidden = offline;
    self.offlineField.text = FAOTLauncherSettings.shared.offlineName;
    if (account.kind == FAOTAccountKindYggdrasil && account.server.length) self.serverField.text = account.server;
    if (!self.serverField.text.length) {
        NSString *saved = [NSUserDefaults.standardUserDefaults stringForKey:FAOTYggdrasilServerKey];
        self.serverField.text = saved.length ? saved : @"https://littleskin.cn/api/yggdrasil";
    }
    [self.microsoftLoginButton setTitle:(account.kind == FAOTAccountKindMicrosoft ? @"重新登录 Microsoft" : @"使用 Microsoft 登录")
                               forState:UIControlStateNormal];

    NSTimeInterval now = NSDate.date.timeIntervalSince1970;
    BOOL expired = account.kind != FAOTAccountKindOffline && account.expiresAt < now;
    if (expired && !self.refreshing && now - self.lastRefreshAttempt > 300) {
        self.lastRefreshAttempt = now;
        [self refreshAccountSilently];
    }
}

- (void)refreshAccountSilently {
    FAOTAccount *account = FAOTAccountStore.shared.activeAccount;
    if (account.kind == FAOTAccountKindOffline || self.refreshing) return;
    self.refreshing = YES;
    NSString *identifier = account.identifier;
    UILabel *status = account.kind == FAOTAccountKindMicrosoft ? self.microsoftStatus : self.yggdrasilStatus;
    status.text = @"正在刷新登录状态…";
    [FAOTAuthService.shared refreshAccount:account completion:^(FAOTAccount *updated, NSError *error) {
        self.refreshing = NO;
        if (![FAOTAccountStore.shared.activeAccount.identifier isEqual:identifier]) return;
        if (updated) {
            [FAOTAccountStore.shared activateAccount:updated];
            [self.host pageAccountsChanged];
            [self refreshPage];
        } else if (error) {
            status.text = error.localizedDescription;
        }
    }];
}

- (void)refreshActiveAccount {
    self.lastRefreshAttempt = NSDate.date.timeIntervalSince1970;
    [self refreshAccountSilently];
}

- (void)logoutTapped {
    [self stopPolling];
    self.challenge = nil;
    self.challengeCard.hidden = YES;
    self.microsoftLoginButton.hidden = NO;
    [FAOTAccountStore.shared clearActiveAccount];
    self.microsoftStatus.text = @"已退出登录";
    self.yggdrasilStatus.text = @"";
    [self refreshPage];
    [self.host pageAccountsChanged];
}

#pragma mark Microsoft UI

- (void)microsoftLoginTapped {
    self.microsoftStatus.text = @"正在获取设备码…";
    self.microsoftLoginButton.enabled = NO;
    self.challengeCard.hidden = YES;
    [FAOTAuthService.shared beginMicrosoftLogin:^(NSDictionary<NSString *, id> *challenge, NSError *error) {
        self.microsoftLoginButton.enabled = YES;
        if (!challenge) {
            self.microsoftLoginButton.hidden = NO;
            self.microsoftStatus.text = error.localizedDescription;
            return;
        }
        self.challenge = challenge;
        self.codeLabel.text = challenge[@"userCode"];
        self.challengeURL.text = challenge[@"verificationURL"];
        self.challengeCard.hidden = NO;
        self.microsoftLoginButton.hidden = YES;
        self.microsoftStatus.text = @"等待在浏览器完成授权…";
        [self schedulePollWithInterval:[challenge[@"interval"] doubleValue]];
    }];
}

- (void)schedulePollWithInterval:(NSTimeInterval)interval {
    [self stopPolling];
    self.pollInterval = MAX(5, interval);
    __weak typeof(self) weakSelf = self;
    self.pollTimer = [NSTimer scheduledTimerWithTimeInterval:self.pollInterval repeats:YES block:^(NSTimer *timer) {
        [weakSelf pollMicrosoftIfNeeded];
    }];
}

- (void)stopPolling {
    [self.pollTimer invalidate];
    self.pollTimer = nil;
}

- (void)pollMicrosoftNow { [self pollMicrosoftIfNeeded]; }

- (void)pollMicrosoftIfNeeded {
    if (!self.challenge || self.polling) return;
    NSDictionary<NSString *, id> *requested = self.challenge;
    self.polling = YES;
    __weak typeof(self) weakSelf = self;
    [FAOTAuthService.shared pollMicrosoftLogin:self.challenge completion:^(FAOTAccount *account, BOOL pending, NSTimeInterval interval, NSError *error) {
        typeof(self) strongSelf = weakSelf;
        if (!strongSelf) return;
        strongSelf.polling = NO;
        if (strongSelf.challenge != requested) return;
        if (error) {
            [strongSelf stopPolling];
            strongSelf.microsoftLoginButton.hidden = NO;
            strongSelf.microsoftStatus.text = error.localizedDescription;
            return;
        }
        if (pending) {
            strongSelf.microsoftStatus.text = @"等待在浏览器完成授权…";
            if (fabs(interval - strongSelf.pollInterval) > 0.1) [strongSelf schedulePollWithInterval:interval];
            return;
        }
        if (account) {
            [strongSelf stopPolling];
            strongSelf.challenge = nil;
            strongSelf.challengeCard.hidden = YES;
            strongSelf.microsoftLoginButton.hidden = NO;
            [FAOTAccountStore.shared activateAccount:account];
            strongSelf.microsoftStatus.text = [NSString stringWithFormat:@"已登录：%@", account.name];
            [strongSelf.host pageAccountsChanged];
            [strongSelf refreshPage];
        }
    }];
}

- (void)openLoginPage {
    NSString *value = self.challenge[@"verificationURL"] ?: @"https://www.microsoft.com/link";
    NSURL *url = [NSURL URLWithString:value];
    if (url) [UIApplication.sharedApplication openURL:url options:@{} completionHandler:nil];
}

- (void)copyCode {
    if (self.codeLabel.text.length) {
        UIPasteboard.generalPasteboard.string = self.codeLabel.text;
        self.microsoftStatus.text = @"验证码已复制";
    }
}

- (void)cancelMicrosoftLogin {
    [self stopPolling];
    self.challenge = nil;
    self.challengeCard.hidden = YES;
    self.microsoftLoginButton.hidden = NO;
    self.microsoftStatus.text = @"已取消登录";
}

#pragma mark Yggdrasil

- (void)yggdrasilLoginTapped {
    if (self.yggdrasilBusy) return;
    self.yggdrasilBusy = YES;
    self.yggdrasilLoginButton.enabled = NO;
    self.yggdrasilStatus.text = @"正在连接外置登录服务器…";
    NSString *server = self.serverField.text;
    NSString *username = self.usernameField.text;
    NSString *password = self.passwordField.text;
    __weak typeof(self) weakSelf = self;
    [FAOTAuthService.shared authenticateYggdrasil:server username:username password:password
                                       completion:^(NSDictionary<NSString *, id> *session,
                                                    NSArray<NSDictionary<NSString *, id> *> *profiles,
                                                    NSError *error) {
        typeof(self) strongSelf = weakSelf;
        if (!strongSelf) return;
        strongSelf.yggdrasilBusy = NO;
        strongSelf.yggdrasilLoginButton.enabled = YES;
        if (error) {
            strongSelf.yggdrasilStatus.text = error.localizedDescription;
            return;
        }
        NSDictionary *selected = session[@"selectedProfile"];
        if (![selected isKindOfClass:NSDictionary.class] && profiles.count == 1) selected = profiles.firstObject;
        if ([selected isKindOfClass:NSDictionary.class] && [selected[@"id"] isKindOfClass:NSString.class]) {
            [strongSelf completeYggdrasil:session profile:selected server:server];
            return;
        }
        if (profiles.count > 1) {
            [strongSelf chooseYggdrasilProfile:profiles session:session server:server];
            return;
        }
        strongSelf.yggdrasilStatus.text = @"登录成功，但该账号没有游戏档案。";
    }];
}

- (void)chooseYggdrasilProfile:(NSArray<NSDictionary *> *)profiles
                       session:(NSDictionary *)session
                        server:(NSString *)server {
    UIAlertController *sheet = [UIAlertController alertControllerWithTitle:@"选择角色"
                                                                  message:@"该外置账号包含多个角色"
                                                           preferredStyle:UIAlertControllerStyleActionSheet];
    __weak typeof(self) weakSelf = self;
    for (NSDictionary *profile in profiles) {
        NSString *title = [NSString stringWithFormat:@"%@", profile[@"name"]];
        [sheet addAction:[UIAlertAction actionWithTitle:title style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            [weakSelf completeYggdrasil:session profile:profile server:server];
        }]];
    }
    [sheet addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
    sheet.popoverPresentationController.sourceView = self.view;
    sheet.popoverPresentationController.sourceRect = CGRectMake(CGRectGetMidX(self.view.bounds), CGRectGetMidY(self.view.bounds), 1, 1);
    [self presentViewController:sheet animated:YES completion:nil];
}

- (void)completeYggdrasil:(NSDictionary *)session profile:(NSDictionary *)profile server:(NSString *)server {
    self.yggdrasilStatus.text = @"正在读取角色档案与皮肤…";
    self.yggdrasilLoginButton.enabled = NO;
    __weak typeof(self) weakSelf = self;
    [FAOTAuthService.shared completeYggdrasilSession:session profile:profile server:server
                                         completion:^(FAOTAccount *account, NSError *error) {
        typeof(self) strongSelf = weakSelf;
        if (!strongSelf) return;
        strongSelf.yggdrasilLoginButton.enabled = YES;
        if (!account) {
            strongSelf.yggdrasilStatus.text = error.localizedDescription;
            return;
        }
        if (account.server.length) {
            [NSUserDefaults.standardUserDefaults setObject:account.server forKey:FAOTYggdrasilServerKey];
            strongSelf.serverField.text = account.server;
        }
        strongSelf.passwordField.text = @"";
        [FAOTAccountStore.shared activateAccount:account];
        strongSelf.yggdrasilStatus.text = [NSString stringWithFormat:@"已登录：%@", account.name];
        [strongSelf.host pageAccountsChanged];
        [strongSelf refreshPage];
    }];
}

- (void)offlineLoginTapped {
    NSString *name = [self.offlineField.text stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!FAOTValidOfflineName(name)) {
        self.offlineStatus.text = @"玩家名需为 1–16 位字母、数字或下划线。";
        return;
    }
    FAOTLauncherSettings.shared.offlineName = name;
    FAOTAccount *account = [FAOTAccount offlineAccountWithName:name];
    [FAOTAccountStore.shared activateAccount:account];
    self.offlineStatus.text = [NSString stringWithFormat:@"已切换到离线账号 %@", name];
    [self.host pageAccountsChanged];
    [self refreshPage];
}

- (BOOL)textFieldShouldReturn:(UITextField *)textField {
    [textField resignFirstResponder];
    return YES;
}

- (void)textFieldDidBeginEditing:(UITextField *)textField {
    self.activeField = textField;
}

- (void)keyboardWillChangeFrame:(NSNotification *)note {
    CGRect frame = [note.userInfo[UIKeyboardFrameEndUserInfoKey] CGRectValue];
    CGRect local = [self.view convertRect:frame fromView:nil];
    CGFloat overlap = MAX(0, CGRectGetMaxY(self.view.bounds) - CGRectGetMinY(local));
    UIEdgeInsets inset = self.scrollView.contentInset;
    inset.bottom = overlap;
    self.scrollView.contentInset = inset;
    self.scrollView.scrollIndicatorInsets = inset;
    if (self.activeField && overlap > 0) {
        CGRect target = [self.activeField convertRect:self.activeField.bounds toView:self.scrollView];
        [self.scrollView scrollRectToVisible:CGRectInset(target, 0, -28) animated:YES];
    }
}

- (void)dealloc {
    [NSNotificationCenter.defaultCenter removeObserver:self];
    [self stopPolling];
}

@end

@implementation FAOTGamePageController

- (instancetype)initWithHost:(id<FAOTLauncherPageHost>)host {
    self = [super initWithNibName:nil bundle:nil];
    if (self) _host = host;
    return self;
}

static NSString *FAOTSaveDateText(NSDate *date) {
    static NSDateFormatter *formatter;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ formatter = [NSDateFormatter new]; formatter.dateFormat = @"yyyy-MM-dd HH:mm"; });
    return date ? [formatter stringFromDate:date] : @"";
}

static NSArray<NSDictionary<NSString *, id> *> *FAOTLocalSaves(void) {
    NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    NSString *saves = [[documents ?: NSTemporaryDirectory() stringByAppendingPathComponent:@"game"] stringByAppendingPathComponent:@"saves"];
    NSMutableArray *entries = [NSMutableArray array];
    NSArray *names = [NSFileManager.defaultManager contentsOfDirectoryAtPath:saves error:nil] ?: @[];
    for (NSString *name in names) {
        if ([name hasPrefix:@"."]) continue;
        NSString *path = [saves stringByAppendingPathComponent:name];
        NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
        if (![attributes[NSFileType] isEqual:NSFileTypeDirectory]) continue;
        NSString *level = [path stringByAppendingPathComponent:@"level.dat"];
        NSDictionary *levelAttributes = [NSFileManager.defaultManager attributesOfItemAtPath:level error:nil];
        NSDate *date = levelAttributes[NSFileModificationDate] ?: attributes[NSFileModificationDate];
        [entries addObject:@{@"name": name, @"date": date ?: NSDate.date, @"detail": FAOTSaveDateText(date)}];
    }
    [entries sortUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
        return [b[@"date"] compare:a[@"date"]];
    }];
    return entries;
}

- (UIView *)cardWithScrollView:(UIScrollView **)outScroll content:(UIStackView **)outContent {
    UIView *card = FAOTMakeCard();
    card.clipsToBounds = YES;
    card.translatesAutoresizingMaskIntoConstraints = NO;

    UIScrollView *scroll = [UIScrollView new];
    scroll.alwaysBounceVertical = YES;
    scroll.showsVerticalScrollIndicator = NO;
    scroll.translatesAutoresizingMaskIntoConstraints = NO;
    [card addSubview:scroll];
    UIStackView *content = FAOTMakeStack(@[], 10);
    content.translatesAutoresizingMaskIntoConstraints = NO;
    [scroll addSubview:content];

    [NSLayoutConstraint activateConstraints:@[
        [scroll.topAnchor constraintEqualToAnchor:card.topAnchor],
        [scroll.leadingAnchor constraintEqualToAnchor:card.leadingAnchor],
        [scroll.trailingAnchor constraintEqualToAnchor:card.trailingAnchor],
        [scroll.bottomAnchor constraintEqualToAnchor:card.bottomAnchor],
        [content.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:14],
        [content.leadingAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.leadingAnchor constant:16],
        [content.trailingAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.trailingAnchor constant:-16],
        [content.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-14],
    ]];
    if (outScroll) *outScroll = scroll;
    if (outContent) *outContent = content;
    return card;
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.clearColor;

    UILabel *title = FAOTMakeLabel(@"游戏", 26, UIFontWeightBold, FAOTPrimaryTextColor());
    title.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:title];

    self.skinView = [[FAOTSkinView alloc] initWithFrame:CGRectZero];
    self.skinView.headOnly = YES;
    self.skinView.translatesAutoresizingMaskIntoConstraints = NO;
    self.skinView.backgroundColor = FAOTRGBA(1, 1, 1, 0.06);
    [NSLayoutConstraint activateConstraints:@[
        [self.skinView.widthAnchor constraintEqualToConstant:44],
        [self.skinView.heightAnchor constraintEqualToConstant:44],
    ]];
    self.nameLabel = FAOTMakeLabel(@"Dev", 18, UIFontWeightBold, FAOTPrimaryTextColor());
    self.accountLabel = FAOTMakeLabel(@"离线账号", 10, UIFontWeightSemibold, FAOTAccentColor());
    // The identity block sits at the trailing edge of the header row, so the
    // text hugs the avatar on its right instead of running away from it.
    self.nameLabel.textAlignment = NSTextAlignmentRight;
    self.accountLabel.textAlignment = NSTextAlignmentRight;
    self.nameLabel.numberOfLines = 1;
    self.accountLabel.numberOfLines = 1;
    // Keep the two labels at their natural width so the avatar stays right
    // beside the name instead of the stack squeezing the subtitle into a column.
    [self.nameLabel setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    [self.accountLabel setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    UIStackView *identity = FAOTMakeStack(@[self.nameLabel, self.accountLabel], 3);
    identity.alignment = UIStackViewAlignmentTrailing;
    [identity setContentHuggingPriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    [identity setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    // Name first, avatar after it.
    UIStackView *hero = [[UIStackView alloc] initWithArrangedSubviews:@[identity, self.skinView]];
    hero.axis = UILayoutConstraintAxisHorizontal;
    hero.alignment = UIStackViewAlignmentCenter;
    hero.spacing = 10;
    hero.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:hero];

    self.memoryValue = FAOTMakeLabel(@"—", 17, UIFontWeightSemibold, FAOTPrimaryTextColor());
    self.modsValue = FAOTMakeLabel(@"—", 17, UIFontWeightSemibold, FAOTPrimaryTextColor());
    self.packsValue = FAOTMakeLabel(@"—", 17, UIFontWeightSemibold, FAOTPrimaryTextColor());
    self.shadersValue = FAOTMakeLabel(@"—", 17, UIFontWeightSemibold, FAOTPrimaryTextColor());
    UIStackView *row1 = [[UIStackView alloc] initWithArrangedSubviews:@[
        FAOTMetricTile(@"Java 内存", self.memoryValue), FAOTMetricTile(@"Mod", self.modsValue)]];
    UIStackView *row2 = [[UIStackView alloc] initWithArrangedSubviews:@[
        FAOTMetricTile(@"资源包", self.packsValue), FAOTMetricTile(@"光影包", self.shadersValue)]];
    for (UIStackView *row in @[row1, row2]) {
        row.axis = UILayoutConstraintAxisHorizontal;
        row.distribution = UIStackViewDistributionFillEqually;
        row.spacing = 10;
    }
    // The metrics card holds only two fixed rows, so it is a plain card that
    // sizes itself. Wrapping it in a scroll view gave it no intrinsic height and
    // the layout collapsed it.
    UIView *infoCard = FAOTMakeCard();
    infoCard.clipsToBounds = YES;
    infoCard.translatesAutoresizingMaskIntoConstraints = NO;
    [infoCard addSubview:row1];
    [infoCard addSubview:row2];
    row1.translatesAutoresizingMaskIntoConstraints = NO;
    row2.translatesAutoresizingMaskIntoConstraints = NO;
    // Equal heights make the two rows share whatever space the card receives.
    // With the 54pt tile floor inside, the card can grow but never squeezes a
    // row below its minimum.
    [row2.heightAnchor constraintEqualToAnchor:row1.heightAnchor].active = YES;
    [NSLayoutConstraint activateConstraints:@[
        [row1.topAnchor constraintEqualToAnchor:infoCard.topAnchor constant:14],
        [row1.leadingAnchor constraintEqualToAnchor:infoCard.leadingAnchor constant:16],
        [row1.trailingAnchor constraintEqualToAnchor:infoCard.trailingAnchor constant:-16],
        [row2.topAnchor constraintEqualToAnchor:row1.bottomAnchor constant:10],
        [row2.leadingAnchor constraintEqualToAnchor:infoCard.leadingAnchor constant:16],
        [row2.trailingAnchor constraintEqualToAnchor:infoCard.trailingAnchor constant:-16],
        [row2.bottomAnchor constraintEqualToAnchor:infoCard.bottomAnchor constant:-14],
    ]];

    UIScrollView *savesScroll = nil;
    UIStackView *savesContent = nil;
    UIView *savesCard = [self cardWithScrollView:&savesScroll content:&savesContent];
    self.savesScrollView = savesScroll;
    self.savesStack = savesContent;
    self.savesEmptyLabel = FAOTMakeLabel(@"暂无存档 · 首次进入游戏后可在此查看", 12, UIFontWeightRegular, FAOTMutedTextColor());
    self.savesEmptyLabel.textAlignment = NSTextAlignmentCenter;

    // Both cards take exactly half of the column's height. Letting the info card
    // hug its content made it grow on tall layouts while the saves card stayed
    // small, which is the imbalance this layout is meant to avoid.
    UIView *leftColumn = [UIView new];
    leftColumn.translatesAutoresizingMaskIntoConstraints = NO;
    [leftColumn addSubview:infoCard];
    [leftColumn addSubview:savesCard];
    [NSLayoutConstraint activateConstraints:@[
        [infoCard.topAnchor constraintEqualToAnchor:leftColumn.topAnchor],
        [infoCard.leadingAnchor constraintEqualToAnchor:leftColumn.leadingAnchor],
        [infoCard.trailingAnchor constraintEqualToAnchor:leftColumn.trailingAnchor],
        [savesCard.topAnchor constraintEqualToAnchor:infoCard.bottomAnchor constant:12],
        [savesCard.leadingAnchor constraintEqualToAnchor:leftColumn.leadingAnchor],
        [savesCard.trailingAnchor constraintEqualToAnchor:leftColumn.trailingAnchor],
        [savesCard.bottomAnchor constraintEqualToAnchor:leftColumn.bottomAnchor],
        [infoCard.heightAnchor constraintEqualToAnchor:savesCard.heightAnchor],
    ]];
    [self.view addSubview:leftColumn];
    // Equal heights, so each card is half of the column once the 12pt gap is
    // taken out. The floor keeps the metric rows readable on short layouts.
    [savesCard.heightAnchor constraintGreaterThanOrEqualToConstant:64].active = YES;

    UIView *previewCard = FAOTMakeCard();
    previewCard.clipsToBounds = YES;
    previewCard.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:previewCard];
    self.previewSkinView = [[FAOTSkinView alloc] initWithFrame:CGRectZero];
    self.previewSkinView.translatesAutoresizingMaskIntoConstraints = NO;
    self.previewSkinView.backgroundColor = UIColor.clearColor;
    self.previewSkinView.userInteractionEnabled = YES;
    self.previewSkinView.yaw = 0.38;
    self.previewSkinView.pitch = 0.1;
    self.previewSkinView.layer.cornerRadius = 0;
    self.previewSkinView.clipsToBounds = NO;
    [previewCard addSubview:self.previewSkinView];
    [NSLayoutConstraint activateConstraints:@[
        [self.previewSkinView.topAnchor constraintEqualToAnchor:previewCard.topAnchor constant:12],
        [self.previewSkinView.leadingAnchor constraintEqualToAnchor:previewCard.leadingAnchor constant:12],
        [self.previewSkinView.trailingAnchor constraintEqualToAnchor:previewCard.trailingAnchor constant:-12],
        [self.previewSkinView.bottomAnchor constraintEqualToAnchor:previewCard.bottomAnchor constant:-12],
    ]];
    UIPanGestureRecognizer *pan = [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(previewPanned:)];
    [self.previewSkinView addGestureRecognizer:pan];

    self.statusLabel = FAOTMakeLabel(@"准备就绪", 11, UIFontWeightRegular, FAOTMutedTextColor());
    self.statusLabel.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightRegular];
    self.statusLabel.numberOfLines = 1;
    [self.statusLabel setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisVertical];
    self.launchButton = FAOTMakeButton(@"进入世界  →", FAOTAccentColor(), FAOTDynamicColor(UIColor.whiteColor, UIColor.blackColor));
    self.launchButton.titleLabel.font = [UIFont systemFontOfSize:19 weight:UIFontWeightBold];
    self.launchButton.layer.cornerRadius = 14;
    [self.launchButton addTarget:self action:@selector(launchTapped) forControlEvents:UIControlEventTouchUpInside];
    [self.launchButton.heightAnchor constraintEqualToConstant:52].active = YES;
    // Status and button are laid out independently. A stack that contains a
    // 52pt button plus a single-line label kept squeezing the label to zero
    // height once the cards above claimed the remaining space.
    self.statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.launchButton.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.statusLabel];
    [self.view addSubview:self.launchButton];

    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [title.topAnchor constraintEqualToAnchor:safe.topAnchor constant:20],
        [title.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:24],
        [hero.topAnchor constraintEqualToAnchor:title.topAnchor],
        [hero.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-24],
        [hero.leadingAnchor constraintGreaterThanOrEqualToAnchor:title.trailingAnchor constant:16],
        [leftColumn.topAnchor constraintEqualToAnchor:hero.bottomAnchor constant:18],
        [leftColumn.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:24],
        [leftColumn.bottomAnchor constraintEqualToAnchor:self.statusLabel.topAnchor constant:-8],
        [previewCard.topAnchor constraintEqualToAnchor:leftColumn.topAnchor],
        [previewCard.leadingAnchor constraintEqualToAnchor:leftColumn.trailingAnchor constant:14],
        [previewCard.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-24],
        [previewCard.bottomAnchor constraintEqualToAnchor:leftColumn.bottomAnchor],
        [leftColumn.widthAnchor constraintEqualToAnchor:previewCard.widthAnchor multiplier:0.96],
        [self.statusLabel.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:24],
        [self.statusLabel.trailingAnchor constraintLessThanOrEqualToAnchor:safe.trailingAnchor constant:-24],
        [self.statusLabel.heightAnchor constraintEqualToConstant:14],
        [self.statusLabel.bottomAnchor constraintEqualToAnchor:self.launchButton.topAnchor constant:-8],
        [self.launchButton.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:24],
        [self.launchButton.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-24],
        // The footer owns the bottom edge; pinning to the safe area left a visible
        // home-indicator strip below the launch button in landscape.
        [self.launchButton.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor constant:-10],
    ]];
    [self refreshPage];
}

- (void)previewPanned:(UIPanGestureRecognizer *)pan {
    CGPoint translation = [pan translationInView:pan.view];
    if (pan.state == UIGestureRecognizerStateBegan) {
        self.panStartYaw = self.previewSkinView.yaw;
        self.panStartPitch = self.previewSkinView.pitch;
    } else if (pan.state == UIGestureRecognizerStateChanged) {
        self.previewSkinView.yaw = self.panStartYaw + translation.x * 0.012;
        // Dragging up should look down on the figure (towards its head) and
        // dragging down should look up at it, which is the reverse of how the
        // screen-space translation reads.
        CGFloat pitch = self.panStartPitch + translation.y * 0.005;
        self.previewSkinView.pitch = MAX(-0.45, MIN(0.45, pitch));
    }
}

- (void)refreshSaves {
    for (UIView *view in self.savesStack.arrangedSubviews) {
        [self.savesStack removeArrangedSubview:view];
        [view removeFromSuperview];
    }
    NSArray<NSDictionary<NSString *, id> *> *saves = FAOTLocalSaves();
    if (saves.count == 0) {
        [self.savesStack addArrangedSubview:self.savesEmptyLabel];
        return;
    }
    for (NSDictionary *entry in saves) {
        UIView *row = [UIView new];
        row.backgroundColor = FAOTDynamicColor(FAOTRGBA(0.93, 0.94, 0.95, 1), FAOTRGBA(1, 1, 1, 0.05));
        row.layer.cornerRadius = 10;
        UILabel *name = FAOTMakeLabel(entry[@"name"], 13, UIFontWeightSemibold, FAOTPrimaryTextColor());
        UILabel *detail = FAOTMakeLabel(entry[@"detail"], 11, UIFontWeightRegular, FAOTMutedTextColor());
        UIStackView *text = FAOTMakeStack(@[name, detail], 2);
        text.translatesAutoresizingMaskIntoConstraints = NO;
        [row addSubview:text];
        [NSLayoutConstraint activateConstraints:@[
            [text.topAnchor constraintEqualToAnchor:row.topAnchor constant:9],
            [text.leadingAnchor constraintEqualToAnchor:row.leadingAnchor constant:12],
            [text.trailingAnchor constraintEqualToAnchor:row.trailingAnchor constant:-12],
            [text.bottomAnchor constraintEqualToAnchor:row.bottomAnchor constant:-9],
        ]];
        [self.savesStack addArrangedSubview:row];
    }
}

- (void)refreshPage {
    FAOTAccountStore *store = FAOTAccountStore.shared;
    FAOTAccount *account = store.activeAccount;
    FAOTLauncherSettings *settings = FAOTLauncherSettings.shared;
    UIImage *skin = [store cachedSkinForAccount:account];
    self.nameLabel.text = account.name.length ? account.name : settings.offlineName;
    self.accountLabel.text = account.kindTitle;
    self.skinView.skin = skin;
    self.previewSkinView.skin = skin;
    BOOL slim = [store skinModelForAccount:account] == FAOTSkinModelSlim;
    self.previewSkinView.slim = slim;
    self.memoryValue.text = [NSString stringWithFormat:@"%ld GB", (long)settings.memoryGiB];
    self.modsValue.text = [NSString stringWithFormat:@"%lu", (unsigned long)FAOTContentCatalog.mods.count];
    self.packsValue.text = [NSString stringWithFormat:@"%lu", (unsigned long)FAOTContentCatalog.resourcePacks.count];
    self.shadersValue.text = [NSString stringWithFormat:@"%lu", (unsigned long)FAOTContentCatalog.shaderPacks.count];
    [self refreshSaves];
    BOOL launched = [self.host pageGameHasLaunched];
    [self.launchButton setTitle:(launched ? @"重新启动应用" : @"进入世界  →") forState:UIControlStateNormal];
    self.launchButton.backgroundColor = launched ? UIColor.systemOrangeColor : FAOTAccentColor();
    [self.launchButton setTitleColor:FAOTDynamicColor(UIColor.whiteColor, UIColor.blackColor) forState:UIControlStateNormal];
}

- (void)showStatus:(NSString *)status {
    self.statusLabel.text = status.length ? status : @"准备就绪";
}

- (void)launchTapped {
    [self.host pageRequestedLaunch];
}

@end
