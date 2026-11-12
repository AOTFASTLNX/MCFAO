//
//  FAOTLauncherViewController.m
//
#import "FAOTLauncherViewController.h"
#import "FAOTControlsOverlay.h"
#include <unistd.h>
#import <QuartzCore/QuartzCore.h>

NSString *const FAOTPlayerNameDefaultsKey = @"FAOTPlayerName";
NSString *const FAOTMemoryGiBDefaultsKey = @"FAOTMemoryGiB";
NSString *const FAOTControlLayoutDefaultsKey = @"FAOTControlLayout";

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

#pragma mark - Launcher

@interface FAOTLauncherViewController () <UITextFieldDelegate>
@property (nonatomic, strong) UITextField *nameField;
@property (nonatomic, strong) UISegmentedControl *memoryPicker;
@property (nonatomic, strong) UILabel *layoutLabel;
@property (nonatomic, strong) UILabel *statusLabel;
@property (nonatomic, strong) UIButton *launchButton;
@property (nonatomic, assign) BOOL launchedInThisProcess;
@property (nonatomic, copy) NSArray<NSNumber *> *memoryOptions;
@property (nonatomic, strong) UIView *card;
@property (nonatomic, strong) UIStackView *contentStack;
@property (nonatomic, strong) CAGradientLayer *backdrop;
@property (nonatomic, copy) NSString *layoutName;
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


+ (NSArray<NSNumber *> *)memoryOptionsForDevice {
    double physicalGiB = (double)NSProcessInfo.processInfo.physicalMemory / 1073741824.0;
    NSInteger maxGiB = (NSInteger)floor(physicalGiB * 0.55);
    if (maxGiB < 1) maxGiB = 1;
    if (maxGiB > 8) maxGiB = 8;
    NSMutableArray<NSNumber *> *options = [NSMutableArray array];
    for (NSInteger value = 1; value <= maxGiB; value++) {
        [options addObject:@(value)];
    }
    return options;
}

+ (NSString *)deviceMemoryCaption {
    double physicalGiB = (double)NSProcessInfo.processInfo.physicalMemory / 1073741824.0;
    return [NSString stringWithFormat:@"Java 内存 · 设备 %.0f GB", physicalGiB];
}

- (void)viewWillAppear:(BOOL)animated {
    [super viewWillAppear:animated];
    [self refreshLaunchButton];
}

- (void)refreshLaunchButton {
    if (self.launchedInThisProcess) {
        [self.launchButton setTitle:@"重新启动应用" forState:UIControlStateNormal];
        self.launchButton.backgroundColor = [UIColor systemOrangeColor];
    } else {
        [self.launchButton setTitle:@"进入世界  →" forState:UIControlStateNormal];
    }
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = [UIColor colorWithRed:0.055 green:0.063 blue:0.078 alpha:1.0];
    self.backdrop = [CAGradientLayer layer];
    self.backdrop.colors = @[(id)[UIColor colorWithRed:0.025 green:0.07 blue:0.12 alpha:1].CGColor,
                            (id)[UIColor colorWithRed:0.04 green:0.22 blue:0.24 alpha:1].CGColor,
                            (id)[UIColor colorWithRed:0.04 green:0.08 blue:0.16 alpha:1].CGColor];
    self.backdrop.startPoint = CGPointMake(0,0);
    self.backdrop.endPoint = CGPointMake(1,1);
    [self.view.layer insertSublayer:self.backdrop atIndex:0];
    [self buildInterface];
    [self reloadSettings];
}

- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    BOOL landscape = self.view.bounds.size.width > self.view.bounds.size.height;
    UILayoutConstraintAxis axis = landscape ? UILayoutConstraintAxisHorizontal : UILayoutConstraintAxisVertical;
    if (self.contentStack.axis != axis) {
        self.contentStack.axis = axis;
        self.contentStack.alignment = landscape ? UIStackViewAlignmentTop : UIStackViewAlignmentFill;
        self.contentStack.distribution = landscape ? UIStackViewDistributionFillEqually : UIStackViewDistributionFill;
    }
    [CATransaction begin];
    [CATransaction setDisableActions:YES];
    self.backdrop.frame = self.view.bounds;
    [CATransaction commit];
}

