//
//  FAOTControlLayout.m
//
#import "FAOTControlLayout.h"

static NSString *const kFAOTLayoutDirectory = @"controlmap";
static NSString *const kFAOTDefaultName = @"default";

#pragma mark - Key names

static NSDictionary<NSString *, NSNumber *> *FAOTPojavKeyTable(void) {
    static NSDictionary<NSString *, NSNumber *> *table;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        NSMutableDictionary *map = [NSMutableDictionary dictionary];
        // Letters
        for (unichar c = 'A'; c <= 'Z'; c++) {
            NSString *letter = [NSString stringWithFormat:@"%C", c];
            map[[@"KEY_" stringByAppendingString:letter]] = @(c); // GLFW uses ASCII for A-Z
        }
        // Digits
        for (unichar c = '0'; c <= '9'; c++) {
            NSString *digit = [NSString stringWithFormat:@"%C", c];
            map[[@"KEYCODE_" stringByAppendingString:digit]] = @(c);
        }
        NSDictionary *named = @{
            @"KEY_SPACE": @32, @"KEY_ESCAPE": @256, @"KEY_ENTER": @257,
            @"KEY_TAB": @258, @"KEY_BACKSPACE": @259, @"KEY_DELETE": @261,
            @"KEY_INSERT": @260, @"KEY_HOME": @268, @"KEY_END": @269,
            @"KEY_PAGE_UP": @266, @"KEY_PAGE_DOWN": @267,
            @"KEY_DPAD_UP": @265, @"KEY_DPAD_DOWN": @264,
            @"KEY_DPAD_LEFT": @263, @"KEY_DPAD_RIGHT": @262,
            @"KEY_SHIFT_LEFT": @340, @"KEY_SHIFT_RIGHT": @344,
            @"KEY_CTRL_LEFT": @341, @"KEY_CTRL_RIGHT": @345,
            @"KEY_ALT_LEFT": @342, @"KEY_ALT_RIGHT": @346,
            @"KEY_MENU": @348, @"KEY_SYM": @348,
            @"KEY_GRAVE": @96, @"KEY_MINUS": @45, @"KEY_EQUALS": @61,
            @"KEY_LEFT_BRACKET": @91, @"KEY_RIGHT_BRACKET": @93,
            @"KEY_BACKSLASH": @92, @"KEY_SEMICOLON": @59, @"KEY_APOSTROPHE": @39,
            @"KEY_COMMA": @44, @"KEY_PERIOD": @46, @"KEY_SLASH": @47,
        };
        [map addEntriesFromDictionary:named];
        for (int i = 1; i <= 12; i++) {
            map[[NSString stringWithFormat:@"KEY_F%d", i]] = @(289 + i); // F1=290 .. F12=301
        }
        table = map.copy;
    });
    return table;
}

NSInteger FAOTKeycodeFromPojavName(NSString *name) {
    if (name.length == 0) return 0;
    NSNumber *known = FAOTPojavKeyTable()[name.uppercaseString];
    if (known) return known.integerValue;
    if ([name hasPrefix:@"KEYCODE_"]) {
        NSString *tail = [name substringFromIndex:@"KEYCODE_".length];
        return tail.integerValue;
    }
    if ([name hasPrefix:@"KEY_"] && name.length > 4) {
        unichar c = [name characterAtIndex:4];
        if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z')) return c;
        if (c >= '0' && c <= '9') return c;
    }
    return 0;
}

