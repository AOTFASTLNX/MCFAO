#import <UIKit/UIKit.h>
#include <stdio.h>
#include <unistd.h>
#include "graal_isolate.h"
#include "a1probe.h"

// Bound this small semantic probe's virtual heap reservation on physical iOS.
// Graal's default address-range provider otherwise requests at least 32 GiB.
static const __graal_uword FAOTReservedAddressSpaceBytes = 256ULL * 1024 * 1024;
// Assigned once on the main thread for this process. UI never loads an earlier run.
static NSString *FAOTCurrentReportName;
static NSString *FAOTCurrentLogName;
static NSTimeInterval FAOTCurrentStartedUnix;

static NSString *FAOTDocuments(void) {
    return NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
}

static void FAOTSaveReport(NSDictionary *report, NSString *filename) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:nil];
    [data writeToFile:[FAOTDocuments() stringByAppendingPathComponent:filename] atomically:YES];
    [data writeToFile:[FAOTDocuments() stringByAppendingPathComponent:@"latest.json"] atomically:YES];
}

static void FAOTNotifyUpdated(void) {
    dispatch_async(dispatch_get_main_queue(), ^{
        [NSNotificationCenter.defaultCenter postNotificationName:@"FAOTProbeUpdated" object:nil];
    });
}

static void FAOTRunProbe(void) {
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        NSTimeInterval started = NSDate.date.timeIntervalSince1970;
        NSString *stamp = [NSString stringWithFormat:@"%.0f", started * 1000];
        NSString *reportName = [NSString stringWithFormat:@"b1-result-%@.json", stamp];
        NSString *logName = [NSString stringWithFormat:@"b1-%@.log", stamp];
        FAOTCurrentReportName = reportName;
        FAOTCurrentLogName = logName;
        FAOTCurrentStartedUnix = started;
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
            @autoreleasepool {
                NSString *logPath = [FAOTDocuments() stringByAppendingPathComponent:logName];
                freopen(logPath.fileSystemRepresentation, "a", stdout);
                freopen(logPath.fileSystemRepresentation, "a", stderr);
                setvbuf(stdout, NULL, _IONBF, 0);
                setvbuf(stderr, NULL, _IONBF, 0);
                NSMutableDictionary *report = [@{
                    @"status": @"STARTED", @"scope": @"B1 pre-transformed first-party fixture",
                    @"bundleID": NSBundle.mainBundle.bundleIdentifier,
                    @"probeID": @"B1",
                    @"harnessBuild": [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleVersion"],
                    @"runID": stamp, @"processID": @(getpid()),
                    @"reservedAddressSpaceBytes": @(FAOTReservedAddressSpaceBytes),
                    @"systemVersion": UIDevice.currentDevice.systemVersion,
                    @"startedUnix": @(started), @"log": logName
                } mutableCopy];
                FAOTSaveReport(report, reportName);
                FAOTNotifyUpdated();
                fprintf(stdout, "B1_NATIVE_START\n");
                fprintf(stdout, "B1_RUN_ID %s pid=%d\n", stamp.UTF8String, getpid());
                graal_isolate_t *isolate = NULL;
                graal_isolatethread_t *thread = NULL;
                // Use the public version-1 fields only; later reserved fields are internal.
                graal_create_isolate_params_t parameters = {0};
                parameters.version = 1;
                parameters.reserved_address_space_size = FAOTReservedAddressSpaceBytes;
                fprintf(stdout, "B1_ISOLATE_CONFIG reserved_address_space_bytes=%llu\n",
                        (unsigned long long)parameters.reserved_address_space_size);
                int created = graal_create_isolate(&parameters, &isolate, &thread);
                report[@"createIsolate"] = @(created);
                if (created != 0) {
                    report[@"error"] = (created == 801) ? @"Isolate address-space reservation failed (801)"
                        : [NSString stringWithFormat:@"Isolate creation failed (%d)", created];
                }
                int result = -1;
                int teardown = -1;
                if (created == 0) {
                    NSString *library = [NSBundle.mainBundle.privateFrameworksPath stringByAppendingPathComponent:@"liba1probe.dylib"];
                    NSString *scratch = [FAOTDocuments() stringByAppendingPathComponent:@"probe-files"];
                    result = fabricaot_a1_run(thread, (char *)library.fileSystemRepresentation, (char *)scratch.fileSystemRepresentation);
                    teardown = graal_tear_down_isolate(thread);
                }
                report[@"runResult"] = @(result);
                report[@"tearDownIsolate"] = @(teardown);
                report[@"status"] = (created == 0 && result == 0 && teardown == 0) ? @"PASS" : @"FAIL";
                report[@"finishedUnix"] = @(NSDate.date.timeIntervalSince1970);
                fprintf(stdout, "B1_NATIVE_FINISH create=%d run=%d teardown=%d\n", created, result, teardown);
                fflush(stdout);
                fflush(stderr);
                fsync(fileno(stdout));
                FAOTSaveReport(report, reportName);
                FAOTNotifyUpdated();
            }
        });
    });
}