- (void)buildInterface {
    UILabel *title = [UILabel new];
    title.text = @"FabricAOT";
    title.numberOfLines = 0;
    title.font = [UIFont systemFontOfSize:30 weight:UIFontWeightBold];
    title.textColor = [UIColor colorWithRed:0.6 green:0.95 blue:0.82 alpha:1];

    UILabel *subtitle = [UILabel new];
    subtitle.text = @"你的方块世界，随身出发。\nMinecraft Java 26.1.2 · Fabric";
    subtitle.font = [UIFont systemFontOfSize:13 weight:UIFontWeightRegular];
    subtitle.textColor = [UIColor colorWithWhite:1.0 alpha:0.6];
    subtitle.numberOfLines = 0;

    self.nameField = [UITextField new];
    self.nameField.borderStyle = UITextBorderStyleNone;
    self.nameField.backgroundColor = [UIColor colorWithWhite:1.0 alpha:0.08];
    self.nameField.textColor = UIColor.whiteColor;
    self.nameField.tintColor = UIColor.systemGreenColor;
    self.nameField.font = [UIFont systemFontOfSize:16 weight:UIFontWeightMedium];
    self.nameField.layer.cornerRadius = 10;
    self.nameField.delegate = self;
    self.nameField.returnKeyType = UIReturnKeyDone;
    self.nameField.leftView = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 12, 1)];
    self.nameField.leftViewMode = UITextFieldViewModeAlways;
    self.nameField.placeholder = @"玩家名称";

    UILabel *memoryCaption = [UILabel new];
    memoryCaption.text = [FAOTLauncherViewController deviceMemoryCaption];
    memoryCaption.font = [UIFont systemFontOfSize:13 weight:UIFontWeightMedium];
    memoryCaption.textColor = [UIColor colorWithWhite:1.0 alpha:0.55];

    /* Only offer what this device can actually back: iOS counts the app, Metal and the native
       image against the same physical RAM, so leave a little more than half for the Java heap. */
    self.memoryOptions = [FAOTLauncherViewController memoryOptionsForDevice];
    NSMutableArray<NSString *> *titles = [NSMutableArray arrayWithCapacity:self.memoryOptions.count];
    for (NSNumber *value in self.memoryOptions) {
        [titles addObject:[NSString stringWithFormat:@"%@G", value]];
    }
    self.memoryPicker = [[UISegmentedControl alloc] initWithItems:titles];
    self.memoryPicker.selectedSegmentIndex = MIN(1, self.memoryPicker.numberOfSegments - 1);
    self.memoryPicker.backgroundColor = [UIColor colorWithWhite:1.0 alpha:0.08];
    self.memoryPicker.selectedSegmentTintColor = [UIColor colorWithRed:0.6 green:0.95 blue:0.82 alpha:1];
    [self.memoryPicker setTitleTextAttributes:@{NSForegroundColorAttributeName:UIColor.whiteColor} forState:UIControlStateNormal];
    [self.memoryPicker setTitleTextAttributes:@{NSForegroundColorAttributeName:UIColor.blackColor} forState:UIControlStateSelected];

    self.layoutLabel = [UILabel new];
    self.layoutLabel.font = [UIFont systemFontOfSize:15 weight:UIFontWeightMedium];
    self.layoutLabel.textColor = UIColor.whiteColor;
    self.layoutLabel.numberOfLines = 0;

    UIButton *editLayout = [self pillButton:@"编辑按键" action:@selector(editLayoutTapped)];
    UIButton *importLayout = [self pillButton:@"导入布局" action:@selector(importLayoutTapped)];

    UIButton *launch = [UIButton buttonWithType:UIButtonTypeSystem];
    [launch setTitle:@"进入世界  →" forState:UIControlStateNormal];
    self.launchButton = launch;
    [launch setTitleColor:UIColor.blackColor forState:UIControlStateNormal];
    launch.titleLabel.font = [UIFont systemFontOfSize:19 weight:UIFontWeightBold];
    launch.backgroundColor = UIColor.systemGreenColor;
    launch.layer.cornerRadius = 14;
    [launch addTarget:self action:@selector(launchTapped) forControlEvents:UIControlEventTouchUpInside];

    self.statusLabel = [UILabel new];
    self.statusLabel.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightRegular];
    self.statusLabel.textColor = [UIColor colorWithWhite:1.0 alpha:0.5];
    self.statusLabel.numberOfLines = 0;
    self.statusLabel.text = @"准备就绪";

    UIButton *diagnostics = [self pillButton:@"运行诊断" action:@selector(diagnosticsTapped)];

    self.card = [UIView new];
    self.card.backgroundColor = [UIColor colorWithRed:0.04 green:0.09 blue:0.14 alpha:0.94];
    self.card.layer.borderWidth = 1;
    self.card.layer.borderColor = [UIColor colorWithWhite:1 alpha:0.12].CGColor;
    self.card.layer.shadowColor = UIColor.blackColor.CGColor;
    self.card.layer.shadowOpacity = 0.25;
    self.card.layer.shadowRadius = 20;
    self.card.layer.shadowOffset = CGSizeMake(0,8);
    self.card.layer.cornerRadius = 24;

    UIStackView *actions = [[UIStackView alloc] initWithArrangedSubviews:@[editLayout,importLayout]];
    actions.axis = UILayoutConstraintAxisHorizontal;
    actions.distribution = UIStackViewDistributionFillEqually;
    actions.spacing = 8;
    UIStackView *hero = [[UIStackView alloc] initWithArrangedSubviews:@[title,subtitle,launch]];
    hero.axis = UILayoutConstraintAxisVertical;
    hero.spacing = 16;
    UIStackView *settings = [[UIStackView alloc] initWithArrangedSubviews:@[self.nameField,memoryCaption,self.memoryPicker,self.layoutLabel,actions,self.statusLabel,diagnostics]];
    settings.axis = UILayoutConstraintAxisVertical;
    settings.spacing = 8;
    self.contentStack = [[UIStackView alloc] initWithArrangedSubviews:@[hero,settings]];
    self.contentStack.axis = self.view.bounds.size.width > self.view.bounds.size.height ? UILayoutConstraintAxisHorizontal : UILayoutConstraintAxisVertical;
    self.contentStack.distribution = self.contentStack.axis == UILayoutConstraintAxisHorizontal ? UIStackViewDistributionFillEqually : UIStackViewDistributionFill;
    self.contentStack.alignment = self.contentStack.axis == UILayoutConstraintAxisHorizontal ? UIStackViewAlignmentTop : UIStackViewAlignmentFill;
    self.contentStack.spacing = 24;
    self.contentStack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.card addSubview:self.contentStack];
    self.card.translatesAutoresizingMaskIntoConstraints = NO;
    UIScrollView *scroll = [UIScrollView new];
    scroll.translatesAutoresizingMaskIntoConstraints = NO;
    scroll.alwaysBounceVertical = YES;
    [self.view addSubview:scroll];
    [scroll addSubview:self.card];
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [scroll.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [scroll.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [scroll.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [scroll.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor],
        [self.card.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:16],
        [self.card.leadingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.leadingAnchor constant:16],
        [self.card.trailingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.trailingAnchor constant:-16],
        [self.card.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-16],
        [self.card.widthAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.widthAnchor constant:-32],
        [self.contentStack.topAnchor constraintEqualToAnchor:self.card.topAnchor constant:20],
        [self.contentStack.leadingAnchor constraintEqualToAnchor:self.card.leadingAnchor constant:20],
        [self.contentStack.trailingAnchor constraintEqualToAnchor:self.card.trailingAnchor constant:-20],
        [self.contentStack.bottomAnchor constraintEqualToAnchor:self.card.bottomAnchor constant:-20],
        [self.nameField.heightAnchor constraintEqualToConstant:44],
        [actions.heightAnchor constraintEqualToConstant:36],
        [launch.heightAnchor constraintEqualToConstant:52],
        [diagnostics.heightAnchor constraintEqualToConstant:32],
    ]];
}

