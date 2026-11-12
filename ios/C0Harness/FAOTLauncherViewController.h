//
//  FAOTLauncherViewController.h
//  Pre-game launcher: instance/profile summary, memory budget, control layout selection
//  and the editable control editor. Starting the game hands off to the existing harness.
//
#import <UIKit/UIKit.h>
#import "FAOTControlLayout.h"

NS_ASSUME_NONNULL_BEGIN

extern NSString *const FAOTPlayerNameDefaultsKey;   // NSString
extern NSString *const FAOTMemoryGiBDefaultsKey;    // NSNumber
extern NSString *const FAOTControlLayoutDefaultsKey; // NSString, layout name under Documents/controlmap

@interface FAOTLauncherViewController : UIViewController

/// Invoked by the 启动游戏 button. main.m wires this to the AOT harness. Arguments are the
/// player name, the reserved address space in GiB and the chosen control layout name.
@property (nonatomic, copy, nullable) void (^onLaunch)(NSString *playerName, NSInteger memoryGiB, NSString *layoutName);

+ (FAOTControlLayout *)activeLayout;

@end

/// Full-screen editor over a black canvas; nil layout starts from the built-in default.
@interface FAOTControlEditorViewController : UIViewController
- (instancetype)initWithLayout:(FAOTControlLayout *)layout
                    layoutName:(NSString *)layoutName
                    completion:(void (^)(FAOTControlLayout *layout, BOOL saved))completion;
@end

/// The default control set that ships with Pojav (generateAndSaveDefaultControl in
/// CustomControlsUtils.m), kept as JSON so the launcher can hand it to the importer.
NSString *FAOTPojavDefaultLayoutJSON(void);

NS_ASSUME_NONNULL_END
