//
//  FAOTSkinView.h
//  Head and full-body preview for a downloaded Minecraft skin.
//
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@interface FAOTSkinView : UIView

/// The launcher keeps the original 64x64 texture so the preview can draw unblurred pixels.
@property (nonatomic, strong, nullable) UIImage *skin;
/// Draw only the head (used in compact rows). Defaults to NO (head and body).
@property (nonatomic, assign) BOOL headOnly;
/// Arm width the texture was authored for. Slim skins use 3-pixel arms and a
/// 3-pixel-wide side strip in the 64x64 atlas. Defaults to classic (4 px).
@property (nonatomic, assign) BOOL slim;
/// Horizontal rotation in radians for the full-body preview.
@property (nonatomic, assign) CGFloat yaw;
/// Vertical tilt in radians for the full-body preview.
@property (nonatomic, assign) CGFloat pitch;

@end

NS_ASSUME_NONNULL_END
