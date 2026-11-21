//
//  FAOTAccountStore.m
//
#import "FAOTAccountStore.h"
#import <Security/Security.h>

static NSString *const FAOTAccountMetadataKey = @"FAOTActiveAccountV2";
static NSString *const FAOTTokenService = @"org.fabricaot.c0.accounts";
static NSString *const FAOTTokenAccount = @"tokens";
static NSString *const FAOTMemoryKey = @"FAOTMemoryGiB";
static NSString *const FAOTLanguageKey = @"FAOTLanguage";
static NSString *const FAOTLayoutKey = @"FAOTControlLayout";
static NSString *const FAOTOfflineNameKey = @"FAOTPlayerName";
static NSString *const FAOTLogRetentionKey = @"FAOTLogRetention";

#pragma mark - Keychain

static NSData *FAOTKeychainRead(void) {
    NSDictionary *query = @{
        (__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
        (__bridge id)kSecAttrService: FAOTTokenService,
        (__bridge id)kSecAttrAccount: FAOTTokenAccount,
        (__bridge id)kSecReturnData: @YES,
        (__bridge id)kSecMatchLimit: (__bridge id)kSecMatchLimitOne,
    };
    CFTypeRef value = NULL;
    if (SecItemCopyMatching((__bridge CFDictionaryRef)query, &value) != errSecSuccess || !value) return nil;
    NSData *data = [((__bridge NSData *)value) copy];
    CFRelease(value);
    return data;
}

static void FAOTKeychainWrite(NSData *data) {
    NSDictionary *query = @{
        (__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
        (__bridge id)kSecAttrService: FAOTTokenService,
        (__bridge id)kSecAttrAccount: FAOTTokenAccount,
    };
    if (SecItemUpdate((__bridge CFDictionaryRef)query,
                      (__bridge CFDictionaryRef)@{(__bridge id)kSecValueData: data}) == errSecSuccess) return;
    NSMutableDictionary *insert = [query mutableCopy];
    insert[(__bridge id)kSecValueData] = data;
    insert[(__bridge id)kSecAttrAccessible] = (__bridge id)kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly;
    SecItemAdd((__bridge CFDictionaryRef)insert, NULL);
}

static NSMutableDictionary<NSString *, NSDictionary *> *FAOTTokenMap(void) {
    NSData *data = FAOTKeychainRead();
    id value = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL] : nil;
    return [value isKindOfClass:NSDictionary.class] ? [value mutableCopy] : [NSMutableDictionary dictionary];
}

static void FAOTSaveTokenMap(NSDictionary *map) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:map options:0 error:NULL];
    if (data) FAOTKeychainWrite(data);
}

static NSString *FAOTSafeFileName(NSString *value) {
    NSMutableString *out = [NSMutableString string];
    for (NSUInteger index = 0; index < value.length && out.length < 96; index++) {
        unichar c = [value characterAtIndex:index];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_') {
            [out appendFormat:@"%C", c];
        } else {
            [out appendString:@"_"];
        }
    }
    return out.length ? out : @"account";
}

#pragma mark - Account

@implementation FAOTAccount

+ (instancetype)offlineAccountWithName:(NSString *)name {
    FAOTAccount *account = [FAOTAccount new];
    account.kind = FAOTAccountKindOffline;
    account.name = name.length ? name : @"Dev";
    account.uuid = @"00000000000000000000000000000000";
    return account;
}

- (NSString *)kindTitle {
    switch (self.kind) {
        case FAOTAccountKindMicrosoft: return @"Microsoft 正版";
        case FAOTAccountKindYggdrasil: return @"外置登录";
        default: return @"离线账号";
    }
}

- (NSString *)identifier {
    switch (self.kind) {
        case FAOTAccountKindMicrosoft:
            return [@"microsoft-" stringByAppendingString:self.uuid.length ? self.uuid : self.name];
        case FAOTAccountKindYggdrasil:
            return [@"yggdrasil-" stringByAppendingString:self.uuid.length ? self.uuid : self.name];
        default:
            return [@"offline-" stringByAppendingString:self.name];
    }
}

- (NSDictionary<NSString *, id> *)publicDictionary {
    NSMutableDictionary *dictionary = [@{
        @"kind": @(self.kind),
        @"name": self.name ?: @"",
        @"uuid": self.uuid ?: @"",
        @"expiresAt": @(self.expiresAt),
    } mutableCopy];
    if (self.server.length) dictionary[@"server"] = self.server;
    if (self.skinURL.length) dictionary[@"skinURL"] = self.skinURL;
    return dictionary;
}

