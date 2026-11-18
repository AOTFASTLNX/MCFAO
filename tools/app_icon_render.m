// Normalise any image ImageIO understands (including SVG, HEIC and WebP) to a
// square PNG for the iOS app icon catalog. Built on demand by app_icon.py with
// the macOS SDK; never shipped in the game bundle.
#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>

static NSString *option(NSArray<NSString *> *arguments, NSString *key) {
  NSUInteger index = [arguments indexOfObject:key];
  return (index != NSNotFound && index + 1 < arguments.count) ? arguments[index + 1] : nil;
}

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    NSArray<NSString *> *arguments = NSProcessInfo.processInfo.arguments;
    NSString *input = option(arguments, @"--input");
    NSString *output = option(arguments, @"--output");
    NSString *fit = option(arguments, @"--fit") ?: @"fit";
    NSString *background = option(arguments, @"--background") ?: @"transparent";
    NSString *paddingText = option(arguments, @"--padding") ?: @"0";
    NSString *sizeText = option(arguments, @"--size") ?: @"1024";
    NSInteger size = sizeText.integerValue;
    double padding = paddingText.doubleValue / 100.0;
    if (!input || !output || size <= 0 || padding < 0 || padding > 0.3) {
      fprintf(stderr, "usage: app_icon_render --input IMAGE --output PNG [--fit fit|fill]"
                      " [--background transparent|#RRGGBB] [--padding PERCENT] [--size PIXELS]\n");
      return 1;
    }
    NSImage *image = [[NSImage alloc] initWithContentsOfFile:input];
    if (!image || image.size.width <= 0 || image.size.height <= 0) {
      fprintf(stderr, "unreadable image: %s\n", input.UTF8String);
      return 2;
    }
    NSRect canvas = NSMakeRect(0, 0, size, size);
    NSBitmapImageRep *bitmap = [[NSBitmapImageRep alloc]
        initWithBitmapDataPlanes:NULL pixelsWide:size pixelsHigh:size bitsPerSample:8
                  samplesPerPixel:4 hasAlpha:YES isPlanar:NO
                   colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:0 bitsPerPixel:0];
    if (!bitmap) {
      fprintf(stderr, "bitmap allocation failed\n");
      return 3;
    }
    [NSGraphicsContext saveGraphicsState];
    NSGraphicsContext *context = [NSGraphicsContext graphicsContextWithBitmapImageRep:bitmap];
    context.imageInterpolation = NSImageInterpolationHigh;
    [NSGraphicsContext setCurrentContext:context];
    [[NSColor clearColor] set];
    NSRectFillUsingOperation(canvas, NSCompositingOperationCopy);
    if (![background isEqualToString:@"transparent"]) {
      unsigned red = 255, green = 255, blue = 255;
      if (sscanf(background.UTF8String, "#%2x%2x%2x", &red, &green, &blue) != 3) {
        fprintf(stderr, "invalid background colour\n");
        return 4;
      }
      [[NSColor colorWithSRGBRed:red / 255.0 green:green / 255.0 blue:blue / 255.0 alpha:1.0] set];
      NSRectFillUsingOperation(canvas, NSCompositingOperationSourceOver);
    }
    // Work in points: NSImage reports its natural size in points for vector
    // sources, so scale that box to the canvas rather than assuming pixels.
    NSSize source = image.size;
    NSRect inner = NSInsetRect(canvas, size * padding, size * padding);
    CGFloat scale = MAX(inner.size.width / source.width, inner.size.height / source.height);
    if ([fit isEqualToString:@"fit"]) {
      scale = MIN(inner.size.width / source.width, inner.size.height / source.height);
    }
    NSSize drawn = NSMakeSize(source.width * scale, source.height * scale);
    NSRect target = NSMakeRect(inner.origin.x + (inner.size.width - drawn.width) / 2.0,
                               inner.origin.y + (inner.size.height - drawn.height) / 2.0,
                               drawn.width, drawn.height);
    [image drawInRect:target fromRect:NSZeroRect operation:NSCompositingOperationSourceOver
             fraction:1.0 respectFlipped:NO
                hints:@{NSImageHintInterpolation: @(NSImageInterpolationHigh)}];
    [NSGraphicsContext restoreGraphicsState];
    NSData *png = [bitmap representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
    if (!png || ![png writeToFile:output atomically:YES]) {
      fprintf(stderr, "could not write png: %s\n", output.UTF8String);
      return 5;
    }
    printf("{\"width\": %.0f, \"height\": %.0f}", source.width, source.height);
    return 0;
  }
}
