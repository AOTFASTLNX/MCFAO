//
//  FAOTControlsOverlay.m
//
#import "FAOTControlsOverlay.h"

@interface FAOTControlButtonView : UIButton
@property (nonatomic, strong) FAOTControlModel *model;
@property (nonatomic, weak) FAOTControlsOverlay *overlay;
@property (nonatomic, assign, getter=isHeld) BOOL held;
@property (nonatomic, assign) CGPoint dragStartCenter;
@property (nonatomic, assign) CGAffineTransform dragStartTransform;
- (void)applyModel;
@end

@interface FAOTControlsOverlay () <UIGestureRecognizerDelegate>
@property (nonatomic, strong) NSMutableArray<FAOTControlButtonView *> *buttons;
@property (nonatomic, strong) NSMutableSet<NSNumber *> *heldCodes;
@property (nonatomic, strong) UIPinchGestureRecognizer *pinch;
@end

@implementation FAOTControlsOverlay

- (instancetype)initWithLayout:(FAOTControlLayout *)layout {
    if ((self = [super initWithFrame:CGRectZero])) {
        self.backgroundColor = UIColor.clearColor;
        self.multipleTouchEnabled = YES;
        _buttons = [NSMutableArray array];
        _heldCodes = [NSMutableSet set];
        _layout = layout;
        [self setLayout:layout];
    }
    return self;
}

- (void)setLayout:(FAOTControlLayout *)layout {
    _layout = layout;
    [self reloadControls];
}

- (CGRect)safeRect {
    return UIEdgeInsetsInsetRect(self.bounds, self.safeAreaInsets);
}

