//
//  C0Harness/main.m
//
//  Minimal iOS host for the FabricAOT C0 native image of the real Minecraft 26.1.2 client.
//
//  Scope: this app proves only that the AOT image can be *loaded and entered* on a physical
//  iPhone. It can embed the first-party GLFW/JNI/Metal libraries for graphics integration probes.
//  It is a diagnostic host; game resource loading and rendering have separate gates.
//  Whatever the Java side does after entry is recorded verbatim in Documents/c0-logs/.
//
//  The dylib is loaded with dlopen (not linked) so the install name recorded by the linker
//  ("@rpath/FabricAOTClient.dylib") does not have to match the embedded file name.
//

#import <UIKit/UIKit.h>
#import <TargetConditionals.h>
#import <dlfcn.h>
#import <errno.h>
#import <signal.h>
#import <execinfo.h>
#import <mach/mach.h>
#import <os/proc.h>
#import <stdio.h>
#import <string.h>
#import <sys/mman.h>
#import <sys/sysctl.h>
#import <unistd.h>
#include "log_file.h"
#import "FAOTLauncherViewController.h"

// A single process can only ever host one Graal isolate; later attempts return an error.
// The reservation must be bounded because Graal otherwise asks for at least 32 GiB, which
// iOS rejects outright.
static const unsigned long long FAOTReservedSpaceDefault = 4ULL * 1024 * 1024 * 1024;

typedef int (*faot_create_isolate_t)(void *params, void **isolate, void **thread);
typedef int (*faot_run_main_t)(int argc, char **argv);
typedef int (*faot_tear_down_t)(void *thread);


/* Clamped so a 4 GiB phone keeps its native/Metal headroom. */
static long FAOTSelectedHeapGiB(void) {
    NSInteger gib = [NSUserDefaults.standardUserDefaults integerForKey:@"FAOTMemoryGiB"];
    if (gib <= 0) gib = [NSUserDefaults.standardUserDefaults integerForKey:@"reservedGiB"];
    if (gib <= 0) gib = 2;
    if (gib < 1) gib = 1;
    if (gib > 3) gib = 3;
    return (long)gib;
}
static NSString *FAOTDocuments(void) {
    return NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
}

static NSString *FAOTLogDirectory(void) {
    NSString *dir = [FAOTDocuments() stringByAppendingPathComponent:@"c0-logs"];
    [NSFileManager.defaultManager createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:nil error:nil];
    return dir;
}

static NSString *FAOTNewestLog(void) {
    NSArray<NSString *> *names = [NSFileManager.defaultManager contentsOfDirectoryAtPath:FAOTLogDirectory() error:nil];
    NSString *best = nil;
    for (NSString *name in names) {
        if (![name hasSuffix:@".log"]) continue;
        if (!best || [name compare:best] == NSOrderedDescending) best = name;
    }
    return best ? [FAOTLogDirectory() stringByAppendingPathComponent:best] : nil;
}

static NSString *FAOTPhysicalMemoryText(void) {
    unsigned long long bytes = NSProcessInfo.processInfo.physicalMemory;
    return [NSString stringWithFormat:@"%.1f GiB", bytes / 1073741824.0];
}

// ---------------------------------------------------------------------------------------------
// Crash breadcrumbs. Graal installs its own handlers during isolate creation, so these may be
// replaced; when they survive they tell us the signal instead of leaving a silent process death.
static int FAOTCrashFD = -1;

static void FAOTSignalHandler(int signalNumber) {
    const char *name = strsignal(signalNumber);
    char buffer[512];
    int length = snprintf(buffer, sizeof buffer, "\n[FAOT] FATAL signal %d (%s)\n", signalNumber,
                          name ? name : "?");
    if (FAOTCrashFD >= 0) {
        write(FAOTCrashFD, buffer, (size_t)length);
        void *frames[64];
        int count = backtrace(frames, 64);
        backtrace_symbols_fd(frames, count, FAOTCrashFD);
    }
    _exit(128 + signalNumber);
}

static void FAOTInstallCrashHandlers(int fd) {
    FAOTCrashFD = fd;
    int signals[] = {SIGSEGV, SIGBUS, SIGILL, SIGABRT, SIGFPE, SIGTRAP};
    for (size_t i = 0; i < sizeof signals / sizeof signals[0]; i++) {
        signal(signals[i], FAOTSignalHandler);
    }
}