@interface FAOTSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) UILabel *status;
@end

@implementation FAOTSceneDelegate
- (void)refresh {
    NSData *data = FAOTCurrentReportName
        ? [NSData dataWithContentsOfFile:[FAOTDocuments() stringByAppendingPathComponent:FAOTCurrentReportName]] : nil;
    NSDictionary *report = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    NSString *state = report[@"status"];
    if (!state || [state isEqualToString:@"STARTED"]) state = @"RUNNING · 正在运行";
    NSDateFormatter *formatter = [NSDateFormatter new];
    formatter.locale = [NSLocale localeWithLocaleIdentifier:@"zh_CN"];
    formatter.dateFormat = @"yyyy-MM-dd HH:mm:ss.SSS";
    NSString *startedText = FAOTCurrentStartedUnix > 0
        ? [formatter stringFromDate:[NSDate dateWithTimeIntervalSince1970:FAOTCurrentStartedUnix]] : @"等待启动";
    NSString *duration = report[@"finishedUnix"]
        ? [NSString stringWithFormat:@"%.3f 秒", [report[@"finishedUnix"] doubleValue] - [report[@"startedUnix"] doubleValue]] : @"进行中";
    NSString *detail = report[@"error"] ?: (report[@"createIsolate"]
        ? [NSString stringWithFormat:@"create=%@ run=%@ teardown=%@", report[@"createIsolate"],
           report[@"runResult"] ?: @"pending", report[@"tearDownIsolate"] ?: @"pending"] : @"");
    self.status.text = [NSString stringWithFormat:@"FabricAOT B1 · build %@\nFabric/Mixin AOT fixture\n\n%@\n%@\n\n本次开始：%@\n探针耗时：%@\n日志：%@\n\n每个进程运行一次。重新测试请在后台划掉 App 后打开。",
                       [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleVersion"],
                       state, detail, startedText, duration, FAOTCurrentLogName ?: @"等待生成"];
}
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    UIViewController *controller = [UIViewController new];
    controller.view.backgroundColor = UIColor.systemBackgroundColor;
    self.status = [UILabel new];
    self.status.numberOfLines = 0;
    self.status.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    self.status.adjustsFontForContentSizeCategory = YES;
    self.status.translatesAutoresizingMaskIntoConstraints = NO;
    [controller.view addSubview:self.status];
    [NSLayoutConstraint activateConstraints:@[
        [self.status.leadingAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.leadingAnchor constant:24],
        [self.status.trailingAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.trailingAnchor constant:-24],
        [self.status.topAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.topAnchor constant:24]
    ]];
    self.window.rootViewController = controller;
    [self.window makeKeyAndVisible];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(refresh) name:@"FAOTProbeUpdated" object:nil];
    FAOTRunProbe();
    [self refresh];
}
- (void)sceneDidBecomeActive:(UIScene *)scene { [self refresh]; }
@end

@interface FAOTAppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation FAOTAppDelegate
- (UISceneConfiguration *)application:(UIApplication *)application configurationForConnectingSceneSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    UISceneConfiguration *config = [[UISceneConfiguration alloc] initWithName:@"Probe" sessionRole:session.role];
    config.delegateClass = FAOTSceneDelegate.class;
    return config;
}
@end

int main(int argc, char *argv[]) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(FAOTAppDelegate.class)); }
}