NSString *FAOTPojavNameForKeycode(NSInteger keycode) {
    if (keycode >= 'A' && keycode <= 'Z') {
        return [NSString stringWithFormat:@"KEY_%C", (unichar)keycode];
    }
    if (keycode >= '0' && keycode <= '9') {
        return [NSString stringWithFormat:@"KEYCODE_%C", (unichar)keycode];
    }
    if (keycode >= 290 && keycode <= 301) {
        return [NSString stringWithFormat:@"KEY_F%ld", (long)(keycode - 289)];
    }
    __block NSString *best = nil;
    NSDictionary *table = FAOTPojavKeyTable();
    [table enumerateKeysAndObjectsUsingBlock:^(NSString *name, NSNumber *value, BOOL *stop) {
        if (value.integerValue == keycode) { best = name; *stop = YES; }
    }];
    return best ?: [NSString stringWithFormat:@"KEYCODE_%ld", (long)keycode];
}

#pragma mark - Model

@implementation FAOTControlModel

+ (instancetype)modelWithDictionary:(NSDictionary *)dictionary {
    FAOTControlModel *model = [FAOTControlModel new];
    model.name = [dictionary[@"name"] isKindOfClass:NSString.class] ? dictionary[@"name"] : @"";
    id keycode = dictionary[@"keycode"];
    if ([keycode isKindOfClass:NSNumber.class]) {
        model.keycode = [keycode integerValue];
    } else if ([keycode isKindOfClass:NSString.class]) {
        model.keycode = FAOTKeycodeFromPojavName(keycode);
    }
    model.x = [dictionary[@"x"] doubleValue];
    model.y = [dictionary[@"y"] doubleValue];
    model.width = [dictionary[@"width"] doubleValue] ?: 0.06;
    model.height = [dictionary[@"height"] doubleValue] ?: 0.12;
    model.opacity = dictionary[@"opacity"] ? [dictionary[@"opacity"] doubleValue] : 0.55;
    model.cornerRadius = dictionary[@"cornerRadius"] ? [dictionary[@"cornerRadius"] doubleValue] : 8.0;
    model.toggle = [dictionary[@"toggle"] boolValue];
    model.showInMenu = dictionary[@"showInMenu"] ? [dictionary[@"showInMenu"] boolValue] : YES;
    model.showInGame = dictionary[@"showInGame"] ? [dictionary[@"showInGame"] boolValue] : YES;
    NSString *color = dictionary[@"color"];
    if ([color isKindOfClass:NSString.class] && color.length == 7) {
        unsigned int value = 0;
        NSScanner *scanner = [NSScanner scannerWithString:[color substringFromIndex:1]];
        if ([scanner scanHexInt:&value]) {
            model.background = [UIColor colorWithRed:((value >> 16) & 0xFF) / 255.0
                                               green:((value >> 8) & 0xFF) / 255.0
                                                blue:(value & 0xFF) / 255.0
                                               alpha:1.0];
        }
    }
    return model;
}

- (instancetype)init {
    if ((self = [super init])) {
        _showInMenu = YES;
        _showInGame = YES;
        _opacity = 0.55;
        _cornerRadius = 8.0;
        _background = [UIColor colorWithWhite:0.0 alpha:1.0];
    }
    return self;
}

- (NSDictionary *)dictionaryRepresentation {
    CGFloat red = 0, green = 0, blue = 0, alpha = 1;
    [self.background getRed:&red green:&green blue:&blue alpha:&alpha];
    NSString *color = [NSString stringWithFormat:@"#%02X%02X%02X",
                       (unsigned)lround(red * 255), (unsigned)lround(green * 255), (unsigned)lround(blue * 255)];
    return @{
        @"name": self.name ?: @"",
        @"keycode": @(self.keycode),
        @"x": @(self.x), @"y": @(self.y),
        @"width": @(self.width), @"height": @(self.height),
        @"opacity": @(self.opacity),
        @"cornerRadius": @(self.cornerRadius),
        @"color": color,
        @"toggle": @(self.toggle),
        @"showInMenu": @(self.showInMenu),
        @"showInGame": @(self.showInGame),
    };
}

- (BOOL)isSpecial { return self.keycode < 0 && self.keycode >= FAOTSpecialScrollDown; }