// ---------------------------------------------------------------------------------------------

@interface FAOTHarnessController : UIViewController
@property(nonatomic, strong) UITextView *console;
@property(nonatomic, strong) UILabel *status;
@property(nonatomic, strong) UITextField *extraArgs;
@property(nonatomic, strong) UISegmentedControl *spacePicker;
@property(nonatomic, assign) BOOL started;
@property(nonatomic, assign) BOOL finished;
@property(nonatomic, strong) NSFileHandle *logHandle;
@end

@implementation FAOTHarnessController

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.systemBackgroundColor;

    self.status = [UILabel new];
    self.status.numberOfLines = 0;
    self.status.font = [UIFont monospacedSystemFontOfSize:12 weight:UIFontWeightMedium];
    self.status.translatesAutoresizingMaskIntoConstraints = NO;

    self.spacePicker = [[UISegmentedControl alloc] initWithItems:@[@"1G", @"2G", @"4G", @"6G"]];
    // The resource probe starts with a smaller reservation than a full world.
#if defined(FAOT_DEVICE_WORLD)
    self.spacePicker.selectedSegmentIndex = 1;
#else
    self.spacePicker.selectedSegmentIndex = TARGET_OS_SIMULATOR ? 1 : 0;
    NSInteger saved = [NSUserDefaults.standardUserDefaults integerForKey:@"reservedGiB"];
    if (saved == 2) {
        self.spacePicker.selectedSegmentIndex = 1;
    }
#endif
    self.spacePicker.translatesAutoresizingMaskIntoConstraints = NO;

    self.extraArgs = [UITextField new];
    self.extraArgs.placeholder = @"额外参数（可留空）";
    self.extraArgs.borderStyle = UITextBorderStyleRoundedRect;
    self.extraArgs.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightRegular];
    self.extraArgs.autocorrectionType = UITextAutocorrectionTypeNo;
    self.extraArgs.autocapitalizationType = UITextAutocapitalizationTypeNone;
    self.extraArgs.text = [NSUserDefaults.standardUserDefaults stringForKey:@"extraArgs"];
    self.extraArgs.translatesAutoresizingMaskIntoConstraints = NO;

    UIButton *run = [UIButton buttonWithType:UIButtonTypeSystem];
    [run setTitle:@"启动客户端" forState:UIControlStateNormal];
    run.titleLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    [run addTarget:self action:@selector(runTapped) forControlEvents:UIControlEventTouchUpInside];
    run.translatesAutoresizingMaskIntoConstraints = NO;

    UIButton *copy = [UIButton buttonWithType:UIButtonTypeSystem];
    [copy setTitle:@"复制日志" forState:UIControlStateNormal];
    [copy addTarget:self action:@selector(copyTapped) forControlEvents:UIControlEventTouchUpInside];
    copy.translatesAutoresizingMaskIntoConstraints = NO;

    self.console = [UITextView new];
    self.console.editable = NO;
    self.console.font = [UIFont monospacedSystemFontOfSize:9 weight:UIFontWeightRegular];
    self.console.backgroundColor = [UIColor secondarySystemBackgroundColor];
    self.console.textContainerInset = UIEdgeInsetsMake(6, 6, 6, 6);
    self.console.translatesAutoresizingMaskIntoConstraints = NO;

    for (UIView *view in @[self.status, self.spacePicker, self.extraArgs, run, copy, self.console]) {
        [self.view addSubview:view];
    }
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [self.status.topAnchor constraintEqualToAnchor:safe.topAnchor constant:12],
        [self.status.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:16],
        [self.status.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-16],

        [self.spacePicker.topAnchor constraintEqualToAnchor:self.status.bottomAnchor constant:10],
        [self.spacePicker.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:16],
        [self.spacePicker.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-16],

        [self.extraArgs.topAnchor constraintEqualToAnchor:self.spacePicker.bottomAnchor constant:8],
        [self.extraArgs.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:16],
        [self.extraArgs.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-16],
        [self.extraArgs.heightAnchor constraintEqualToConstant:30],

        [run.topAnchor constraintEqualToAnchor:self.extraArgs.bottomAnchor constant:10],
        [run.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:16],
        [copy.centerYAnchor constraintEqualToAnchor:run.centerYAnchor],
        [copy.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-16],
        [copy.leadingAnchor constraintEqualToAnchor:run.trailingAnchor constant:16],

        [self.console.topAnchor constraintEqualToAnchor:run.bottomAnchor constant:10],
        [self.console.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:12],
        [self.console.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-12],
        [self.console.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-12],
    ]];

    [self refreshStatus];
    [self showPreviousLogTail];
    // Run once per process launch: the isolate cannot be re-created after teardown, so a second
    // in-process attempt would only produce a misleading error.
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.4 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{ [self start]; });
}