+ (instancetype)accountFromPublicDictionary:(NSDictionary<NSString *, id> *)dictionary {
    if (![dictionary isKindOfClass:NSDictionary.class]) return nil;
    FAOTAccount *account = [FAOTAccount new];
    account.kind = [dictionary[@"kind"] integerValue];
    account.name = [dictionary[@"name"] isKindOfClass:NSString.class] ? dictionary[@"name"] : @"";
    account.uuid = [dictionary[@"uuid"] isKindOfClass:NSString.class] ? dictionary[@"uuid"] : @"";
    account.server = [dictionary[@"server"] isKindOfClass:NSString.class] ? dictionary[@"server"] : nil;
    account.skinURL = [dictionary[@"skinURL"] isKindOfClass:NSString.class] ? dictionary[@"skinURL"] : nil;
    account.expiresAt = [dictionary[@"expiresAt"] doubleValue];
    return account;
}

@end

#pragma mark - Store

@interface FAOTAccountStore ()
@property (nonatomic, readwrite) FAOTAccount *activeAccount;
@property (nonatomic, assign) BOOL loaded;
@end

@implementation FAOTAccountStore

+ (FAOTAccountStore *)shared {
    static FAOTAccountStore *store;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ store = [FAOTAccountStore new]; });
    return store;
}

- (NSString *)skinDirectory {
    NSArray<NSString *> *paths = NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES);
    NSString *base = paths.firstObject ?: NSTemporaryDirectory();
    NSString *directory = [base stringByAppendingPathComponent:@"NCL/Skins"];
    [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
    return directory;
}

- (NSString *)skinPathForIdentifier:(NSString *)identifier {
    return [[self skinDirectory] stringByAppendingPathComponent:
            [FAOTSafeFileName(identifier) stringByAppendingPathExtension:@"png"]];
}

- (FAOTAccount *)activeAccount {
    if (!_loaded) {
        _loaded = YES;
        NSDictionary *metadata = [NSUserDefaults.standardUserDefaults dictionaryForKey:FAOTAccountMetadataKey];
        FAOTAccount *account = metadata ? [FAOTAccount accountFromPublicDictionary:metadata] : nil;
        if (!account) {
            account = [FAOTAccount offlineAccountWithName:FAOTLauncherSettings.shared.offlineName];
        } else {
            NSDictionary *tokens = FAOTTokenMap()[account.identifier];
            if ([tokens isKindOfClass:NSDictionary.class]) {
                account.accessToken = [tokens[@"accessToken"] isKindOfClass:NSString.class] ? tokens[@"accessToken"] : nil;
                account.refreshToken = [tokens[@"refreshToken"] isKindOfClass:NSString.class] ? tokens[@"refreshToken"] : nil;
                account.clientToken = [tokens[@"clientToken"] isKindOfClass:NSString.class] ? tokens[@"clientToken"] : nil;
            }
        }
        _activeAccount = account;
    }
    return _activeAccount;
}

- (void)activateAccount:(FAOTAccount *)account {
    if (!account) return;
    _loaded = YES;
    _activeAccount = account;
    [NSUserDefaults.standardUserDefaults setObject:account.publicDictionary forKey:FAOTAccountMetadataKey];
    NSMutableDictionary *map = FAOTTokenMap();
    if (account.accessToken.length || account.refreshToken.length || account.clientToken.length) {
        NSMutableDictionary *tokens = [NSMutableDictionary dictionary];
        if (account.accessToken.length) tokens[@"accessToken"] = account.accessToken;
        if (account.refreshToken.length) tokens[@"refreshToken"] = account.refreshToken;
        if (account.clientToken.length) tokens[@"clientToken"] = account.clientToken;
        map[account.identifier] = tokens;
    }
    FAOTSaveTokenMap(map);
}

- (void)clearActiveAccount {
    FAOTAccount *old = self.activeAccount;
    NSMutableDictionary *map = FAOTTokenMap();
    [map removeObjectForKey:old.identifier];
    FAOTSaveTokenMap(map);
    [NSUserDefaults.standardUserDefaults removeObjectForKey:FAOTAccountMetadataKey];
    _activeAccount = nil;
    _loaded = NO;
}

- (UIImage *)cachedSkinForAccount:(FAOTAccount *)account {
    NSString *path = [self skinPathForIdentifier:account.identifier];
    NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
    if ([attributes[NSFileSize] unsignedLongLongValue] > 4 * 1024 * 1024) return nil;
    return [UIImage imageWithContentsOfFile:path];
}

- (void)storeSkinData:(NSData *)data forAccount:(FAOTAccount *)account {
    if (data.length == 0 || data.length > 2 * 1024 * 1024 || !account) return;
    NSString *path = [self skinPathForIdentifier:account.identifier];
    [data writeToFile:path atomically:YES];
}

