//
//  FAOTControlEditorViewController.m
//  Full-screen control layout editor. Reuses FAOTControlsOverlay's editable buttons.
//
#import "FAOTLauncherViewController.h"
#import "FAOTControlsOverlay.h"
#include <math.h>

@interface FAOTControlEditorViewController () <FAOTControlsOverlayDelegate>
@property (nonatomic, strong) FAOTControlLayout *layout;
@property (nonatomic, copy) NSString *layoutName;
@property (nonatomic, copy) void (^completion)(FAOTControlLayout *, BOOL);
@property (nonatomic, strong) FAOTControlsOverlay *overlay;
@property (nonatomic, strong) UILabel *hint;
@property (nonatomic, strong) UIView *toolbar;
@end

@implementation FAOTControlEditorViewController

- (BOOL)prefersStatusBarHidden { return YES; }
- (UIInterfaceOrientationMask)supportedInterfaceOrientations { return UIInterfaceOrientationMaskAllButUpsideDown; }

- (instancetype)initWithLayout:(FAOTControlLayout *)layout
                    layoutName:(NSString *)layoutName
                    completion:(void (^)(FAOTControlLayout *, BOOL))completion {
    if ((self = [super initWithNibName:nil bundle:nil])) {
        _layout = layout;
        _layoutName = [layoutName copy];
        _completion = [completion copy];
    }
    return self;
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.blackColor;

    self.overlay = [[FAOTControlsOverlay alloc] initWithLayout:self.layout];
    self.overlay.delegate = self;
    self.overlay.editing = YES;
    self.overlay.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.overlay];

    self.hint = [UILabel new];
    self.hint.text = @"拖动移位 · 双指缩放 · 点按改键";
    self.hint.font = [UIFont systemFontOfSize:12 weight:UIFontWeightMedium];
    self.hint.textColor = [UIColor colorWithWhite:1.0 alpha:0.55];
    self.hint.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.hint];

    self.toolbar = [UIView new];
    self.toolbar.backgroundColor = [UIColor colorWithWhite:0.1 alpha:0.92];
    self.toolbar.layer.cornerRadius = 12;
    self.toolbar.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.toolbar];

    NSArray *titles = @[@"完成", @"保存", @"＋按键", @"改键", @"大小", @"删除", @"Pojav 默认"];
    NSArray *selectors = @[@"finishTapped", @"saveTapped", @"addTapped", @"rebindTapped", @"sizeTapped", @"deleteTapped", @"resetTapped"];
    NSMutableArray *buttons = [NSMutableArray array];
    for (NSUInteger i = 0; i < titles.count; i++) {
        UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
        [button setTitle:titles[i] forState:UIControlStateNormal];
        [button setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
        button.titleLabel.font = [UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
        button.backgroundColor = [UIColor colorWithWhite:1.0 alpha:0.12];
        button.layer.cornerRadius = 8;
        [button addTarget:self action:NSSelectorFromString(selectors[i]) forControlEvents:UIControlEventTouchUpInside];
        [buttons addObject:button];
    }
    /* Six commands do not fit on a phone in landscape, let alone portrait, so the bar scrolls. */
    UIScrollView *strip = [UIScrollView new];
    strip.showsHorizontalScrollIndicator = NO;
    strip.translatesAutoresizingMaskIntoConstraints = NO;
    [self.toolbar addSubview:strip];
    UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:buttons];
    stack.axis = UILayoutConstraintAxisHorizontal;
    stack.spacing = 8;
    stack.alignment = UIStackViewAlignmentCenter;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [strip addSubview:stack];

    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [self.overlay.topAnchor constraintEqualToAnchor:self.view.topAnchor],
        [self.overlay.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [self.overlay.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [self.overlay.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],

        [self.hint.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:16],
        [self.hint.trailingAnchor constraintLessThanOrEqualToAnchor:safe.trailingAnchor constant:-16],
        [self.hint.topAnchor constraintEqualToAnchor:safe.topAnchor constant:8],

        [self.toolbar.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:16],
        [self.toolbar.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-16],
        [self.toolbar.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-8],
        [self.toolbar.heightAnchor constraintEqualToConstant:56],

        [strip.leadingAnchor constraintEqualToAnchor:self.toolbar.leadingAnchor constant:12],
        [strip.trailingAnchor constraintEqualToAnchor:self.toolbar.trailingAnchor constant:-12],
        [strip.topAnchor constraintEqualToAnchor:self.toolbar.topAnchor],
        [strip.bottomAnchor constraintEqualToAnchor:self.toolbar.bottomAnchor],

        [stack.leadingAnchor constraintEqualToAnchor:strip.contentLayoutGuide.leadingAnchor],
        [stack.trailingAnchor constraintEqualToAnchor:strip.contentLayoutGuide.trailingAnchor],
        [stack.topAnchor constraintEqualToAnchor:strip.contentLayoutGuide.topAnchor],
        [stack.bottomAnchor constraintEqualToAnchor:strip.contentLayoutGuide.bottomAnchor],
        [stack.heightAnchor constraintEqualToAnchor:strip.frameLayoutGuide.heightAnchor],
    ]];
    for (UIButton *button in buttons) {
        [button.heightAnchor constraintEqualToConstant:36].active = YES;
        [button.widthAnchor constraintGreaterThanOrEqualToConstant:64].active = YES;
    }
}