- (UIButton *)pillButton:(NSString *)title action:(SEL)action {
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    [button setTitle:title forState:UIControlStateNormal];
    [button setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    button.titleLabel.font = [UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    button.backgroundColor = [UIColor colorWithWhite:1.0 alpha:0.12];
    button.layer.cornerRadius = 10;
    [button addTarget:self action:action forControlEvents:UIControlEventTouchUpInside];
    return button;
}

- (void)reloadSettings {
    NSUserDefaults *defaults = FAOTLauncherViewController.defaults;
    NSString *name = [defaults stringForKey:FAOTPlayerNameDefaultsKey];
    self.nameField.text = name.length ? name : @"Dev";
    NSInteger memory = [defaults integerForKey:FAOTMemoryGiBDefaultsKey];
    if (memory <= 0) memory = 2;
    NSUInteger restoreIndex = 0;
    for (NSUInteger i = 0; i < self.memoryOptions.count; i++) {
        if (self.memoryOptions[i].integerValue <= memory) restoreIndex = i;
    }
    self.memoryPicker.selectedSegmentIndex = (NSInteger)restoreIndex;
    self.layoutName = [defaults stringForKey:FAOTControlLayoutDefaultsKey];
    if (self.layoutName.length == 0) self.layoutName = @"default";
    FAOTControlLayout *layout = [FAOTLauncherViewController activeLayout];
    self.layoutLabel.text = [NSString stringWithFormat:@"按钮布局：%@ · %lu 个按键",
                             self.layoutName, (unsigned long)layout.controls.count];
}

- (NSInteger)selectedMemoryGiB {
    if (self.memoryOptions.count == 0) self.memoryOptions = [FAOTLauncherViewController memoryOptionsForDevice];
    NSInteger index = self.memoryPicker.selectedSegmentIndex;
    if (index < 0 || index >= (NSInteger)self.memoryOptions.count) index = 0;
    return self.memoryOptions[(NSUInteger)index].integerValue;
}

- (void)persistSettings {
    NSUserDefaults *defaults = FAOTLauncherViewController.defaults;
    [defaults setObject:(self.nameField.text.length ? self.nameField.text : @"Dev") forKey:FAOTPlayerNameDefaultsKey];
    NSInteger memory = [self selectedMemoryGiB];
    [defaults setInteger:memory forKey:FAOTMemoryGiBDefaultsKey];
    [defaults setObject:self.layoutName forKey:FAOTControlLayoutDefaultsKey];
}

#pragma mark Actions

- (void)editLayoutTapped {
    FAOTControlLayout *layout = [FAOTLauncherViewController activeLayout];
    __weak typeof(self) weakSelf = self;
    FAOTControlEditorViewController *editor =
        [[FAOTControlEditorViewController alloc] initWithLayout:layout
                                                     layoutName:self.layoutName
                                                     completion:^(FAOTControlLayout *updated, BOOL saved) {
            if (saved) {
                [updated saveNamed:weakSelf.layoutName error:nil];
                weakSelf.statusLabel.text = [NSString stringWithFormat:@"Saved %@ (%lu buttons)",
                                             weakSelf.layoutName, (unsigned long)updated.controls.count];
            }
            [weakSelf reloadSettings];
        }];
    editor.modalPresentationStyle = UIModalPresentationFullScreen;
    [self presentViewController:editor animated:YES completion:nil];
}

- (void)importLayoutTapped {
    UIAlertController *sheet = [UIAlertController alertControllerWithTitle:@"Import control layout"
                                                                  message:@"Parsed from Pojav's mControlDataList schema"
                                                           preferredStyle:UIAlertControllerStyleActionSheet];
    [sheet addAction:[UIAlertAction actionWithTitle:@"Pojav default layout" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        [self importJSONString:FAOTPojavDefaultLayoutJSON() sourceName:@"pojav-default"];
    }]];
    [sheet addAction:[UIAlertAction actionWithTitle:@"Paste JSON" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        [self promptPasteJSON];
    }]];
    [sheet addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    sheet.popoverPresentationController.sourceView = self.view;
    sheet.popoverPresentationController.sourceRect = CGRectMake(self.view.bounds.size.width / 2, self.view.bounds.size.height / 2, 1, 1);
    [self presentViewController:sheet animated:YES completion:nil];
}

- (void)promptPasteJSON {
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"Paste Pojav layout JSON"
                                                                  message:@"mControlDataList / control / bare array"
                                                           preferredStyle:UIAlertControllerStyleAlert];
    [alert addTextFieldWithConfigurationHandler:^(UITextField *field) {
        field.placeholder = @"{\"mControlDataList\":[...]}";
    }];
    [alert addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Import" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        [self importJSONString:alert.textFields.firstObject.text sourceName:@"pasted"];
    }]];
    [self presentViewController:alert animated:YES completion:nil];
}

