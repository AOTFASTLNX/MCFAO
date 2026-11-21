//
//  FAOTSkinView.m
//
#import "FAOTSkinView.h"
#import "FAOTLauncherTheme.h"
#import <stdlib.h>

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

typedef struct {
    CGPoint p[4];
    CGRect uv;
    CGFloat depth;
} FAOTSkinFace;

/// Minecraft's box UV layout: every part occupies two rectangles, one for the
/// sides/top/bottom and one for the front/back. Building the six face rects from
/// the part's origin keeps each face's width and height matched to the box.
static void FAOTSkinFacesForBox(CGRect uvOrigin, CGFloat w, CGFloat h, CGFloat d, CGRect out[6]) {
    CGFloat x = CGRectGetMinX(uvOrigin);
    CGFloat y = CGRectGetMinY(uvOrigin);
    out[0] = CGRectMake(x + d,         y + d,         w, h); // front
    out[1] = CGRectMake(x + d + w + d, y + d,         w, h); // back
    out[2] = CGRectMake(x,             y + d,         d, h); // right
    out[3] = CGRectMake(x + d + w,     y + d,         d, h); // left
    out[4] = CGRectMake(x + d,         y,             w, d); // top
    out[5] = CGRectMake(x + d + w,     y,             w, d); // bottom
}

static int FAOTCompareSkinFaceDepth(const void *a, const void *b) {
    CGFloat left = ((const FAOTSkinFace *)a)->depth;
    CGFloat right = ((const FAOTSkinFace *)b)->depth;
    return left < right ? -1 : (left > right ? 1 : 0);
}

/// Slim (Alex) arms are 3x12x3 but keep the classic 4-pixel template offsets in
/// the 64x64 atlas, so the generic box unwrap is off by one pixel. These are the
/// published rects for the arm slot at (x, y).
static void FAOTSkinSlimArmFaces(CGRect uvOrigin, CGRect out[6]) {
    CGFloat x = CGRectGetMinX(uvOrigin);
    CGFloat y = CGRectGetMinY(uvOrigin);
    out[0] = CGRectMake(x + 3, y + 4, 3, 12); // front
    out[1] = CGRectMake(x + 9, y + 4, 3, 12); // back
    out[2] = CGRectMake(x,     y + 4, 3, 12); // right
    out[3] = CGRectMake(x + 6, y + 4, 3, 12); // left
    out[4] = CGRectMake(x + 4, y,     3, 3);  // top
    out[5] = CGRectMake(x + 7, y,     3, 3);  // bottom
}

