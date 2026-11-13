//
//  FAOTControlLayout.h
//  Launcher-side control layout: Pojav-compatible model, import/export and persistence.
//
//  The on-disk JSON keeps Pojav's field names where they exist (keycodes, dynamicX,
//  dynamicY, width, height, bgColor, opacity, cornerRadius, isToggle, displayInGame,
//  displayInMenu, passThruEnabled) so a layout taken from Pojav's source tree can be
//  loaded verbatim and exported back without loss.
//
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// Codes that are not GLFW keys. They mirror Amethyst/Pojav's SPECIALBTN_* range but are
/// offset into a private negative band so they can never collide with a real GLFW key.
typedef NS_ENUM(NSInteger, FAOTSpecialControl) {
    FAOTSpecialNone = 0,
    FAOTSpecialKeyboard = -101,
    FAOTSpecialToggleControls = -102,
    FAOTSpecialPrimaryMouse = -103,
    FAOTSpecialSecondaryMouse = -104,
    FAOTSpecialVirtualMouse = -105,
    FAOTSpecialMiddleMouse = -106,
    FAOTSpecialScrollUp = -107,
    FAOTSpecialScrollDown = -108,
};

/// One on-screen control. Geometry is stored as fractions of the landscape safe area so a
/// layout survives rotation and different device sizes.
@interface FAOTControlModel : NSObject

@property (nonatomic, copy) NSString *name;      // stable id, e.g. "▲", "Jump"
@property (nonatomic, assign) NSInteger keycode; // GLFW keycode or FAOTSpecialControl
@property (nonatomic, assign) CGFloat x, y;      // top-left, fraction of safe area
@property (nonatomic, assign) CGFloat width, height; // fraction of safe-area width
@property (nonatomic, assign) CGFloat opacity;
@property (nonatomic, assign) CGFloat cornerRadius;  // points, clamped when rendered
@property (nonatomic, strong) UIColor *background;
@property (nonatomic, assign) BOOL toggle;        // stays pressed until tapped again
@property (nonatomic, assign) BOOL showInMenu;
@property (nonatomic, assign) BOOL showInGame;

+ (instancetype)modelWithDictionary:(NSDictionary *)dictionary;
- (NSDictionary *)dictionaryRepresentation;
- (NSString *)title;          // short label drawn on the button
- (BOOL)isSpecial;

@end

@interface FAOTControlLayout : NSObject

@property (nonatomic, copy) NSString *name;
@property (nonatomic, strong) NSMutableArray<FAOTControlModel *> *controls;
/// Scale the layout was authored at (Pojav's "scaledAt"); kept for round-tripping.
@property (nonatomic, assign) CGFloat authoredScale;

/// MCFAO's built-in layout: the thirteen controls the game surface shipped with, expressed
/// in the same model so the launcher can edit them.
+ (instancetype)defaultLayout;

/// Accepts Pojav v2.7/v3.4 data: either `{"mControlDataList": [...]}`, Amethyst's
/// `{"control": [...]}`, or a bare array. Throws on malformed input rather than guessing.
+ (nullable instancetype)layoutFromPojavData:(NSData *)data error:(NSError **)error;

/// Accepts the normalised JSON this class writes (see -JSONData).
+ (nullable instancetype)layoutFromJSONData:(NSData *)data error:(NSError **)error;

- (NSData *)JSONData;

/// Documents/controlmap — the same relative layout Pojav uses under POJAV_HOME.
+ (NSString *)layoutDirectory;
+ (NSArray<NSString *> *)availableLayouts;
+ (nullable instancetype)loadNamed:(NSString *)name;
- (BOOL)saveNamed:(NSString *)name error:(NSError **)error;

/// Geometry resolution for the current safe area in landscape.
- (CGRect)frameForControl:(FAOTControlModel *)control inRect:(CGRect)safeArea;

@end

/// Pojav key name ("KEY_W") or GLFW number to a GLFW keycode.
NSInteger FAOTKeycodeFromPojavName(NSString *name);
NSString *FAOTPojavNameForKeycode(NSInteger keycode);

NS_ASSUME_NONNULL_END