#pragma mark - Toolbar

- (void)finishTapped {
    if (self.completion) self.completion(self.layout, NO);
    [self dismissViewControllerAnimated:YES completion:nil];
}

- (void)saveTapped {
    NSError *error = nil;
    if (![self.layout saveNamed:self.layoutName error:&error]) {
        self.hint.text = [NSString stringWithFormat:@"保存失败：%@", error.localizedDescription];
        return;
    }
    self.hint.text = [NSString stringWithFormat:@"已保存到 controlmap/%@.json", self.layoutName];
    if (self.completion) self.completion(self.layout, YES);
}

- (void)addTapped {
    FAOTControlModel *model = [FAOTControlModel new];
    model.name = @"New";
    model.keycode = 'G';
    model.x = 0.45;
    model.y = 0.45;
    model.width = 44.0 / MAX(1, self.overlay.bounds.size.width);
    model.height = 44.0 / MAX(1, self.overlay.bounds.size.height);
    [self.overlay addControl:model];
    [self promptForControl:model];
}

- (void)rebindTapped {
    if (!self.overlay.selectedControl) {
        self.hint.text = @"先点一个按键再改键";
        return;
    }
    [self promptForControl:self.overlay.selectedControl];
}

- (void)sizeTapped {
    FAOTControlModel *control = self.overlay.selectedControl;
    if (!control) { self.hint.text = @"先点一个按键再调整大小"; return; }
    CGRect safe = UIEdgeInsetsInsetRect(self.overlay.bounds, self.overlay.safeAreaInsets);
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"按钮大小"
        message:@"分别设置宽、高（屏幕点），范围 28–240。保存布局后生效。"
        preferredStyle:UIAlertControllerStyleAlert];
    CGFloat values[] = {control.width * safe.size.width, control.height * safe.size.height};
    for (NSUInteger i=0; i<2; i++) {
        CGFloat value = values[i];
        [alert addTextFieldWithConfigurationHandler:^(UITextField *field) {
            field.keyboardType = UIKeyboardTypeDecimalPad;
            field.placeholder = i == 0 ? @"宽度" : @"高度";
            field.text = [NSString stringWithFormat:@"%.0f", value];
        }];
    }
    [alert addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"应用" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        double width=0, height=0;
        NSScanner *w=[NSScanner scannerWithString:alert.textFields[0].text ?: @""];
        NSScanner *h=[NSScanner scannerWithString:alert.textFields[1].text ?: @""];
        if (![w scanDouble:&width] || !w.isAtEnd || ![h scanDouble:&height] || !h.isAtEnd ||
            !isfinite(width) || !isfinite(height) || width<28 || width>240 || height<28 || height>240) {
            self.hint.text = @"大小无效，请输入 28–240 之间的数字"; return;
        }
        control.width=MIN(width,safe.size.width)/MAX(1,safe.size.width);
        control.height=MIN(height,safe.size.height)/MAX(1,safe.size.height);
        control.x=MIN(MAX(0,control.x),MAX(0,1-control.width));
        control.y=MIN(MAX(0,control.y),MAX(0,1-control.height));
        [self.overlay setNeedsLayout];
        self.hint.text = @"大小已更新，记得保存布局";
    }]];
    [self presentViewController:alert animated:YES completion:nil];
}

