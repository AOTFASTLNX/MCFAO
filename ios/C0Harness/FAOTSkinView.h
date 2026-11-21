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

@end

NS_ASSUME_NONNULL_END
