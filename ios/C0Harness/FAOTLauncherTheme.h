//
//  FAOTLauncherTheme.h
//  Shared visual language for the launcher shell and its pages.
//
#import <UIKit/UIKit.h>

static inline UIColor *FAOTRGBA(CGFloat r, CGFloat g, CGFloat b, CGFloat a) {
    return [UIColor colorWithRed:r green:g blue:b alpha:a];
}

static inline UIColor *FAOTDynamicColor(UIColor *light, UIColor *dark) {
    return [UIColor colorWithDynamicProvider:^UIColor *(UITraitCollection *traits) {
        return traits.userInterfaceStyle == UIUserInterfaceStyleDark ? dark : light;
    }];
}
static inline UIColor *FAOTAccentColor(void) { return FAOTDynamicColor(FAOTRGBA(0.16, 0.18, 0.21, 1.0), FAOTRGBA(0.88, 0.90, 0.93, 1.0)); }
static inline UIColor *FAOTBackgroundColor(void) { return FAOTDynamicColor(FAOTRGBA(0.94, 0.95, 0.96, 1.0), FAOTRGBA(0.055, 0.06, 0.07, 1.0)); }
static inline UIColor *FAOTCardColor(void) { return FAOTDynamicColor(UIColor.whiteColor, FAOTRGBA(0.105, 0.115, 0.13, 1.0)); }
// Keep fields about 3% darker than the light launcher background so their bounds remain visible.
static inline UIColor *FAOTFieldColor(void) { return FAOTDynamicColor(FAOTRGBA(0.91, 0.92, 0.93, 1.0), FAOTRGBA(1.0, 1.0, 1.0, 0.09)); }
static inline UIColor *FAOTPrimaryTextColor(void) { return UIColor.labelColor; }
static inline UIColor *FAOTSecondaryTextColor(void) { return UIColor.secondaryLabelColor; }
static inline UIColor *FAOTMutedTextColor(void) { return UIColor.tertiaryLabelColor; }
static inline UIColor *FAOTHairlineColor(void) { return UIColor.separatorColor; }

static inline UILabel *FAOTMakeLabel(NSString *text, CGFloat size, UIFontWeight weight, UIColor *color) {
    UILabel *label = [UILabel new];
    label.text = text;
    label.font = [UIFont systemFontOfSize:size weight:weight];
    label.textColor = color;
    label.numberOfLines = 0;
    return label;
}

static inline UIView *FAOTMakeCard(void) {
    UIView *card = [UIView new];
    card.backgroundColor = FAOTCardColor();
    card.layer.cornerRadius = 18;
    card.layer.borderWidth = 1;
    card.layer.borderColor = FAOTHairlineColor().CGColor;
    return card;
}

static inline UIStackView *FAOTMakeStack(NSArray<UIView *> *views, CGFloat spacing) {
    UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:views];
    stack.axis = UILayoutConstraintAxisVertical;
    stack.spacing = spacing;
    stack.alignment = UIStackViewAlignmentFill;
    return stack;
}

static inline UIButton *FAOTMakeButton(NSString *title, UIColor *background, UIColor *titleColor) {
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    [button setTitle:title forState:UIControlStateNormal];
    [button setTitleColor:titleColor forState:UIControlStateNormal];
    button.titleLabel.font = [UIFont systemFontOfSize:15 weight:UIFontWeightSemibold];
    button.backgroundColor = background;
    button.layer.cornerRadius = 11;
    return button;
}

static inline UITextField *FAOTMakeField(NSString *placeholder, BOOL secure) {
    UITextField *field = [UITextField new];
    field.attributedPlaceholder = [[NSAttributedString alloc] initWithString:placeholder
        attributes:@{NSForegroundColorAttributeName: FAOTMutedTextColor()}];
    field.secureTextEntry = secure;
    field.borderStyle = UITextBorderStyleNone;
    field.backgroundColor = FAOTFieldColor();
    field.textColor = FAOTPrimaryTextColor();
    field.tintColor = FAOTAccentColor();
    field.font = [UIFont systemFontOfSize:15 weight:UIFontWeightRegular];
    field.layer.cornerRadius = 10;
    field.layer.borderWidth = 1;
    field.layer.borderColor = FAOTDynamicColor(FAOTRGBA(0.78, 0.80, 0.83, 0.42), FAOTRGBA(1.0, 1.0, 1.0, 0.14)).CGColor;
    field.leftView = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 12, 1)];
    field.leftViewMode = UITextFieldViewModeAlways;
    field.autocapitalizationType = UITextAutocapitalizationTypeNone;
    field.autocorrectionType = UITextAutocorrectionTypeNo;
    return field;
}