- (void)deleteTapped {
    if (!self.overlay.selectedControl) {
        self.hint.text = @"先点一个按键再删除";
        return;
    }
    [self.overlay removeSelectedControl];
    self.hint.text = @"已删除";
}

- (void)resetTapped {
    NSError *error = nil;
    FAOTControlLayout *layout = [FAOTControlLayout layoutFromPojavData:[FAOTPojavDefaultLayoutJSON() dataUsingEncoding:NSUTF8StringEncoding]
                                                                 error:&error];
    if (!layout) {
        self.hint.text = [NSString stringWithFormat:@"默认布局解析失败：%@", error.localizedDescription];
        return;
    }
    layout.name = self.layoutName;
    self.layout = layout;
    self.overlay.layout = layout;
    self.hint.text = @"已恢复 Pojav 默认布局，记得保存";
}

#pragma mark - Binding

- (void)promptForControl:(FAOTControlModel *)control {
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"按键绑定"
                                                                  message:@"输入键名（如 KEY_W）或 GLFW 数字码"
                                                           preferredStyle:UIAlertControllerStyleAlert];
    [alert addTextFieldWithConfigurationHandler:^(UITextField *field) {
        field.text = control.keycode > 0 ? FAOTPojavNameForKeycode(control.keycode)
                                         : [NSString stringWithFormat:@"%ld", (long)control.keycode];
        field.autocapitalizationType = UITextAutocapitalizationTypeAllCharacters;
        field.autocorrectionType = UITextAutocorrectionTypeNo;
    }];
    [alert addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"鼠标左键" style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) {
        control.keycode = FAOTSpecialPrimaryMouse;
        [self.overlay setLayout:self.overlay.layout];
    }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"鼠标右键" style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) {
        control.keycode = FAOTSpecialSecondaryMouse;
        [self.overlay setLayout:self.overlay.layout];
    }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"确定" style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) {
        NSString *text = [alert.textFields.firstObject.text stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
        NSInteger code = 0;
        if (text.length && [text rangeOfCharacterFromSet:NSCharacterSet.decimalDigitCharacterSet.invertedSet].location == NSNotFound) {
            code = text.integerValue;
        } else {
            code = FAOTKeycodeFromPojavName(text);
        }
        if (code == 0) {
            self.hint.text = [NSString stringWithFormat:@"无法识别：%@", text];
            return;
        }
        control.keycode = code;
        self.hint.text = [NSString stringWithFormat:@"%@ → %@", [control title], FAOTPojavNameForKeycode(code)];
        [self.overlay setLayout:self.overlay.layout];
    }]];
    [self presentViewController:alert animated:YES completion:nil];
}

#pragma mark - Overlay delegate

- (void)controlsOverlay:(FAOTControlsOverlay *)overlay control:(FAOTControlModel *)control pressed:(BOOL)pressed {
    (void)overlay; (void)control; (void)pressed; // editing never forwards input
}

- (void)controlsOverlay:(FAOTControlsOverlay *)overlay didSelectControl:(FAOTControlModel *)control {
    self.hint.text = [NSString stringWithFormat:@"已选中 %@（%@）", [control title], FAOTPojavNameForKeycode(control.keycode)];
}

@end