- (NSString *)title {
    if (self.name.length) return self.name;
    if (self.isSpecial) {
        switch (self.keycode) {
            case FAOTSpecialKeyboard: return @"⌨";
            case FAOTSpecialToggleControls: return @"GUI";
            case FAOTSpecialPrimaryMouse: return @"LMB";
            case FAOTSpecialSecondaryMouse: return @"RMB";
            case FAOTSpecialVirtualMouse: return @"◆";
            case FAOTSpecialMiddleMouse: return @"MMB";
            case FAOTSpecialScrollUp: return @"▼";
            case FAOTSpecialScrollDown: return @"▲";
        }
        return @"?";
    }
    if (self.keycode == 32) return @"␣";
    if (self.keycode == 256) return @"Esc";
    if (self.keycode == 258) return @"Tab";
    if (self.keycode >= 290 && self.keycode <= 301) {
        return [NSString stringWithFormat:@"F%ld", (long)(self.keycode - 289)];
    }
    if (self.keycode >= 32 && self.keycode < 127) {
        return [NSString stringWithFormat:@"%C", (unichar)self.keycode];
    }
    return FAOTPojavNameForKeycode(self.keycode);
}

@end

#pragma mark - Layout

@implementation FAOTControlLayout

- (instancetype)init {
    if ((self = [super init])) {
        _controls = [NSMutableArray array];
        _authoredScale = 1.0;
    }
    return self;
}

+ (instancetype)defaultLayout {
    FAOTControlLayout *layout = [FAOTControlLayout new];
    layout.name = kFAOTDefaultName;
    // Reference canvas: a 844 x 390 landscape safe area (iPhone 14-class). Fractions are
    // device independent, so this only fixes the *proportions* of the shipped layout.
    const CGFloat W = 844, H = 390, size = 44, step = 48, left = 8;
    const CGFloat right = W - size - 8, bottom = H - size - 32;
    struct { const char *name; NSInteger code; CGFloat x, y, w, h; } rows[] = {
        {"▲", 'W', left + step, bottom - 2 * step, size, size},
        {"◀", 'A', left, bottom - step, size, size},
        {"▼", 'S', left + step, bottom - step, size, size},
        {"▶", 'D', left + 2 * step, bottom - step, size, size},
        {"Jump", ' ', right, bottom - step, size, size},
        {"Items", 'E', right - step, bottom - step, size, size},
        {"Place", FAOTSpecialSecondaryMouse, right, bottom - 2 * step, size, size},
        {"Break", FAOTSpecialPrimaryMouse, right - step, bottom - 2 * step, size, size},
        {"◀h", FAOTSpecialScrollUp, right - step, bottom, size, size},
        {"▶h", FAOTSpecialScrollDown, right, bottom, size, size},
        {"Pick", FAOTSpecialMiddleMouse, left, bottom, size, size},
        {"Pause", 256, right, 8, size, size},
    };
    for (unsigned i = 0; i < sizeof(rows) / sizeof(rows[0]); i++) {
        FAOTControlModel *model = [FAOTControlModel new];
        model.name = @(rows[i].name);
        model.keycode = rows[i].code;
        model.x = rows[i].x / W;
        model.y = rows[i].y / H;
        model.width = rows[i].w / W;
        model.height = rows[i].h / H;
        model.cornerRadius = 8;
        [layout.controls addObject:model];
    }
    return layout;
}

#pragma mark Dynamic expression evaluation (Pojav compatible)

