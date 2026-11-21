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
@property (nonatomic, strong) UIView *indicator;
- (instancetype)initWithTitle:(NSString *)title symbol:(NSString *)symbol;
- (void)setActive:(BOOL)active;
@end

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
    self.indicator = [UIView new];
    self.indicator.backgroundColor = FAOTAccentColor();
    self.indicator.layer.cornerRadius = 1.5;
    self.indicator.translatesAutoresizingMaskIntoConstraints = NO;
    self.indicator.hidden = YES;

    UIStackView *row = [[UIStackView alloc] initWithArrangedSubviews:@[self.iconView, self.titleLabel]];
    row.axis = UILayoutConstraintAxisHorizontal;
    row.alignment = UIStackViewAlignmentCenter;
    row.spacing = 10;
    row.userInteractionEnabled = NO;
    row.translatesAutoresizingMaskIntoConstraints = NO;
    [self addSubview:row];
    [self addSubview:self.indicator];
    [NSLayoutConstraint activateConstraints:@[
        [row.leadingAnchor constraintEqualToAnchor:self.leadingAnchor constant:12],
        [row.trailingAnchor constraintLessThanOrEqualToAnchor:self.trailingAnchor constant:-8],
        [row.centerYAnchor constraintEqualToAnchor:self.centerYAnchor],
        [self.indicator.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [self.indicator.centerYAnchor constraintEqualToAnchor:self.centerYAnchor],
        [self.indicator.widthAnchor constraintEqualToConstant:3],
        [self.indicator.heightAnchor constraintEqualToConstant:18],
        [self.heightAnchor constraintEqualToConstant:42],
    ]];
    [self setActive:NO];
    return self;
}

- (void)setActive:(BOOL)active {
    self.backgroundColor = active ? FAOTRGBA(0.60, 0.95, 0.82, 0.14) : UIColor.clearColor;
    self.iconView.tintColor = active ? FAOTAccentColor() : FAOTRGBA(1, 1, 1, 0.52);
    self.titleLabel.textColor = active ? FAOTPrimaryTextColor() : FAOTSecondaryTextColor();
    self.indicator.hidden = !active;
}

@end

#pragma mark - Launcher

@interface FAOTLauncherViewController () <FAOTLauncherPageHost>
@property (nonatomic, strong) CAGradientLayer *backdrop;
@property (nonatomic, strong) UIView *sidebar;
@property (nonatomic, strong) UIView *content;
@property (nonatomic, strong) NSMutableArray<FAOTSidebarItem *> *sidebarItems;
@property (nonatomic, strong) NSDictionary<NSString *, UIViewController<FAOTLauncherPage> *> *pages;
@property (nonatomic, strong) UIViewController<FAOTLauncherPage> *visiblePage;
@property (nonatomic, copy) NSString *visibleKey;
@property (nonatomic, strong) FAOTGamePageController *gamePage;
@property (nonatomic, strong) UILabel *accountFooter;
@property (nonatomic, assign) BOOL launchedInThisProcess;
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
    self.backdrop.colors = @[(id)FAOTRGBA(0.025, 0.07, 0.12, 1).CGColor,
                             (id)FAOTRGBA(0.04, 0.22, 0.24, 1).CGColor,
                             (id)FAOTRGBA(0.04, 0.08, 0.16, 1).CGColor];
    self.backdrop.startPoint = CGPointMake(0, 0);
    self.backdrop.endPoint = CGPointMake(1, 1);
    [self.view.layer insertSublayer:self.backdrop atIndex:0];

    [self buildSidebar];
    self.content = [UIView new];
    self.content.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.content];
    [NSLayoutConstraint activateConstraints:@[
        [self.content.topAnchor constraintEqualToAnchor:self.view.topAnchor],
        [self.content.leadingAnchor constraintEqualToAnchor:self.sidebar.trailingAnchor],
        [self.content.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [self.content.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],
    ]];
    [self buildPages];
    [self showPage:@"game"];
}

- (void)buildSidebar {
    self.sidebar = [UIView new];
    self.sidebar.backgroundColor = FAOTRGBA(0.025, 0.04, 0.055, 0.88);
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

    UILabel *brand = FAOTMakeLabel(@"Native Craft", 17, UIFontWeightBold, FAOTPrimaryTextColor());
    UILabel *tagline = FAOTMakeLabel(@"26.1.2 · Fabric", 10, UIFontWeightMedium, FAOTAccentColor());
    UIStackView *heading = FAOTMakeStack(@[brand, tagline], 2);

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
    UILabel *version = FAOTMakeLabel([NSString stringWithFormat:@"NCL %@ · build %@",
                                      [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"] ?: @"0.1",
                                      [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"5"],
                                     9, UIFontWeightRegular, FAOTRGBA(1, 1, 1, 0.30));
    UIView *spacer = [UIView new];
    [spacer setContentHuggingPriority:1 forAxis:UILayoutConstraintAxisVertical];
    UIStackView *column = FAOTMakeStack(@[heading, nav, spacer, self.accountFooter, version], 20);
    column.translatesAutoresizingMaskIntoConstraints = NO;
    [self.sidebar addSubview:column];
    UILayoutGuide *safe = self.sidebar.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [column.topAnchor constraintEqualToAnchor:safe.topAnchor constant:22],
        [column.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:12],
        [column.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-12],
        [column.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-16],
    ]];
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
    if (self.visiblePage) self.visiblePage.view.hidden = YES;
    page.view.hidden = NO;
    self.visiblePage = page;
    self.visibleKey = key;
    NSArray *keys = @[@"game", @"account", @"resources", @"settings"];
    for (NSUInteger index = 0; index < self.sidebarItems.count; index++) {
        [self.sidebarItems[index] setActive:[keys[index] isEqual:key]];
    }
    [page refreshPage];
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
    if (self.launchedInThisProcess) {
        [self.gamePage showStatus:@"正在重新启动应用…"];
        exit(0);
    }
    FAOTAccount *account = FAOTAccountStore.shared.activeAccount;
    FAOTLauncherSettings *settings = FAOTLauncherSettings.shared;
    NSString *name = account.name.length ? account.name : settings.offlineName;
    if (account.kind == FAOTAccountKindOffline) settings.offlineName = name;
    if (!self.onLaunch) {
        [self.gamePage showStatus:@"没有连接运行宿主：main.m 必须设置 onLaunch。"];
        return;
    }
    self.launchedInThisProcess = YES;
    [self.gamePage showStatus:@"正在启动 Native Craft…"];
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
