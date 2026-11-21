//
//  FAOTLauncherTheme.h
//  Shared visual language for the launcher shell and its pages.
//
#import <UIKit/UIKit.h>

static inline UIColor *FAOTRGBA(CGFloat r, CGFloat g, CGFloat b, CGFloat a) {
    return [UIColor colorWithRed:r green:g blue:b alpha:a];
}

static inline UIColor *FAOTAccentColor(void) { return FAOTRGBA(0.60, 0.95, 0.82, 1.0); }
static inline UIColor *FAOTBackgroundColor(void) { return FAOTRGBA(0.055, 0.063, 0.078, 1.0); }
static inline UIColor *FAOTCardColor(void) { return FAOTRGBA(0.075, 0.098, 0.122, 0.96); }
static inline UIColor *FAOTFieldColor(void) { return FAOTRGBA(1.0, 1.0, 1.0, 0.075); }
static inline UIColor *FAOTPrimaryTextColor(void) { return UIColor.whiteColor; }
static inline UIColor *FAOTSecondaryTextColor(void) { return FAOTRGBA(1, 1, 1, 0.64); }
static inline UIColor *FAOTMutedTextColor(void) { return FAOTRGBA(1, 1, 1, 0.42); }
static inline UIColor *FAOTHairlineColor(void) { return FAOTRGBA(1, 1, 1, 0.10); }

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
        attributes:@{NSForegroundColorAttributeName: FAOTRGBA(1, 1, 1, 0.42)}];
    field.secureTextEntry = secure;
    field.borderStyle = UITextBorderStyleNone;
    field.backgroundColor = FAOTFieldColor();
    field.textColor = UIColor.whiteColor;
    field.tintColor = FAOTAccentColor();
    field.font = [UIFont systemFontOfSize:15 weight:UIFontWeightRegular];
    field.layer.cornerRadius = 10;
    field.leftView = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 12, 1)];
    field.leftViewMode = UITextFieldViewModeAlways;
    field.autocapitalizationType = UITextAutocapitalizationTypeNone;
    field.autocorrectionType = UITextAutocorrectionTypeNo;
    return field;
}
