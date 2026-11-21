#import <UIKit/UIKit.h>
#import "../C0Harness/FAOTLauncherViewController.h"

@interface NCLDemoSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@end

@implementation NCLDemoSceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)connectionOptions {
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    FAOTLauncherViewController *launcher = [FAOTLauncherViewController new];
    __weak FAOTLauncherViewController *weakLauncher = launcher;
    launcher.onLaunch = ^(NSString *playerName, NSInteger memoryGiB, NSString *layoutName, NSString *languageCode) {
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"NCL Demo"
            message:@"这是无游戏本体 Demo。启动器页面、账号、资源和设置可用；进入游戏需要用户本地构建的游戏运行库。"
            preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"知道了" style:UIAlertActionStyleDefault handler:nil]];
        [weakLauncher presentViewController:alert animated:YES completion:nil];
    };
    self.window.rootViewController = launcher;
    [self.window makeKeyAndVisible];
    UIWindowSceneGeometryPreferencesIOS *preferences = [[UIWindowSceneGeometryPreferencesIOS alloc] initWithInterfaceOrientations:UIInterfaceOrientationMaskLandscape];
    [(UIWindowScene *)scene requestGeometryUpdateWithPreferences:preferences errorHandler:nil];
}
@end

@interface NCLDemoAppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation NCLDemoAppDelegate
- (UISceneConfiguration *)application:(UIApplication *)application configurationForConnectingSceneSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    UISceneConfiguration *configuration = [[UISceneConfiguration alloc] initWithName:@"NCLDemo" sessionRole:session.role];
    configuration.delegateClass = NCLDemoSceneDelegate.class;
    return configuration;
}
@end

int main(int argc, char *argv[]) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(NCLDemoAppDelegate.class)); }
}