- (unsigned long long)reservedBytes {
#if TARGET_OS_SIMULATOR
    // An explicit test override does not persist into the user's settings.
    NSString *requested = NSProcessInfo.processInfo.environment[@"FABRICAOT_SIMULATOR_HEAP_GIB"];
    if ([@[@"1", @"2", @"4", @"6"] containsObject:requested ?: @""]) {
        return requested.longLongValue * 1024ULL * 1024 * 1024;
    }
#endif
    NSInteger index = self.spacePicker.selectedSegmentIndex;
    NSInteger gib = index == 0 ? 1 : index == 1 ? 2 : index == 2 ? 4 : 6;
    [NSUserDefaults.standardUserDefaults setInteger:gib forKey:@"reservedGiB"];
    return (unsigned long long)gib * 1024 * 1024 * 1024;
}

- (void)refreshStatus {
    self.status.text = [NSString stringWithFormat:
        @"C0 · Minecraft 26.1.2 AOT 宿主\n设备 %@ · %@ · 可用内存 %@\n物理内存 %@",
        UIDevice.currentDevice.systemName, UIDevice.currentDevice.systemVersion,
        [NSString stringWithFormat:@"%.1f GiB", os_proc_available_memory() / 1073741824.0],
        FAOTPhysicalMemoryText()];
}

- (void)showPreviousLogTail {
    NSString *path = FAOTNewestLog();
    if (!path) {
        self.console.text = @"（尚无日志）";
        return;
    }
    NSString *text = [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil];
    if (!text) text = @"（日志不是 UTF-8，可在“文件”App 里查看原始文件）";
    self.console.text = [NSString stringWithFormat:@"== 上次运行 %@ ==\n%@",
                         path.lastPathComponent, [self tailOf:text lines:400]];
}

- (NSString *)tailOf:(NSString *)text lines:(NSUInteger)maximum {
    NSArray<NSString *> *lines = [text componentsSeparatedByString:@"\n"];
    if (lines.count <= maximum) return text;
    NSArray<NSString *> *sliced = [lines subarrayWithRange:NSMakeRange(lines.count - maximum, maximum)];
    return [[NSString stringWithFormat:@"…（前 %lu 行省略）\n", (unsigned long)(lines.count - maximum)]
            stringByAppendingString:[sliced componentsJoinedByString:@"\n"]];
}

- (void)copyTapped {
    UIPasteboard.generalPasteboard.string = self.console.text ?: @"";
    self.status.text = @"日志已复制到剪贴板";
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.5 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{ [self refreshStatus]; });
}

- (void)runTapped {
    if (self.started) {
        self.status.text = @"本次进程已运行过一次。iOS 一个进程只能建一个 isolate：\n请在后台划掉本 App 再重新打开。";
        return;
    }
    [self start];
}

