//
//  FAOTControlsOverlay.h
//  Editable on-screen control surface shared by the launcher editor and the game view.
//
//  Interaction model (same as the Amethyst/Pojav custom controls):
//    * normal mode  — touch down/up is forwarded as a GLFW key or mouse button
//    * editing mode — drag moves a button, pinch resizes it, tap selects it for rebinding,
//                     and no input reaches the game
//
#import <UIKit/UIKit.h>
#import "FAOTControlLayout.h"

NS_ASSUME_NONNULL_BEGIN

@class FAOTControlsOverlay;

@protocol FAOTControlsOverlayDelegate <NSObject>
- (void)controlsOverlay:(FAOTControlsOverlay *)overlay control:(FAOTControlModel *)control pressed:(BOOL)pressed;
- (void)controlsOverlay:(FAOTControlsOverlay *)overlay didSelectControl:(FAOTControlModel *)control;
@optional
- (void)controlsOverlayDidRequestExitEditing:(FAOTControlsOverlay *)overlay;
@end

@interface FAOTControlsOverlay : UIView

@property (nonatomic, weak) id<FAOTControlsOverlayDelegate> delegate;
@property (nonatomic, strong) FAOTControlLayout *layout;
@property (nonatomic, assign, getter=isEditing) BOOL editing;
@property (nonatomic, assign) BOOL menuMode; // menu shows the fewer "displayInMenu" controls
@property (nonatomic, strong, nullable) FAOTControlModel *selectedControl;

- (instancetype)initWithLayout:(FAOTControlLayout *)layout;
- (void)setLayout:(FAOTControlLayout *)layout;
- (void)reloadControls;
- (void)addControl:(FAOTControlModel *)control;
- (void)removeSelectedControl;
/// Releases every control that is currently held, e.g. when the app resigns active.
- (void)releaseAllControls;

@end

NS_ASSUME_NONNULL_END