static CGPoint FAOTProjectPoint(CGFloat x, CGFloat y, CGFloat z, CGFloat yaw, CGFloat pitch,
                                CGPoint center, CGFloat unit, CGFloat *depth) {
    CGFloat cosY = cos(yaw), sinY = sin(yaw);
    CGFloat cosP = cos(pitch), sinP = sin(pitch);
    CGFloat x1 = x * cosY + z * sinY;
    CGFloat z1 = -x * sinY + z * cosY;
    CGFloat y1 = y * cosP - z1 * sinP;
    CGFloat z2 = y * sinP + z1 * cosP;
    if (depth) *depth = z2;
    return CGPointMake(center.x + x1 * unit, center.y - y1 * unit);
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

- (void)setYaw:(CGFloat)yaw {
    _yaw = yaw;
    [self setNeedsDisplay];
}

- (void)setPitch:(CGFloat)pitch {
    _pitch = pitch;
    [self setNeedsDisplay];
}

- (void)setSlim:(BOOL)slim {
    _slim = slim;
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

    // The layered 3D renderer draws both the inner skin and its outer overlay.
    [self drawRotatedBodyInContext:context];
}

- (void)drawRotatedBodyInContext:(CGContextRef)context {
    BOOL modern = CGImageGetHeight(self.skin.CGImage) >= 64;

    // Part layout in Minecraft's 16x32 body space, y up and centred on 0.
    // UV bases follow the official 64x64 atlas: the outer layer reuses the
    // same face layout at a different origin per part.
    typedef struct {
        CGFloat cx, cy, cz, w, h, d;
        CGRect uvBase;
        CGRect uvBaseOuter;
    } FAOTPart;

    // Slim (Alex) skins keep the same atlas origins but use 3-pixel-wide arms,
    // so the arm boxes narrow and move in towards the body.
    CGFloat armWidth = self.slim ? 3.0 : 4.0;
    CGFloat armOffset = 4.0 + armWidth / 2.0;
    const FAOTPart parts[6] = {
        { 0,  12, 0, 8,  8, 8, { 0,  0, 0, 0}, {32,  0, 0, 0}}, // head
        { 0,   2, 0, 8, 12, 4, {16, 16, 0, 0}, {16, 32, 0, 0}}, // body
        {-armOffset, 2, 0, armWidth, 12, armWidth, {40, 16, 0, 0}, {40, 32, 0, 0}}, // right arm
        { armOffset, 2, 0, armWidth, 12, armWidth, {32, 48, 0, 0}, {48, 48, 0, 0}}, // left arm
        {-2, -10, 0, 4, 12, 4, { 0, 16, 0, 0}, { 0, 32, 0, 0}}, // right leg
        { 2, -10, 0, 4, 12, 4, {16, 48, 0, 0}, { 0, 48, 0, 0}}, // left leg
    };

    CGFloat width = CGRectGetWidth(self.bounds);
    CGFloat height = CGRectGetHeight(self.bounds);
    // The figure spans 16 x 32 pixels plus the outer layer; keep a small margin.
    // Drawn at 80% so the full body leaves some breathing room in the card.
    CGFloat unit = MIN(width / 18.0, height / 34.0) * 0.8;
    CGPoint center = CGPointMake(width / 2, height / 2);
    CGContextSetInterpolationQuality(context, kCGInterpolationNone);
    CGContextSetShouldAntialias(context, NO);

    // Corners are ordered so that vertex 0 is the texture's top-left, 1 its
    // top-right, 2 bottom-right and 3 bottom-left. The affine map built from
    // (p0,p1,p3) then puts the atlas upright on every face.
    static const CGFloat corner[6][4][3] = {
        // front (+z)
        {{-1, 1, 1}, {1, 1, 1}, {1, -1, 1}, {-1, -1, 1}},
        // back (-z)
        {{1, 1, -1}, {-1, 1, -1}, {-1, -1, -1}, {1, -1, -1}},
        // right (+x)
        {{1, 1, 1}, {1, 1, -1}, {1, -1, -1}, {1, -1, 1}},
        // left (-x)
        {{-1, 1, -1}, {-1, 1, 1}, {-1, -1, 1}, {-1, -1, -1}},
        // top (+y)
        {{-1, 1, -1}, {1, 1, -1}, {1, 1, 1}, {-1, 1, 1}},
        // bottom (-y)
        {{-1, -1, 1}, {1, -1, 1}, {1, -1, -1}, {-1, -1, -1}},
    };
    static const CGFloat normal[6][3] = {
        {0, 0, 1}, {0, 0, -1}, {1, 0, 0}, {-1, 0, 0}, {0, 1, 0}, {0, -1, 0},
    };

    FAOTSkinFace faces[72];
    NSUInteger faceCount = 0;

    int layerCount = modern ? 2 : 1;
    for (int layer = 0; layer < layerCount; layer++) {
        CGFloat inflate = layer == 0 ? 0.0 : 0.5;
        for (int partIndex = 0; partIndex < 6; partIndex++) {
            FAOTPart part = parts[partIndex];
            CGRect base = layer == 0 ? part.uvBase : part.uvBaseOuter;
            CGRect uvs[6];
            BOOL slimArm = self.slim && (partIndex == 2 || partIndex == 3);
            if (slimArm) {
                FAOTSkinSlimArmFaces(base, uvs);
            } else {
                // Outer layer reuses the same face rect sizes as the inner layer.
                FAOTSkinFacesForBox(base, part.w, part.h, part.d, uvs);
            }

            CGFloat hw = (part.w + inflate) / 2;
            CGFloat hh = (part.h + inflate) / 2;
            CGFloat hd = (part.d + inflate) / 2;

            for (int f = 0; f < 6; f++) {
                CGFloat nx = normal[f][0], ny = normal[f][1], nz = normal[f][2];
                CGFloat cosY = cos(self.yaw), sinY = sin(self.yaw);
                CGFloat cosP = cos(self.pitch), sinP = sin(self.pitch);
                CGFloat nz1 = -nx * sinY + nz * cosY;
                CGFloat ny1 = ny * cosP - nz1 * sinP;
                CGFloat nz2 = ny * sinP + nz1 * cosP;
                (void)ny1;
                if (nz2 <= 0.001) continue; // facing away from the viewer

                CGPoint pts[4];
                CGFloat depth = 0;
                for (int k = 0; k < 4; k++) {
                    CGFloat x = part.cx + corner[f][k][0] * hw;
                    CGFloat y = part.cy + corner[f][k][1] * hh;
                    CGFloat z = part.cz + corner[f][k][2] * hd;
                    CGFloat zd = 0;
                    pts[k] = FAOTProjectPoint(x, y, z, self.yaw, self.pitch, center, unit, &zd);
                    depth += zd / 4.0;
                }
                if (faceCount >= sizeof(faces) / sizeof(faces[0])) continue;
                FAOTSkinFace face = { .uv = uvs[f], .depth = depth };
                memcpy(face.p, pts, sizeof(pts));
                faces[faceCount++] = face;
            }
        }
    }

    qsort(faces, faceCount, sizeof(faces[0]), FAOTCompareSkinFaceDepth);
    for (NSUInteger i = 0; i < faceCount; i++) {
        FAOTSkinFace face = faces[i];
        CGImageRef cropped = CGImageCreateWithImageInRect(self.skin.CGImage, face.uv);
        if (!cropped) continue;
        CGContextSaveGState(context);
        CGMutablePathRef path = CGPathCreateMutable();
        CGPathMoveToPoint(path, NULL, face.p[0].x, face.p[0].y);
        for (int k = 1; k < 4; k++) CGPathAddLineToPoint(path, NULL, face.p[k].x, face.p[k].y);
        CGPathCloseSubpath(path);
        CGContextAddPath(context, path);
        CGContextClip(context);
        // p0=top-left, p1=top-right, p3=bottom-left; the texture is drawn
        // into the unit square with its origin at the top-left, so the map must
        // run down the p0->p3 edge and across the p0->p1 edge.
        CGAffineTransform map = CGAffineTransformMake(face.p[1].x - face.p[0].x, face.p[1].y - face.p[0].y,
                                                      face.p[3].x - face.p[0].x, face.p[3].y - face.p[0].y,
                                                      face.p[0].x, face.p[0].y);
        CGContextConcatCTM(context, map);
        // The quad is built top-down (p0 is the texture's top-left) while
        // CGContextDrawImage paints with its origin at the bottom-left.
        CGContextTranslateCTM(context, 0, 1);
        CGContextScaleCTM(context, 1, -1);
        CGContextDrawImage(context, CGRectMake(0, 0, 1, 1), cropped);
        CGContextRestoreGState(context);
        CGPathRelease(path);
        CGImageRelease(cropped);
    }
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