static CGFloat FAOTEvaluateExpression(NSString *expression, NSDictionary<NSString *, NSNumber *> *variables) {
    NSMutableString *text = [expression mutableCopy];
    for (NSString *key in variables) {
        NSString *token = [NSString stringWithFormat:@"${%@}", key];
        [text replaceOccurrencesOfString:token
                              withString:[NSString stringWithFormat:@"%.4f", variables[key].doubleValue]
                                 options:0
                                   range:NSMakeRange(0, text.length)];
    }
    if ([text rangeOfString:@"${"].location != NSNotFound) {
        return NAN; // unknown variable: refuse to guess
    }
    @try {
        NSExpression *parsed = [NSExpression expressionWithFormat:text];
        id value = [parsed expressionValueWithObject:nil context:nil];
        if ([value isKindOfClass:NSNumber.class]) return [value doubleValue];
    } @catch (NSException *exception) {
        NSLog(@"[FAOT] control expression failed: %@ (%@)", expression, exception.reason);
    }
    return NAN;
}

+ (instancetype)layoutFromPojavData:(NSData *)data error:(NSError **)error {
    id root = [NSJSONSerialization JSONObjectWithData:data options:0 error:error];
    if (!root) return nil;

    NSArray *raw = nil;
    if ([root isKindOfClass:NSArray.class]) {
        raw = root;
    } else if ([root isKindOfClass:NSDictionary.class]) {
        NSDictionary *dictionary = root;
        raw = dictionary[@"controls"] ?: dictionary[@"mControlDataList"] ?: dictionary[@"control"];
        if (!raw && (dictionary[@"keycode"] || dictionary[@"keycodes"])) raw = @[dictionary];
    }
    if (![raw isKindOfClass:NSArray.class]) {
        if (error) *error = [NSError errorWithDomain:@"FAOTControlLayout" code:1
                                           userInfo:@{NSLocalizedDescriptionKey: @"JSON 里没有 mControlDataList / control 数组"}];
        return nil;
    }

    // Pojav authors positions for the landscape screen in points.
    CGSize screen = UIScreen.mainScreen.bounds.size;
    const CGFloat screenWidth = MAX(screen.width, screen.height);
    const CGFloat screenHeight = MIN(screen.width, screen.height);

    FAOTControlLayout *layout = [FAOTControlLayout new];
    layout.name = @"imported";
    NSMutableArray *skipped = [NSMutableArray array];
    for (NSDictionary *entry in raw) {
        if (![entry isKindOfClass:NSDictionary.class]) continue;
        FAOTControlModel *model = [FAOTControlModel new];

        id rawName = entry[@"name"] ?: entry[@"mName"];
        model.name = [rawName isKindOfClass:NSString.class] ? rawName : @"";

        id keycodes = entry[@"keycodes"] ?: entry[@"mKeycodes"];
        NSInteger code = 0;
        if ([keycodes isKindOfClass:NSArray.class] && [keycodes count] > 0) {
            id first = [(NSArray *)keycodes firstObject];
            code = [first isKindOfClass:NSNumber.class] ? [first integerValue] : FAOTKeycodeFromPojavName([first description]);
        } else if (entry[@"keycode"] || entry[@"mKeycode"]) {
            id single = entry[@"keycode"] ?: entry[@"mKeycode"];
            code = [single isKindOfClass:NSNumber.class] ? [single integerValue] : FAOTKeycodeFromPojavName([single description]);
        }
        model.keycode = code;
        // Pojav/Amethyst encode their special buttons as -1..-8; remap into our private band so
        // they can never be mistaken for a GLFW key.
        switch (code) {
            case -1: model.keycode = FAOTSpecialKeyboard; break;
            case -2: model.keycode = FAOTSpecialToggleControls; break;
            case -3: model.keycode = FAOTSpecialPrimaryMouse; break;
            case -4: model.keycode = FAOTSpecialSecondaryMouse; break;
            case -5: model.keycode = FAOTSpecialVirtualMouse; break;
            case -6: model.keycode = FAOTSpecialMiddleMouse; break;
            case -7: model.keycode = FAOTSpecialScrollUp; break;
            case -8: model.keycode = FAOTSpecialScrollDown; break;
            default: break;
        }

        CGFloat width = entry[@"width"] ? [entry[@"width"] doubleValue] : 50.0;
        CGFloat height = entry[@"height"] ? [entry[@"height"] doubleValue] : 50.0;

        NSString *dynamicX = entry[@"dynamicX"] ?: entry[@"mDynamicX"];
        NSString *dynamicY = entry[@"dynamicY"] ?: entry[@"mDynamicY"];
        NSDictionary *variables = @{
            @"top": @0,
            @"left": @0,
            @"right": @(screenWidth - width),
            @"bottom": @(screenHeight - height),
            @"width": @(width),
            @"height": @(height),
            @"screen_width": @(screenWidth),
            @"screen_height": @(screenHeight),
            @"margin": @2,
            @"preferred_scale": @1,
        };

        CGFloat px = NAN, py = NAN;
        if ([dynamicX isKindOfClass:NSString.class]) px = FAOTEvaluateExpression(dynamicX, variables);
        if ([dynamicY isKindOfClass:NSString.class]) py = FAOTEvaluateExpression(dynamicY, variables);
        // Older Pojav layouts carry normalised mXPosition/mYPosition instead.
        if (isnan(px) && entry[@"mXPosition"]) px = [entry[@"mXPosition"] doubleValue] * screenWidth;
        if (isnan(py) && entry[@"mYPosition"]) py = [entry[@"mYPosition"] doubleValue] * screenHeight;
        if (isnan(px) || isnan(py)) {
            [skipped addObject:model.name ?: @"?"];
            continue;
        }

        model.x = px / screenWidth;
        model.y = py / screenHeight;
        model.width = width / screenWidth;
        model.height = height / screenHeight;
        model.opacity = entry[@"opacity"] ? [entry[@"opacity"] doubleValue] : 0.55;
        model.cornerRadius = entry[@"cornerRadius"] ? [entry[@"cornerRadius"] doubleValue] : 6.0;
        model.toggle = [entry[@"isToggle"] boolValue];
        model.showInGame = entry[@"displayInGame"] ? [entry[@"displayInGame"] boolValue] : YES;
        model.showInMenu = entry[@"displayInMenu"] ? [entry[@"displayInMenu"] boolValue] : YES;
        model.background = [UIColor colorWithWhite:0.0 alpha:1.0];

        id argb = entry[@"bgColor"];
        if ([argb isKindOfClass:NSNumber.class]) {
            unsigned int value = [argb unsignedIntValue];
            model.background = [UIColor colorWithRed:((value >> 16) & 0xFF) / 255.0
                                               green:((value >> 8) & 0xFF) / 255.0
                                                blue:(value & 0xFF) / 255.0
                                               alpha:((value >> 24) & 0xFF) / 255.0];
            if (((value >> 24) & 0xFF) == 0) model.background = [UIColor colorWithWhite:0.0 alpha:0.55];
        }
        [layout.controls addObject:model];
    }
    if (layout.controls.count == 0) {
        if (error) *error = [NSError errorWithDomain:@"FAOTControlLayout" code:2
                                           userInfo:@{NSLocalizedDescriptionKey: @"没有可用的控件（位置表达式无法解析）"}];
        return nil;
    }
    if (skipped.count) {
        NSLog(@"[FAOT] control import skipped %lu entries: %@", (unsigned long)skipped.count, skipped);
    }
    return layout;
}

