//
//  FAOTSkinView.m
//
#import "FAOTSkinView.h"
#import "FAOTLauncherTheme.h"

static UIImage *FAOTCropSkin(UIImage *skin, CGRect pixels) {
    CGImageRef image = skin.CGImage;
    if (!image) return nil;
    if (CGRectGetMaxX(pixels) > CGImageGetWidth(image) || CGRectGetMaxY(pixels) > CGImageGetHeight(image)) return nil;
    CGImageRef cropped = CGImageCreateWithImageInRect(image, pixels);
    if (!cropped) return nil;
    UIImage *result = [UIImage imageWithCGImage:cropped scale:skin.scale orientation:skin.imageOrientation];
    CGImageRelease(cropped);
    return result;
}

@implementation FAOTSkinView

- (instancetype)initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        self.backgroundColor = UIColor.clearColor;
        self.opaque = NO;
        self.contentMode = UIViewContentModeRedraw;
        self.layer.cornerRadius = 10;
        self.clipsToBounds = YES;
    }
    return self;
}

- (void)setSkin:(UIImage *)skin {
    _skin = skin;
    [self setNeedsDisplay];
}

- (void)setHeadOnly:(BOOL)headOnly {
    _headOnly = headOnly;
    [self setNeedsDisplay];
}

- (void)drawRect:(CGRect)rect {
    CGContextRef context = UIGraphicsGetCurrentContext();
    CGContextSetInterpolationQuality(context, kCGInterpolationNone);
    CGContextSetShouldAntialias(context, NO);
    if (!self.skin.CGImage) {
        [self drawPlaceholderInRect:self.bounds];
        return;
    }

    CGFloat width = CGRectGetWidth(self.bounds);
    CGFloat height = CGRectGetHeight(self.bounds);
    if (self.headOnly) {
        CGFloat side = MIN(width, height);
        CGRect head = CGRectMake((width - side) / 2, (height - side) / 2, side, side);
        [FAOTCropSkin(self.skin, CGRectMake(8, 8, 8, 8)) drawInRect:head];
        [FAOTCropSkin(self.skin, CGRectMake(40, 8, 8, 8)) drawInRect:head];
        return;
    }

    // A 16x32 logical body. Keep integer-ish pixels when possible so the preview stays crisp.
    CGFloat unit = MIN(width / 16.0, height / 32.0);
    CGFloat originX = (width - unit * 16.0) / 2;
    CGFloat originY = (height - unit * 32.0) / 2;
    CGRect (^cell)(CGFloat, CGFloat, CGFloat, CGFloat) = ^CGRect(CGFloat x, CGFloat y, CGFloat w, CGFloat h) {
        return CGRectMake(originX + x * unit, originY + y * unit, w * unit, h * unit);
    };

    BOOL modern = CGImageGetHeight(self.skin.CGImage) >= 64;
    UIImage *body = FAOTCropSkin(self.skin, CGRectMake(20, 20, 8, 12));
    UIImage *rightArm = FAOTCropSkin(self.skin, CGRectMake(44, 20, 4, 12));
    UIImage *leftArm = modern ? FAOTCropSkin(self.skin, CGRectMake(36, 52, 4, 12)) : rightArm;
    UIImage *rightLeg = FAOTCropSkin(self.skin, CGRectMake(4, 20, 4, 12));
    UIImage *leftLeg = modern ? FAOTCropSkin(self.skin, CGRectMake(20, 52, 4, 12)) : rightLeg;
    UIImage *head = FAOTCropSkin(self.skin, CGRectMake(8, 8, 8, 8));
    UIImage *hat = FAOTCropSkin(self.skin, CGRectMake(40, 8, 8, 8));

    [rightLeg drawInRect:cell(4, 20, 4, 12)];
    [leftLeg drawInRect:cell(8, 20, 4, 12)];
    [body drawInRect:cell(4, 8, 8, 12)];
    [rightArm drawInRect:cell(0, 8, 4, 12)];
    [leftArm drawInRect:cell(12, 8, 4, 12)];
    [head drawInRect:cell(4, 0, 8, 8)];
    [hat drawInRect:cell(4, 0, 8, 8)];
}

- (void)drawPlaceholderInRect:(CGRect)rect {
    UIColor *hair = FAOTRGBA(0.20, 0.14, 0.10, 1);
    UIColor *skin = FAOTRGBA(0.78, 0.62, 0.48, 1);
    if (self.headOnly) {
        CGFloat side = MIN(CGRectGetWidth(rect), CGRectGetHeight(rect));
        CGRect head = CGRectMake((CGRectGetWidth(rect) - side) / 2,
                                 (CGRectGetHeight(rect) - side) / 2, side, side);
        [hair setFill];
        UIRectFill(head);
        [skin setFill];
        UIRectFill(CGRectInset(head, side / 8.0, side / 8.0));
        [FAOTRGBA(0.10, 0.10, 0.12, 1) setFill];
        UIRectFill(CGRectMake(CGRectGetMinX(head) + side * 0.28, CGRectGetMinY(head) + side * 0.42,
                              side * 0.12, side * 0.12));
        UIRectFill(CGRectMake(CGRectGetMinX(head) + side * 0.60, CGRectGetMinY(head) + side * 0.42,
                              side * 0.12, side * 0.12));
        return;
    }
    CGFloat unit = MIN(CGRectGetWidth(rect) / 16.0, CGRectGetHeight(rect) / 32.0);
    CGFloat originX = (CGRectGetWidth(rect) - unit * 16.0) / 2;
    CGFloat originY = (CGRectGetHeight(rect) - unit * 32.0) / 2;
    CGRect (^cell)(CGFloat, CGFloat, CGFloat, CGFloat) = ^CGRect(CGFloat x, CGFloat y, CGFloat w, CGFloat h) {
        return CGRectMake(originX + x * unit, originY + y * unit, w * unit, h * unit);
    };
    UIColor *shirt = FAOTRGBA(0.05, 0.55, 0.55, 1);
    UIColor *pants = FAOTRGBA(0.18, 0.20, 0.42, 1);
    UIColor *shoe = FAOTRGBA(0.24, 0.24, 0.26, 1);
    [skin setFill];
    UIRectFill(cell(4, 0, 8, 8));
    [hair setFill];
    UIRectFill(cell(4, 0, 8, 2));
    UIRectFill(cell(4, 0, 1, 6));
    UIRectFill(cell(11, 0, 1, 6));
    [FAOTRGBA(0.10, 0.10, 0.12, 1) setFill];
    UIRectFill(cell(6, 3, 1, 1));
    UIRectFill(cell(9, 3, 1, 1));
    [shirt setFill];
    UIRectFill(cell(4, 8, 8, 10));
    UIRectFill(cell(0, 8, 4, 8));
    UIRectFill(cell(12, 8, 4, 8));
    [skin setFill];
    UIRectFill(cell(0, 16, 4, 4));
    UIRectFill(cell(12, 16, 4, 4));
    [pants setFill];
    UIRectFill(cell(4, 18, 8, 11));
    [shoe setFill];
    UIRectFill(cell(4, 29, 3, 3));
    UIRectFill(cell(9, 29, 3, 3));
}

@end