- (void)reloadControls {
    for (FAOTControlButtonView *button in self.buttons) [button removeFromSuperview];
    [self.buttons removeAllObjects];
    for (FAOTControlModel *model in self.layout.controls) {
        FAOTControlButtonView *button = [FAOTControlButtonView buttonWithType:UIButtonTypeCustom];
        button.model = model;
        button.overlay = self;
        [button addTarget:self action:@selector(touchDown:) forControlEvents:UIControlEventTouchDown];
        [button addTarget:self action:@selector(touchUp:)
         forControlEvents:UIControlEventTouchUpInside | UIControlEventTouchUpOutside | UIControlEventTouchCancel];
        if (self.editing) {
            [button addGestureRecognizer:[[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(drag:)]];
            UIPinchGestureRecognizer *pinch = [[UIPinchGestureRecognizer alloc] initWithTarget:self action:@selector(pinch:)];
            pinch.delegate = self;
            [button addGestureRecognizer:pinch];
        }
        [self addSubview:button];
        [self.buttons addObject:button];
    }
    [self setNeedsLayout];
}

- (void)layoutSubviews {
    [super layoutSubviews];
    CGRect safe = [self safeRect];
    for (FAOTControlButtonView *button in self.buttons) {
        FAOTControlModel *model = button.model;
        BOOL visible = self.menuMode ? model.showInMenu : model.showInGame;
        button.hidden = !visible;
        if (!visible) continue;
        button.frame = [self.layout frameForControl:model inRect:safe];
        [button applyModel];
    }
}

#pragma mark - Editing

- (void)setEditing:(BOOL)editing {
    if (_editing == editing) return;
    _editing = editing;
    self.selectedControl = nil;
    for (FAOTControlButtonView *button in self.buttons) {
        [button.gestureRecognizers.copy enumerateObjectsUsingBlock:^(UIGestureRecognizer *g, NSUInteger idx, BOOL *stop) {
            [button removeGestureRecognizer:g];
        }];
    }
    [self reloadControls];
}

- (void)drag:(UIPanGestureRecognizer *)recognizer {
    FAOTControlButtonView *button = (FAOTControlButtonView *)recognizer.view;
    CGRect safe = [self safeRect];
    if (recognizer.state == UIGestureRecognizerStateBegan) {
        button.dragStartCenter = button.center;
        self.selectedControl = button.model;
    }
    CGPoint translation = [recognizer translationInView:self];
    CGPoint center = CGPointMake(button.dragStartCenter.x + translation.x,
                                 button.dragStartCenter.y + translation.y);
    center.x = MIN(MAX(center.x, CGRectGetMinX(safe) + button.bounds.size.width / 2),
                   CGRectGetMaxX(safe) - button.bounds.size.width / 2);
    center.y = MIN(MAX(center.y, CGRectGetMinY(safe) + button.bounds.size.height / 2),
                   CGRectGetMaxY(safe) - button.bounds.size.height / 2);
    button.center = center;
    [self commitGeometryForButton:button inRect:safe];
}

- (void)commitGeometryForButton:(FAOTControlButtonView *)button inRect:(CGRect)safe {
    FAOTControlModel *model = button.model;
    model.x = (CGRectGetMinX(button.frame) - safe.origin.x) / MAX(1, safe.size.width);
    model.y = (CGRectGetMinY(button.frame) - safe.origin.y) / MAX(1, safe.size.height);
    model.width = button.bounds.size.width / MAX(1, safe.size.width);
    model.height = button.bounds.size.height / MAX(1, safe.size.height);
    [self setNeedsLayout];
}

- (void)pinch:(UIPinchGestureRecognizer *)recognizer {
    FAOTControlButtonView *button = (FAOTControlButtonView *)recognizer.view;
    CGRect safe = [self safeRect];
    switch (recognizer.state) {
        case UIGestureRecognizerStateBegan:
            button.dragStartTransform = button.transform;
            self.selectedControl = button.model;
            break;
        case UIGestureRecognizerStateChanged:
            button.transform = CGAffineTransformScale(button.dragStartTransform, recognizer.scale, recognizer.scale);
            break;
        case UIGestureRecognizerStateEnded:
        case UIGestureRecognizerStateCancelled: {
            CGFloat scale = recognizer.scale;
            button.transform = CGAffineTransformIdentity;
            CGFloat side = button.bounds.size.width * scale;
            side = MIN(MAX(side, 28.0), 120.0);
            button.bounds = CGRectMake(0, 0, side, side);
            [self commitGeometryForButton:button inRect:safe];
            break;
        }
        default:
            break;
    }
}

- (void)addControl:(FAOTControlModel *)control {
    [self.layout.controls addObject:control];
    [self reloadControls];
    self.selectedControl = control;
}

- (void)removeSelectedControl {
    if (!self.selectedControl) return;
    [self.layout.controls removeObject:self.selectedControl];
    self.selectedControl = nil;
    [self reloadControls];
}

#pragma mark - Input

- (void)touchDown:(FAOTControlButtonView *)button {
    if (self.editing) {
        self.selectedControl = button.model;
        [self.delegate controlsOverlay:self didSelectControl:button.model];
        return;
    }
    NSNumber *code = @(button.model.keycode);
    if ([self.heldCodes containsObject:code]) return;
    [self.heldCodes addObject:code];
    button.held = YES;
    [self.delegate controlsOverlay:self control:button.model pressed:YES];
}

- (void)touchUp:(FAOTControlButtonView *)button {
    if (self.editing) return;
    NSNumber *code = @(button.model.keycode);
    if (![self.heldCodes containsObject:code]) return;
    [self.heldCodes removeObject:code];
    button.held = NO;
    [self.delegate controlsOverlay:self control:button.model pressed:NO];
}

- (void)releaseAllControls {
    for (NSNumber *code in self.heldCodes) {
        for (FAOTControlButtonView *button in self.buttons) {
            if (button.model.keycode == code.integerValue) {
                button.held = NO;
                [self.delegate controlsOverlay:self control:button.model pressed:NO];
                break;
            }
        }
    }
    [self.heldCodes removeAllObjects];
}

@end

#pragma mark - Button view

@implementation FAOTControlButtonView
@synthesize held = _held;

- (void)applyModel {
    FAOTControlModel *model = self.model;
    [self setTitle:[model title] forState:UIControlStateNormal];
    [self setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    self.titleLabel.font = [UIFont systemFontOfSize:13 weight:UIFontWeightSemibold];
    self.backgroundColor = [model.background colorWithAlphaComponent:model.opacity];
    self.layer.cornerRadius = MIN(model.cornerRadius, self.bounds.size.width / 2);
    self.layer.borderWidth = 1.0;
    self.layer.borderColor = [UIColor colorWithWhite:1.0 alpha:0.65].CGColor;
    self.accessibilityLabel = [model title];
    self.accessibilityIdentifier = [NSString stringWithFormat:@"control_%@", [model title]];
}

- (void)setHeld:(BOOL)held {
    _held = held;
    self.alpha = held ? 0.45 : 1.0;
    self.layer.borderColor = (held ? UIColor.systemYellowColor : [UIColor colorWithWhite:1.0 alpha:0.65]).CGColor;
}

@end