+ (instancetype)layoutFromJSONData:(NSData *)data error:(NSError **)error {
    id root = [NSJSONSerialization JSONObjectWithData:data options:0 error:error];
    if (![root isKindOfClass:NSDictionary.class]) return nil;
    NSArray *items = root[@"controls"];
    if (![items isKindOfClass:NSArray.class]) return [self layoutFromPojavData:data error:error];
    FAOTControlLayout *layout = [FAOTControlLayout new];
    layout.name = [root[@"name"] isKindOfClass:NSString.class] ? root[@"name"] : @"custom";
    layout.authoredScale = [root[@"scaledAt"] doubleValue] ?: 1.0;
    for (NSDictionary *item in items) {
        if ([item isKindOfClass:NSDictionary.class]) {
            [layout.controls addObject:[FAOTControlModel modelWithDictionary:item]];
        }
    }
    return layout;
}

- (NSData *)JSONData {
    NSMutableArray *items = [NSMutableArray arrayWithCapacity:self.controls.count];
    for (FAOTControlModel *model in self.controls) [items addObject:[model dictionaryRepresentation]];
    NSDictionary *root = @{
        @"version": @1,
        @"name": self.name ?: kFAOTDefaultName,
        @"scaledAt": @(self.authoredScale),
        @"controls": items,
    };
    return [NSJSONSerialization dataWithJSONObject:root options:NSJSONWritingPrettyPrinted error:nil];
}