- (void)start {
    if (self.started) return;
    self.started = YES;
    [self.extraArgs resignFirstResponder];
    [NSUserDefaults.standardUserDefaults setObject:self.extraArgs.text ?: @"" forKey:@"extraArgs"];

    unsigned long long reserved = [self reservedBytes];
    NSTimeInterval stamp = NSDate.date.timeIntervalSince1970;
    NSString *name = [NSString stringWithFormat:@"run-%.0f.log", stamp * 1000];
    NSString *logPath = [FAOTLogDirectory() stringByAppendingPathComponent:name];

    // Java's tmpdir and HOME are read from the environment by the image's runtime.
    NSString *tmp = [FAOTDocuments() stringByAppendingPathComponent:@"tmp"];
    [NSFileManager.defaultManager createDirectoryAtPath:tmp withIntermediateDirectories:YES attributes:nil error:nil];
    setenv("TMPDIR", tmp.fileSystemRepresentation, 1);
    setenv("HOME", FAOTDocuments().fileSystemRepresentation, 1);

    int logFD = faot_open_append_log(logPath.fileSystemRepresentation);
    if (logFD < 0) {
        self.status.text = [NSString stringWithFormat:@"无法创建本次日志：%s", strerror(errno)];
        return;
    }
    self.logHandle = [[NSFileHandle alloc] initWithFileDescriptor:logFD closeOnDealloc:YES];
    int fd = self.logHandle.fileDescriptor;
    dup2(fd, STDOUT_FILENO);
    dup2(fd, STDERR_FILENO);
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    FAOTInstallCrashHandlers(fd);

    self.status.text = [NSString stringWithFormat:@"启动中 · 预留 %llu GiB · 日志 %@",
                        reserved >> 30, name];

    NSString *extra = self.extraArgs.text ?: @"";
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        [self runImageReserving:reserved logPath:logPath extraArgs:extra];
    });
}

- (void)appendConsole:(NSString *)line {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.console.text = [self.console.text stringByAppendingFormat:@"\n%@", line];
    });
}

