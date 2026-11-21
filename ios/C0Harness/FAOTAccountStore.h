//
//  FAOTAccountStore.h
//  Launcher accounts, settings, content inventory and log retention.
//
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

typedef NS_ENUM(NSInteger, FAOTAccountKind) {
    FAOTAccountKindOffline = 0,
    FAOTAccountKindMicrosoft = 1,
    FAOTAccountKindYggdrasil = 2,
};

@interface FAOTAccount : NSObject

@property (nonatomic, assign) FAOTAccountKind kind;
@property (nonatomic, copy) NSString *name;
@property (nonatomic, copy) NSString *uuid;
@property (nonatomic, copy, nullable) NSString *accessToken;
@property (nonatomic, copy, nullable) NSString *refreshToken;
@property (nonatomic, copy, nullable) NSString *clientToken;
/// API root of an authlib-injector compatible Yggdrasil server.
@property (nonatomic, copy, nullable) NSString *server;
@property (nonatomic, copy, nullable) NSString *skinURL;
@property (nonatomic, assign) NSTimeInterval expiresAt;

@property (nonatomic, readonly) NSString *kindTitle;
@property (nonatomic, readonly) NSString *identifier;

+ (instancetype)offlineAccountWithName:(NSString *)name;
- (NSDictionary<NSString *, id> *)publicDictionary;
+ (instancetype)accountFromPublicDictionary:(NSDictionary<NSString *, id> *)dictionary;

@end

@interface FAOTAccountStore : NSObject

@property (class, readonly) FAOTAccountStore *shared;
/// Never nil: when nothing is signed in this is the persisted offline profile.
@property (nonatomic, readonly) FAOTAccount *activeAccount;

- (void)activateAccount:(FAOTAccount *)account;
- (void)clearActiveAccount;
- (nullable UIImage *)cachedSkinForAccount:(FAOTAccount *)account;
- (void)storeSkinData:(NSData *)data forAccount:(FAOTAccount *)account;
- (void)deleteSkinForAccount:(FAOTAccount *)account;

@end

@interface FAOTLauncherSettings : NSObject

@property (class, readonly) FAOTLauncherSettings *shared;
@property (nonatomic, assign) NSInteger memoryGiB;
@property (nonatomic, copy) NSString *languageCode;
@property (nonatomic, copy) NSString *layoutName;
@property (nonatomic, assign) NSInteger logRetention;
@property (nonatomic, copy) NSString *offlineName;
@property (nonatomic, readonly) NSArray<NSNumber *> *memoryOptions;
@property (nonatomic, readonly) NSString *deviceMemoryCaption;

@end

@interface FAOTLogStore : NSObject

+ (NSString *)directory;
/// Newest first. Each entry has name, date and bytes.
+ (NSArray<NSDictionary<NSString *, id> *> *)files;
+ (void)pruneToRetention:(NSInteger)retention;

@end

@interface FAOTContentCatalog : NSObject

/// Entries contain name, bytes and source.
+ (NSArray<NSDictionary<NSString *, id> *> *)mods;
+ (NSArray<NSDictionary<NSString *, id> *> *)resourcePacks;
+ (NSArray<NSDictionary<NSString *, id> *> *)shaderPacks;

@end

NS_ASSUME_NONNULL_END