#pragma mark Persistence

+ (NSString *)layoutDirectory {
    NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    return [documents stringByAppendingPathComponent:kFAOTLayoutDirectory];
}

+ (NSArray<NSString *> *)availableLayouts {
    NSMutableArray *names = [NSMutableArray array];
    NSString *directory = [self layoutDirectory];
    for (NSString *file in [[NSFileManager defaultManager] contentsOfDirectoryAtPath:directory error:nil]) {
        if ([file.pathExtension isEqualToString:@"json"]) {
            [names addObject:file.stringByDeletingPathExtension];
        }
    }
    [names sortUsingSelector:@selector(localizedStandardCompare:)];
    return names;
}

+ (instancetype)loadNamed:(NSString *)name {
    NSString *path = [[self layoutDirectory] stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"json"]];
    NSData *data = [NSData dataWithContentsOfFile:path];
    if (!data) return nil;
    NSError *error = nil;
    FAOTControlLayout *layout = [self layoutFromJSONData:data error:&error];
    if (!layout) NSLog(@"[FAOT] layout %@ unreadable: %@", name, error.localizedDescription);
    return layout;
}

- (BOOL)saveNamed:(NSString *)name error:(NSError **)error {
    if (!name.length || ![name isEqualToString:name.lastPathComponent] || [name isEqualToString:@"."] || [name isEqualToString:@".."]) {
        if (error) *error = [NSError errorWithDomain:@"FAOTControlLayout" code:3 userInfo:@{NSLocalizedDescriptionKey:@"布局名称无效"}];
        return NO;
    }
    NSFileManager *manager = [NSFileManager defaultManager];
    NSString *directory = [FAOTControlLayout layoutDirectory];
    if (![manager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:error]) {
        return NO;
    }
    NSString *path = [directory stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"json"]];
    self.name = name;
    NSMutableArray *items = [NSMutableArray array];
    for (FAOTControlModel *control in self.controls) [items addObject:control.dictionaryRepresentation];
    NSDictionary *root = @{@"version":@1, @"name":name, @"scaledAt":@(self.authoredScale), @"controls":items};
    NSData *data = [NSJSONSerialization dataWithJSONObject:root options:NSJSONWritingPrettyPrinted error:error];
    if (!data) return NO;
    return [data writeToFile:path options:NSDataWritingAtomic error:error];
}

#pragma mark Geometry

- (CGRect)frameForControl:(FAOTControlModel *)control inRect:(CGRect)safeArea {
    CGFloat width = MAX(28.0, control.width * safeArea.size.width);
    CGFloat height = MAX(28.0, control.height * safeArea.size.height);
    CGFloat x = safeArea.origin.x + control.x * safeArea.size.width;
    CGFloat y = safeArea.origin.y + control.y * safeArea.size.height;
    // Keep a dragged button inside the safe area instead of letting it fall off-screen.
    x = MIN(MAX(x, safeArea.origin.x), CGRectGetMaxX(safeArea) - width);
    y = MIN(MAX(y, safeArea.origin.y), CGRectGetMaxY(safeArea) - height);
    return CGRectMake(x, y, width, height);
}

@end