// mmap probes. Graal reserves one contiguous PROT_NONE range before it copies the image heap, and
// iOS refuses large reservations. Recording what the process can actually get turns a bare error
// code into a usable number on the next run.
static void FAOTProbeReservations(FILE *logFile) {
    static const unsigned long long sizes[] = {1ULL << 28, 1ULL << 29, 1ULL << 30, 2ULL << 30,
                                               4ULL << 30, 32ULL << 30};
    for (size_t i = 0; i < sizeof sizes / sizeof sizes[0]; i++) {
        void *p = mmap(NULL, (size_t)sizes[i], PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        BOOL ok = (p != MAP_FAILED);
        fprintf(logFile, "[FAOT] probe reserve %llu MiB -> %s\n", sizes[i] >> 20,
                ok ? "OK" : strerror(errno));
        if (ok) {
            int rw = mprotect(p, (size_t)sizes[i], PROT_READ | PROT_WRITE);
            fprintf(logFile, "[FAOT] probe commit  %llu MiB -> %s\n", sizes[i] >> 20,
                    rw == 0 ? "OK" : strerror(errno));
            munmap(p, (size_t)sizes[i]);
        }
        fflush(logFile);
    }
}

- (void)runImageReserving:(unsigned long long)reserved logPath:(NSString *)logPath extraArgs:(NSString *)extra {
    @autoreleasepool {
        // Append + flush per line: when the image aborts (as it does on a failed isolate) anything
        // still sitting in a buffer is lost, which is exactly the diagnostic we need.
        FILE *logFile = fopen(logPath.fileSystemRepresentation, "a");
        void (^emit)(NSString *) = ^(NSString *line) {
            if (logFile) {
                fputs(line.UTF8String, logFile);
                fputc('\n', logFile);
                fflush(logFile);
            }
            [self appendConsole:line];
        };

        NSString *frameworks = NSBundle.mainBundle.privateFrameworksPath;
        NSString *library = [frameworks stringByAppendingPathComponent:@"client-graph.dylib"];
        emit([NSString stringWithFormat:@"[FAOT] bundle=%@", NSBundle.mainBundle.bundleIdentifier]);
        emit([NSString stringWithFormat:@"[FAOT] library=%@ exists=%d", library,
              [NSFileManager.defaultManager fileExistsAtPath:library]]);
        emit([NSString stringWithFormat:@"[FAOT] physicalMemory=%@ reserved=%llu MiB",
              FAOTPhysicalMemoryText(), reserved >> 20]);

        void *handle = dlopen(library.fileSystemRepresentation, RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            emit([NSString stringWithFormat:@"[FAOT] dlopen failed: %s", dlerror()]);
            if (logFile) fclose(logFile);
            [self finishWithStatus:@"dlopen 失败" logPath:logPath];
            return;
        }
        emit(@"[FAOT] dlopen OK");

        faot_run_main_t runMain = (faot_run_main_t)dlsym(handle, "run_main");
        faot_tear_down_t tearDown = (faot_tear_down_t)dlsym(handle, "graal_tear_down_isolate");
        if (!runMain) {
            emit(@"[FAOT] missing entry point run_main");
            if (logFile) fclose(logFile);
            [self finishWithStatus:@"入口缺失" logPath:logPath];
            return;
        }

        if (logFile) FAOTProbeReservations(logFile);

        // run_main creates the isolate itself (JavaMainWrapper's prologue). Creating one here first
        // is not an option: the image only ever holds a single isolate, so the second attempt fails.
        // That prologue reads ReservedAddressSpaceSize from the argument vector, where the default
        // of 0 means "32 GiB" - a reservation iOS rejects with error 801. The bound therefore has to
        // travel as -XX:, not through graal_create_isolate_params_t.
        NSString *game = [FAOTDocuments() stringByAppendingPathComponent:@"game"];
#if defined(FAOT_DEVICE_WORLD)
        NSString *assets = [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"assets"];
#else
        NSString *assets = [FAOTDocuments() stringByAppendingPathComponent:@"assets"];
#endif
        [NSFileManager.defaultManager createDirectoryAtPath:game withIntermediateDirectories:YES attributes:nil error:nil];
#if TARGET_OS_SIMULATOR || defined(FAOT_DEVICE_WORLD)
        // Seed a modest profile on first launch. Minecraft owns this file after it exists.
        NSString *options = [game stringByAppendingPathComponent:@"options.txt"];
        NSData *worldDefaults = [@"renderDistance:8\nsimulationDistance:5\nmaxFps:30\n"
                                 dataUsingEncoding:NSUTF8StringEncoding];
        [worldDefaults writeToFile:options options:NSDataWritingWithoutOverwriting error:nil];
#endif

        NSMutableArray<NSString *> *argvList = [NSMutableArray arrayWithArray:@[
            @"fabricaot-c0",
            [NSString stringWithFormat:@"-XX:ReservedAddressSpaceSize=%llu", reserved],
            /* The launcher's memory picker becomes the runtime heap cap. The image defaults to a
               fixed maximum, so without this the picker had no effect at all. */
            [NSString stringWithFormat:@"-Xmx%ldm", (long)(FAOTSelectedHeapGiB() * 1024)],
            [NSString stringWithFormat:@"-Dorg.lwjgl.librarypath=%@", frameworks],
            @"-Dorg.lwjgl.system.allocator=system",
#if TARGET_OS_SIMULATOR || defined(FAOT_DEVICE_WORLD)
            // 26.1.2 allocates 416 MiB of terrain heaps before drawing the first chunk.
            @"-Dfabricaot.metal.resourceBudgetMiB=768",
#endif
            @"--username", [NSUserDefaults.standardUserDefaults stringForKey:@"FAOTPlayerName"] ?: @"Dev", @"--version", @"26.1.2",
            @"--gameDir", game, @"--assetsDir", assets, @"--assetIndex", @"30",
            @"--uuid", @"00000000000000000000000000000000",
            @"--accessToken", @"0", @"--userType", @"legacy", @"--versionType", @"release",
        ]];
        if (extra.length) {
            [argvList addObjectsFromArray:[extra componentsSeparatedByString:@" "]];
        }
#if TARGET_OS_SIMULATOR
        // Exercise an existing test save through Minecraft's own Quick Play path on a headless host.
        // Pass a save directory name as one argument, including any spaces.
        NSString *quickWorld = NSProcessInfo.processInfo.environment[@"FABRICAOT_SIMULATOR_QUICK_WORLD"];
        if (quickWorld.length) {
            BOOL isName = [quickWorld isEqualToString:quickWorld.lastPathComponent]
                && ![quickWorld isEqualToString:@"."] && ![quickWorld isEqualToString:@".."];
            NSString *saves = [game stringByAppendingPathComponent:@"saves"];
            NSString *world = [saves stringByAppendingPathComponent:quickWorld];
            NSString *level = [world stringByAppendingPathComponent:@"level.dat"];
            if (isName && [NSFileManager.defaultManager fileExistsAtPath:level]) {
                [argvList addObjectsFromArray:@[@"--quickPlaySingleplayer", quickWorld]];
            } else {
                emit(@"[FAOT] Quick Play ignored: an existing local save name is required");
            }
        }
#endif
        // log4j resolves "logs/latest.log" against the working directory, which on a device is "/"
        // and not writable ("Could not create directory /logs"). Starting from the game directory
        // puts those files somewhere real.
        if (chdir(game.fileSystemRepresentation) == 0) {
            char cwd[PATH_MAX] = {0};
            emit([NSString stringWithFormat:@"[FAOT] cwd=%s",
                  getcwd(cwd, sizeof cwd) ?: "(unavailable)"]);
        }
        int argc = (int)argvList.count;
        char **argv = calloc((size_t)argc + 1, sizeof(char *));
        for (int i = 0; i < argc; i++) argv[i] = strdup(argvList[(NSUInteger)i].UTF8String);
        emit([NSString stringWithFormat:@"[FAOT] run_main argc=%d argv=%@", argc,
              [argvList componentsJoinedByString:@" "]]);

        int result = runMain(argc, argv);
        emit([NSString stringWithFormat:@"[FAOT] run_main returned %d", result]);
        typedef void *(*faot_current_thread_t)(void *isolate);
        faot_current_thread_t currentThread =
            (faot_current_thread_t)dlsym(handle, "graal_get_current_thread");
        if (tearDown && currentThread) {
            int teardown = tearDown(currentThread(NULL));
            emit([NSString stringWithFormat:@"[FAOT] graal_tear_down_isolate=%d", teardown]);
        }
        if (logFile) fclose(logFile);
        [self finishWithStatus:[NSString stringWithFormat:@"Java 入口已返回 %d", result]
                       logPath:logPath];
    }
}

- (void)finishWithStatus:(NSString *)text logPath:(NSString *)path {
    FILE *f = fopen(path.fileSystemRepresentation, "a");
    if (f) {
        fprintf(f, "\n[FAOT] %s\n", text.UTF8String);
        fclose(f);
    }
    self.finished = YES;
    dispatch_async(dispatch_get_main_queue(), ^{
        self.status.text = [NSString stringWithFormat:@"%@\n日志：%@", text, path.lastPathComponent];
        [self refreshStatus];
        self.status.text = [NSString stringWithFormat:@"%@\n\n%@", text,
                            ([NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil] ?: @"")];
    });
}

- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    [self refreshStatus];
}

