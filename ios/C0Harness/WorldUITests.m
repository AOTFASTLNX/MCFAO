#import <XCTest/XCTest.h>

// Run only in a dedicated simulator whose C0 sandbox contains the disposable New World save.
@interface WorldUITests : XCTestCase
@end

@implementation WorldUITests
- (XCUICoordinate *)pointIn:(XCUIApplication *)app x:(CGFloat)x y:(CGFloat)y {
    return [app coordinateWithNormalizedOffset:CGVectorMake(x,y)];
}

- (void)attachFrame:(NSString *)name {
    XCTAttachment *frame=[XCTAttachment attachmentWithScreenshot:XCUIScreen.mainScreen.screenshot];
    frame.name=name;
    frame.lifetime=XCTAttachmentLifetimeKeepAlways;
    [self addAttachment:frame];
}

- (void)testLandscapeInventory {
    self.continueAfterFailure=NO;
    XCUIApplication *app=[XCUIApplication new];
    app.launchEnvironment=@{@"FABRICAOT_SIMULATOR_QUICK_WORLD":@"New World",
                            @"FABRICAOT_SIMULATOR_EXTRA_ARGS":@"",
                            @"OS_ACTIVITY_MODE":@"disable"};
    [app launch];
    XCUIElement *forward=app.buttons[@"Move forward"];
    XCTAssertTrue([forward waitForExistenceWithTimeout:90]);
    CGSize screen=XCUIScreen.mainScreen.screenshot.image.size;
    XCTAssertGreaterThan(screen.width,screen.height);
    [[self pointIn:app x:0.52 y:0.66] pressForDuration:0.15
                               thenDragToCoordinate:[self pointIn:app x:0.56 y:0.24]];
    [app.buttons[@"Pick block"] tap];
    [app.buttons[@"Place or use"] tap];
    [self attachFrame:@"landscape-placed-block"];
    [app.buttons[@"Break or attack"] tap];
    [self attachFrame:@"landscape-broke-block"];
    [app.buttons[@"Move backward"] pressForDuration:0.75];
    [self attachFrame:@"landscape-world"];
    [app.buttons[@"Inventory"] tap];
    XCTAssertTrue([app.buttons[@"Back to game"] waitForExistenceWithTimeout:10]);
    [self attachFrame:@"landscape-inventory"];
    [app.buttons[@"Back to game"] tap];
    XCTAssertTrue([forward waitForExistenceWithTimeout:10]);
    [app.buttons[@"Pause"] tap];
    XCTAssertTrue([app.buttons[@"Back to game"] waitForExistenceWithTimeout:10]);
    [self attachFrame:@"landscape-pause"];
    [[self pointIn:app x:0.50 y:0.725] tap];
    [NSThread sleepForTimeInterval:6];
    [self attachFrame:@"landscape-saved-and-exited"];
}

// Requires a disposable dedicated server on the simulator host. MCFAO_TEST_SERVER can override
// the default 127.0.0.1:25566 used by docs/MULTIPLAYER_DIAGNOSTICS.md. The test never changes the
// server's configuration and never disables the loading screen itself.
- (void)testMultiplayerTerrainAndMovement {
    self.continueAfterFailure=NO;
    NSString *server=NSProcessInfo.processInfo.environment[@"MCFAO_TEST_SERVER"] ?: @"127.0.0.1:25566";
    XCUIApplication *app=[XCUIApplication new];
    app.launchEnvironment=@{
        @"FABRICAOT_SIMULATOR_QUICK_SERVER":server,
        @"FABRICAOT_SIMULATOR_EXTRA_ARGS":@"-Dmcfao.diag.play=true -Dmcfao.diag.stallSeconds=20",
        @"OS_ACTIVITY_MODE":@"disable",
    };
    [app launch];
    XCUIElement *forward=app.buttons[@"Move forward"];
    XCTAssertTrue([forward waitForExistenceWithTimeout:120],
                  @"The multiplayer world never became interactive (Loading terrain did not close)");
    [self attachFrame:@"multiplayer-terrain"];
    [forward pressForDuration:1.2];
    [NSThread sleepForTimeInterval:1.0];
    [self attachFrame:@"multiplayer-moved"];
    XCUIElement *jump=app.buttons[@"Jump"];
    XCTAssertTrue([jump exists]);
    [jump tap];
    [NSThread sleepForTimeInterval:0.5];
    [self attachFrame:@"multiplayer-jumped"];
    [app.buttons[@"Break or attack"] tap];
    [self attachFrame:@"multiplayer-interacted"];
}

- (void)testRecollection3InventoryInput {
    self.continueAfterFailure=NO;
    XCUIApplication *app=[XCUIApplication new];
    app.launchEnvironment=@{@"FABRICAOT_SIMULATOR_QUICK_WORLD":@"New World",
                            @"FABRICAOT_SIMULATOR_EXTRA_ARGS":@"",
                            @"OS_ACTIVITY_MODE":@"disable"};
    [app launch];
    XCUIElement *inventory=app.buttons[@"Inventory"];
    XCTAssertTrue([inventory waitForExistenceWithTimeout:90]);
    [inventory tap];
    XCUIElement *back=app.buttons[@"Back to game"];
    XCTAssertTrue([back waitForExistenceWithTimeout:10]);
    [[self pointIn:app x:0.49 y:0.53] tap];
    [self attachFrame:@"recollection3-inventory-after-input"];
    [back tap];
    XCTAssertTrue([inventory waitForExistenceWithTimeout:10]);
}

@end
