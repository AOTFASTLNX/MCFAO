//
//  smoke_main.m
//  Minimal host used only to render the launcher and editor in CI for a screenshot.
//  It is not part of the shipping app: main.m in C0Harness wires the same controllers to
//  the AOT harness instead.
//
#import <UIKit/UIKit.h>
#import "FAOTLauncherViewController.h"

@interface SmokeSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property (nonatomic, strong) UIWindow *window;
@end

@implementation SmokeSceneDelegate

- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session
      options:(UISceneConnectionOptions *)options {
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    FAOTLauncherViewController *launcher = [FAOTLauncherViewController new];

    NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
    if (![defaults boolForKey:@"FAOTSmokeSeeded"]) {
        [defaults setBool:YES forKey:@"FAOTSmokeSeeded"];
        [defaults setObject:@"Dev" forKey:FAOTPlayerNameDefaultsKey];
        [defaults setInteger:2 forKey:FAOTMemoryGiBDefaultsKey];
        [defaults setObject:@"default" forKey:FAOTControlLayoutDefaultsKey];
    }
    self.window.rootViewController = launcher;
    [self.window makeKeyAndVisible];

    NSString *mode = NSProcessInfo.processInfo.environment[@"FAOT_SMOKE_MODE"];
    if ([mode isEqualToString:@"editor"]) {
        FAOTControlLayout *layout = [FAOTControlLayout layoutFromPojavData:[FAOTPojavDefaultLayoutJSON() dataUsingEncoding:NSUTF8StringEncoding]
                                                                     error:nil] ?: [FAOTControlLayout defaultLayout];
        FAOTControlEditorViewController *editor =
            [[FAOTControlEditorViewController alloc] initWithLayout:layout
                                                        layoutName:@"default"
                                                        completion:^(FAOTControlLayout *updated, BOOL saved) {
                (void)updated; (void)saved;
            }];
        editor.modalPresentationStyle = UIModalPresentationFullScreen;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.4 * NSEC_PER_SEC)),
                       dispatch_get_main_queue(), ^{
            [launcher presentViewController:editor animated:NO completion:nil];
        });
    }
}

@end

@interface SmokeAppDelegate : UIResponder <UIApplicationDelegate>
@end

@implementation SmokeAppDelegate
- (UISceneConfiguration *)application:(UIApplication *)application
    configurationForConnectingSceneSession:(UISceneSession *)session
                                   options:(UISceneConnectionOptions *)options {
    UISceneConfiguration *config = [[UISceneConfiguration alloc] initWithName:@"Smoke" sessionRole:session.role];
    config.delegateClass = SmokeSceneDelegate.class;
    return config;
}
@end

int main(int argc, char *argv[]) {
    @autoreleasepool {
        return UIApplicationMain(argc, argv, nil, NSStringFromClass(SmokeAppDelegate.class));
    }
}