@end

@interface FAOTSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@end

@implementation FAOTSceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session
      options:(UISceneConnectionOptions *)options {
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    FAOTLauncherViewController *launcher = [FAOTLauncherViewController new];
    __weak FAOTLauncherViewController *weakLauncher = launcher;
    launcher.onLaunch = ^(NSString *playerName, NSInteger memoryGiB, NSString *layoutName) {
        NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
        [defaults setObject:playerName forKey:@"FAOTPlayerName"];
        [defaults setInteger:memoryGiB forKey:@"FAOTMemoryGiB"];
        [defaults setInteger:memoryGiB forKey:@"reservedGiB"];  // the harness picker reads this
        [defaults setObject:layoutName forKey:@"FAOTControlLayout"];
        FAOTHarnessController *harness = [FAOTHarnessController new];
        harness.modalPresentationStyle = UIModalPresentationFullScreen;
        [weakLauncher presentViewController:harness animated:YES completion:nil];
    };
    self.window.rootViewController = launcher;
    [self.window makeKeyAndVisible];
}
@end

@interface FAOTAppDelegate : UIResponder <UIApplicationDelegate>
@end

@implementation FAOTAppDelegate
// iOS 26 and later refuse to launch an app that does not adopt the scene life cycle; without
// this method (plus UIApplicationSceneManifest in Info.plist) UIApplicationMain traps with
// EXC_BREAKPOINT before any of our code runs.
- (UISceneConfiguration *)application:(UIApplication *)application
    configurationForConnectingSceneSession:(UISceneSession *)session
                                   options:(UISceneConnectionOptions *)options {
    UISceneConfiguration *config = [[UISceneConfiguration alloc] initWithName:@"C0Harness"
                                                                 sessionRole:session.role];
    config.delegateClass = FAOTSceneDelegate.class;
    return config;
}
@end

int main(int argc, char *argv[]) {
    @autoreleasepool {
        return UIApplicationMain(argc, argv, nil, NSStringFromClass(FAOTAppDelegate.class));
    }
}