- (void)importJSONString:(NSString *)json sourceName:(NSString *)source {
    NSError *error = nil;
    FAOTControlLayout *layout = [FAOTControlLayout layoutFromPojavData:[json dataUsingEncoding:NSUTF8StringEncoding]
                                                                 error:&error];
    if (!layout) {
        self.statusLabel.text = [NSString stringWithFormat:@"Import failed: %@", error.localizedDescription ?: @"bad format"];
        return;
    }
    NSString *name = [NSString stringWithFormat:@"imported-%@", source];
    [layout saveNamed:name error:nil];
    self.layoutName = name;
    [self persistSettings];
    [self reloadSettings];
    self.statusLabel.text = [NSString stringWithFormat:@"Imported %lu controls -> %@",
                             (unsigned long)layout.controls.count, name];
}

- (void)launchTapped {
    [self.view endEditing:YES];
    [self persistSettings];
    /* A Graal isolate lives for the whole process, so a second run_main in the same process can
       never succeed. Offer the only action that actually works: start over. */
    if (self.launchedInThisProcess) {
        self.statusLabel.text = @"Restarting so the game gets a fresh isolate...";
        exit(0);
    }
    if (self.onLaunch) {
        self.launchedInThisProcess = YES;
        self.onLaunch(self.nameField.text.length ? self.nameField.text : @"Dev",
                      [self selectedMemoryGiB], self.layoutName);
    } else {
        self.statusLabel.text = @"No runtime host attached: main.m must set onLaunch.";
    }
}

- (void)diagnosticsTapped {
    [self dismissViewControllerAnimated:YES completion:nil];
}

- (BOOL)textFieldShouldReturn:(UITextField *)textField {
    [textField resignFirstResponder];
    return YES;
}

@end