- (void)deleteSkinForAccount:(FAOTAccount *)account {
    if (!account) return;
    [NSFileManager.defaultManager removeItemAtPath:[self skinPathForIdentifier:account.identifier] error:nil];
}

@end

#pragma mark - Settings

@implementation FAOTLauncherSettings

+ (FAOTLauncherSettings *)shared {
    static FAOTLauncherSettings *settings;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ settings = [FAOTLauncherSettings new]; });
    return settings;
}

- (NSInteger)memoryCap {
    double physical = (double)NSProcessInfo.processInfo.physicalMemory / 1073741824.0;
    return MAX(1, MIN(8, (NSInteger)floor(physical * 0.55)));
}

- (NSArray<NSNumber *> *)memoryOptions {
    NSMutableArray *values = [NSMutableArray array];
    for (NSInteger value = 1; value <= [self memoryCap]; value++) [values addObject:@(value)];
    return values;
}

- (NSInteger)memoryGiB {
    NSInteger value = [NSUserDefaults.standardUserDefaults integerForKey:FAOTMemoryKey];
    if (value <= 0) value = MIN(2, [self memoryCap]);
    return MAX(1, MIN(value, [self memoryCap]));
}

- (void)setMemoryGiB:(NSInteger)memoryGiB {
    NSInteger value = MAX(1, MIN(memoryGiB, [self memoryCap]));
    [NSUserDefaults.standardUserDefaults setInteger:value forKey:FAOTMemoryKey];
}

- (NSString *)languageCode {
    NSString *value = [NSUserDefaults.standardUserDefaults stringForKey:FAOTLanguageKey];
    if ([value isEqualToString:@"zh_cn"] || [value isEqualToString:@"ja_jp"] || [value isEqualToString:@"en_us"]) return value;
    return @"en_us";
}

- (void)setLanguageCode:(NSString *)languageCode {
    if (![@[@"zh_cn", @"en_us", @"ja_jp"] containsObject:languageCode]) languageCode = @"en_us";
    [NSUserDefaults.standardUserDefaults setObject:languageCode forKey:FAOTLanguageKey];
}

- (NSString *)layoutName {
    NSString *value = [NSUserDefaults.standardUserDefaults stringForKey:FAOTLayoutKey];
    return value.length ? value : @"default";
}

- (void)setLayoutName:(NSString *)layoutName {
    [NSUserDefaults.standardUserDefaults setObject:layoutName.length ? layoutName : @"default" forKey:FAOTLayoutKey];
}

- (NSInteger)logRetention {
    NSInteger value = [NSUserDefaults.standardUserDefaults integerForKey:FAOTLogRetentionKey];
    return value > 0 ? value : 20;
}

- (void)setLogRetention:(NSInteger)logRetention {
    [NSUserDefaults.standardUserDefaults setInteger:MAX(1, MIN(200, logRetention)) forKey:FAOTLogRetentionKey];
    [FAOTLogStore pruneToRetention:self.logRetention];
}

- (NSString *)offlineName {
    NSString *value = [NSUserDefaults.standardUserDefaults stringForKey:FAOTOfflineNameKey];
    return value.length ? value : @"Dev";
}

- (void)setOfflineName:(NSString *)offlineName {
    [NSUserDefaults.standardUserDefaults setObject:offlineName.length ? offlineName : @"Dev" forKey:FAOTOfflineNameKey];
}

- (NSString *)deviceMemoryCaption {
    double physical = (double)NSProcessInfo.processInfo.physicalMemory / 1073741824.0;
    return [NSString stringWithFormat:@"设备 %.0f GB · 可分配 %ld GB", physical, (long)[self memoryCap]];
}

@end

#pragma mark - Logs

@implementation FAOTLogStore

+ (NSString *)directory {
    NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    NSString *directory = [(documents ?: NSTemporaryDirectory()) stringByAppendingPathComponent:@"c0-logs"];
    [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
    return directory;
}

+ (NSArray<NSDictionary<NSString *, id> *> *)files {
    NSArray<NSString *> *names = [NSFileManager.defaultManager contentsOfDirectoryAtPath:[self directory] error:nil] ?: @[];
    NSMutableArray *files = [NSMutableArray array];
    for (NSString *name in names) {
        if (![name hasSuffix:@".log"]) continue;
        NSString *path = [[self directory] stringByAppendingPathComponent:name];
        NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
        if (!attributes) continue;
        [files addObject:@{
            @"name": name,
            @"date": attributes[NSFileModificationDate] ?: NSDate.date,
            @"bytes": attributes[NSFileSize] ?: @0,
            @"path": path,
        }];
    }
    [files sortUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
        return [b[@"date"] compare:a[@"date"]];
    }];
    return files;
}

