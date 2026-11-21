//
//  FAOTLauncherPages.h
//  Game, account, resource and settings pages hosted by the launcher shell.
//
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@protocol FAOTLauncherPageHost <NSObject>
- (void)pageRequestedLaunch;
- (void)pageRequestedLayoutEditor;
- (void)pageRequestedLayoutImport;
- (void)pageAccountsChanged;
- (BOOL)pageGameHasLaunched;
- (void)pageSetGameStatus:(NSString *)status;
@end

@protocol FAOTLauncherPage <NSObject>
- (void)refreshPage;
@end

@interface FAOTGamePageController : UIViewController <FAOTLauncherPage>
- (instancetype)initWithHost:(id<FAOTLauncherPageHost>)host;
- (void)showStatus:(NSString *)status;
@end

@interface FAOTAccountPageController : UIViewController <FAOTLauncherPage>
- (instancetype)initWithHost:(id<FAOTLauncherPageHost>)host;
@end

@interface FAOTResourcesPageController : UIViewController <FAOTLauncherPage>
- (instancetype)initWithHost:(id<FAOTLauncherPageHost>)host;
@end

@interface FAOTSettingsPageController : UIViewController <FAOTLauncherPage>
- (instancetype)initWithHost:(id<FAOTLauncherPageHost>)host;
@end

NS_ASSUME_NONNULL_END
