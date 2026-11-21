//
//  FAOTAuthService.h
//  Microsoft device-code login and authlib-injector compatible Yggdrasil login.
//
#import <UIKit/UIKit.h>
#import "FAOTAccountStore.h"

NS_ASSUME_NONNULL_BEGIN

typedef void (^FAOTAccountCompletion)(FAOTAccount * _Nullable account, NSError * _Nullable error);
typedef void (^FAOTSkinCompletion)(UIImage * _Nullable image, NSError * _Nullable error);

@interface FAOTAuthService : NSObject

@property (class, readonly) FAOTAuthService *shared;

- (void)beginMicrosoftLogin:(void (^)(NSDictionary<NSString *, id> * _Nullable challenge, NSError * _Nullable error))completion;
- (void)pollMicrosoftLogin:(NSDictionary<NSString *, id> *)challenge
                completion:(void (^)(FAOTAccount * _Nullable account, BOOL pending,
                                     NSTimeInterval interval, NSError * _Nullable error))completion;

/// Authenticates against {server}/authserver/authenticate. When the server does not select a
/// profile, the caller must choose one from `profiles` and call -completeYggdrasilSession:...
- (void)authenticateYggdrasil:(NSString *)server
                     username:(NSString *)username
                     password:(NSString *)password
                   completion:(void (^)(NSDictionary<NSString *, id> * _Nullable session,
                                        NSArray<NSDictionary<NSString *, id> *> * _Nullable profiles,
                                        NSError * _Nullable error))completion;
- (void)completeYggdrasilSession:(NSDictionary<NSString *, id> *)session
                         profile:(NSDictionary<NSString *, id> *)profile
                          server:(NSString *)server
                      completion:(FAOTAccountCompletion)completion;

- (void)refreshAccount:(FAOTAccount *)account completion:(FAOTAccountCompletion)completion;
- (void)downloadSkinForAccount:(FAOTAccount *)account completion:(FAOTSkinCompletion)completion;

+ (nullable NSString *)normalizedServerURL:(NSString *)input error:(NSError **)error;

@end

NS_ASSUME_NONNULL_END