+ (void)pruneToRetention:(NSInteger)retention {
    NSInteger keep = MAX(1, retention);
    NSArray<NSDictionary *> *files = [self files];
    for (NSUInteger index = (NSUInteger)keep; index < files.count; index++) {
        [NSFileManager.defaultManager removeItemAtPath:files[index][@"path"] error:nil];
    }
}

@end

#pragma mark - Content

static unsigned long long FAOTTreeSize(NSString *path, NSUInteger depth) {
    NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
    if (attributes[NSFileType] == NSFileTypeRegular) return [attributes[NSFileSize] unsignedLongLongValue];
    if (![attributes[NSFileType] isEqual:NSFileTypeDirectory] || depth > 4) return 0;
    unsigned long long total = 0;
    for (NSString *name in [NSFileManager.defaultManager contentsOfDirectoryAtPath:path error:nil] ?: @[]) {
        total += FAOTTreeSize([path stringByAppendingPathComponent:name], depth + 1);
        if (total > 4ULL * 1024 * 1024 * 1024) break;
    }
    return total;
}

@implementation FAOTContentCatalog

+ (NSDictionary<NSString *, id> *)manifest {
    NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    NSArray<NSString *> *paths = @[
        [[(documents ?: NSTemporaryDirectory()) stringByAppendingPathComponent:@"game"] stringByAppendingPathComponent:@"FAOTContentManifest.json"],
        [[NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"instance-seed"] stringByAppendingPathComponent:@"FAOTContentManifest.json"],
    ];
    for (NSString *path in paths) {
        NSData *data = [NSData dataWithContentsOfFile:path];
        id value = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL] : nil;
        if ([value isKindOfClass:NSDictionary.class]) return value;
    }
    return @{};
}

+ (NSArray<NSDictionary<NSString *, id> *> *)entriesInDirectory:(NSString *)directory source:(NSString *)source {
    NSMutableArray *entries = [NSMutableArray array];
    for (NSString *name in [NSFileManager.defaultManager contentsOfDirectoryAtPath:directory error:nil] ?: @[]) {
        if ([name hasPrefix:@"."]) continue;
        NSString *path = [directory stringByAppendingPathComponent:name];
        NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
        BOOL directoryEntry = [attributes[NSFileType] isEqual:NSFileTypeDirectory];
        if (!directoryEntry && [attributes[NSFileType] isEqual:NSFileTypeRegular] == NO) continue;
        [entries addObject:@{
            @"name": name,
            @"bytes": @(FAOTTreeSize(path, 0)),
            @"source": source,
            @"path": path,
        }];
        if (entries.count >= 500) break;
    }
    return entries;
}

+ (NSArray<NSDictionary<NSString *, id> *> *)category:(NSString *)category {
    NSMutableArray *all = [NSMutableArray array];
    NSMutableSet *seen = [NSMutableSet set];
    NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    NSArray<NSDictionary *> *locations = @[
        @{@"path": [(documents ?: NSTemporaryDirectory()) stringByAppendingPathComponent:[@"game" stringByAppendingPathComponent:category]],
          @"source": @"游戏目录"},
        @{@"path": [[NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"instance-seed"] stringByAppendingPathComponent:category],
          @"source": @"构建内置"},
    ];
    for (NSDictionary *location in locations) {
        for (NSDictionary *entry in [self entriesInDirectory:location[@"path"] source:location[@"source"]]) {
            if ([seen containsObject:entry[@"name"]]) continue;
            [seen addObject:entry[@"name"]];
            [all addObject:entry];
        }
    }
    NSArray *compiled = [self manifest][category];
    if ([compiled isKindOfClass:NSArray.class]) {
        for (NSDictionary *item in compiled) {
            if (![item isKindOfClass:NSDictionary.class]) continue;
            NSString *name = item[@"name"];
            if (![name isKindOfClass:NSString.class] || !name.length || [seen containsObject:name]) continue;
            [seen addObject:name];
            [all addObject:@{
                @"name": name,
                @"bytes": [item[@"bytes"] isKindOfClass:NSNumber.class] ? item[@"bytes"] : @0,
                @"source": @"构建内置",
                @"path": @"",
            }];
        }
    }
    [all sortUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
        return [a[@"name"] localizedCaseInsensitiveCompare:b[@"name"]];
    }];
    return all;
}

+ (NSArray<NSDictionary<NSString *, id> *> *)mods { return [self category:@"mods"]; }
+ (NSArray<NSDictionary<NSString *, id> *> *)resourcePacks { return [self category:@"resourcepacks"]; }
+ (NSArray<NSDictionary<NSString *, id> *> *)shaderPacks { return [self category:@"shaderpacks"]; }

@end
