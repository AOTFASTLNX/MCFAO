//
//  FAOTAuthService.m
//
#import "FAOTAuthService.h"

static NSString *const FAOTMicrosoftAuthBase = @"https://login.microsoftonline.com/consumers/oauth2/v2.0/";
static NSString *const FAOTMicrosoftScope = @"XboxLive.signin offline_access";

static NSError *FAOTAuthError(NSString *message) {
    return [NSError errorWithDomain:@"org.fabricaot.account" code:1
                           userInfo:@{NSLocalizedDescriptionKey: message ?: @"登录失败，请稍后重试。"}];
}

static NSString *FAOTPercentEncoded(NSString *value) {
    NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:
        @"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"];
    return [value stringByAddingPercentEncodingWithAllowedCharacters:allowed] ?: @"";
}

static NSString *FAOTClientID(void) {
    NSString *value = [NSBundle.mainBundle objectForInfoDictionaryKey:@"FAOTMicrosoftClientId"];
    return [value isKindOfClass:NSString.class] && value.length ? value : nil;
}

static NSURLRequest *FAOTJSONRequest(NSURL *url, NSString *method, NSDictionary *body, NSString *bearer) {
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url
                                                          cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                      timeoutInterval:20];
    request.HTTPMethod = method;
    [request setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
    [request setValue:@"application/json" forHTTPHeaderField:@"Accept"];
    [request setValue:@"NativeCraft/0.1" forHTTPHeaderField:@"User-Agent"];
    if (bearer.length) [request setValue:[@"Bearer " stringByAppendingString:bearer] forHTTPHeaderField:@"Authorization"];
    if (body) request.HTTPBody = [NSJSONSerialization dataWithJSONObject:body options:0 error:NULL];
    return request;
}

static NSURLRequest *FAOTFormRequest(NSURL *url, NSDictionary<NSString *, NSString *> *values) {
    NSMutableArray *pairs = [NSMutableArray array];
    for (NSString *key in values) {
        [pairs addObject:[NSString stringWithFormat:@"%@=%@", FAOTPercentEncoded(key), FAOTPercentEncoded(values[key])]];
    }
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url
                                                          cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                      timeoutInterval:20];
    request.HTTPMethod = @"POST";
    [request setValue:@"application/x-www-form-urlencoded" forHTTPHeaderField:@"Content-Type"];
    [request setValue:@"application/json" forHTTPHeaderField:@"Accept"];
    [request setValue:@"NativeCraft/0.1" forHTTPHeaderField:@"User-Agent"];
    request.HTTPBody = [[pairs componentsJoinedByString:@"&"] dataUsingEncoding:NSUTF8StringEncoding];
    return request;
}

static void FAOTJSONCall(NSURLRequest *request,
                         void (^completion)(NSDictionary<NSString *, id> *json, NSInteger status, NSError *error)) {
    [[NSURLSession.sharedSession dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        NSInteger status = [response isKindOfClass:NSHTTPURLResponse.class] ? ((NSHTTPURLResponse *)response).statusCode : 0;
        NSDictionary *json = nil;
        NSError *failure = nil;
        if (error) {
            failure = FAOTAuthError(@"无法连接登录服务，请检查网络后重试。");
        } else if (data.length > 1024 * 1024) {
            failure = FAOTAuthError(@"登录服务响应过大，请稍后重试。");
        } else if (data.length) {
            id value = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
            if ([value isKindOfClass:NSDictionary.class]) json = value;
            else failure = FAOTAuthError(@"登录服务返回了无法解析的内容。");
        }
        dispatch_async(dispatch_get_main_queue(), ^{ completion(json, status, failure); });
    }] resume];
}

static NSString *FAOTErrorMessage(NSDictionary *json) {
    for (NSString *key in @[@"errorMessage", @"error_description", @"message", @"error"]) {
        NSString *value = json[key];
        if ([value isKindOfClass:NSString.class] && value.length) return value;
    }
    return nil;
}

static BOOL FAOTAllowedSkinURL(NSURL *url) {
    if ([url.scheme.lowercaseString isEqual:@"https"]) return YES;
    NSString *host = url.host.lowercaseString;
    return [url.scheme.lowercaseString isEqual:@"http"] &&
           ([host isEqual:@"localhost"] || [host isEqual:@"127.0.0.1"]);
}

static void FAOTDownloadImage(NSString *urlString,
                              void (^completion)(UIImage *image, NSError *error)) {
    NSString *trimmed = [urlString stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    NSURL *url = [NSURL URLWithString:trimmed];
    if (!url || !FAOTAllowedSkinURL(url)) {
        completion(nil, FAOTAuthError(@"皮肤地址无效或不是 HTTPS。"));
        return;
    }
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url
                                                          cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                      timeoutInterval:20];
    [request setValue:@"image/png,image/jpeg" forHTTPHeaderField:@"Accept"];
    [[NSURLSession.sharedSession dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        UIImage *image = nil;
        NSError *failure = nil;
        NSInteger status = [response isKindOfClass:NSHTTPURLResponse.class] ? ((NSHTTPURLResponse *)response).statusCode : 0;
        if (error) failure = FAOTAuthError(@"无法下载皮肤，请检查网络后重试。");
        else if (status != 200 || data.length == 0) failure = FAOTAuthError(@"皮肤服务器没有返回图片。");
        else if (data.length > 2 * 1024 * 1024) failure = FAOTAuthError(@"皮肤文件过大。");
        else image = [UIImage imageWithData:data];
        if (!failure && !image) failure = FAOTAuthError(@"皮肤文件无法识别。");
        dispatch_async(dispatch_get_main_queue(), ^{ completion(image, failure); });
    }] resume];
}

static NSString *FAOTTexturesSkinURL(NSDictionary *profile) {
    NSArray *properties = profile[@"properties"];
    if (![properties isKindOfClass:NSArray.class]) return nil;
    for (NSDictionary *property in properties) {
        if (![property isKindOfClass:NSDictionary.class] || ![property[@"name"] isEqual:@"textures"]) continue;
        NSString *value = property[@"value"];
        if (![value isKindOfClass:NSString.class]) continue;
        NSData *data = [[NSData alloc] initWithBase64EncodedString:value options:NSDataBase64DecodingIgnoreUnknownCharacters];
        id decoded = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL] : nil;
        NSDictionary *textures = [decoded isKindOfClass:NSDictionary.class] ? decoded[@"textures"] : nil;
        NSDictionary *skin = [textures isKindOfClass:NSDictionary.class] ? textures[@"SKIN"] : nil;
        NSString *url = [skin isKindOfClass:NSDictionary.class] ? skin[@"url"] : nil;
        if ([url isKindOfClass:NSString.class] && url.length) return url;
    }
    return nil;
}

@interface FAOTAuthService ()
@end

@implementation FAOTAuthService

+ (FAOTAuthService *)shared {
    static FAOTAuthService *service;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ service = [FAOTAuthService new]; });
    return service;
}

#pragma mark Microsoft

- (void)beginMicrosoftLogin:(void (^)(NSDictionary<NSString *, id> *challenge, NSError *error))completion {
    NSString *client = FAOTClientID();
    if (!client.length) {
        completion(nil, FAOTAuthError(@"此构建未配置 Microsoft 登录 Client ID。"));
        return;
    }
    NSURL *url = [NSURL URLWithString:[FAOTMicrosoftAuthBase stringByAppendingString:@"devicecode"]];
    NSURLRequest *request = FAOTFormRequest(url, @{@"client_id": client, @"scope": FAOTMicrosoftScope});
    FAOTJSONCall(request, ^(NSDictionary *json, NSInteger status, NSError *error) {
        if (error) { completion(nil, error); return; }
        NSString *device = json[@"device_code"];
        NSString *user = json[@"user_code"];
        if (status != 200 || ![device isKindOfClass:NSString.class] || ![user isKindOfClass:NSString.class]) {
            completion(nil, FAOTAuthError(FAOTErrorMessage(json) ?: @"Microsoft 登录服务暂不可用。"));
            return;
        }
        NSString *verification = [json[@"verification_uri"] isKindOfClass:NSString.class]
            ? json[@"verification_uri"] : @"https://www.microsoft.com/link";
        NSInteger interval = MAX(5, [json[@"interval"] integerValue]);
        NSTimeInterval expires = [json[@"expires_in"] doubleValue];
        if (expires <= 0) expires = 900;
        completion(@{
            @"deviceCode": device,
            @"userCode": user,
            @"verificationURL": verification,
            @"interval": @(interval),
            @"expiresAt": @(NSDate.date.timeIntervalSince1970 + MIN(expires, 1800)),
        }, nil);
    });
}

- (void)pollMicrosoftLogin:(NSDictionary<NSString *, id> *)challenge
                completion:(void (^)(FAOTAccount *account, BOOL pending, NSTimeInterval interval, NSError *error))completion {
    NSString *client = FAOTClientID();
    NSString *device = challenge[@"deviceCode"];
    NSTimeInterval interval = MAX(5, [challenge[@"interval"] doubleValue]);
    NSTimeInterval expiresAt = [challenge[@"expiresAt"] doubleValue];
    if (!client.length || !device.length) {
        completion(nil, NO, interval, FAOTAuthError(@"登录验证码已失效，请重新获取。"));
        return;
    }
    if (expiresAt > 0 && NSDate.date.timeIntervalSince1970 >= expiresAt) {
        completion(nil, NO, interval, FAOTAuthError(@"登录验证码已过期，请重新获取。"));
        return;
    }
    NSURL *url = [NSURL URLWithString:[FAOTMicrosoftAuthBase stringByAppendingString:@"token"]];
    NSURLRequest *request = FAOTFormRequest(url, @{
        @"grant_type": @"urn:ietf:params:oauth:grant-type:device_code",
        @"client_id": client,
        @"device_code": device,
    });
    FAOTJSONCall(request, ^(NSDictionary *json, NSInteger status, NSError *error) {
        if (error) { completion(nil, NO, interval, error); return; }
        if (status == 200 && [json[@"access_token"] isKindOfClass:NSString.class]) {
            [self verifyMicrosoftAccessToken:json[@"access_token"] refreshToken:json[@"refresh_token"] completion:^(FAOTAccount *account, NSError *failure) {
                completion(account, NO, interval, failure);
            }];
            return;
        }
        NSString *code = [json[@"error"] isKindOfClass:NSString.class] ? json[@"error"] : @"";
        if ([code isEqualToString:@"authorization_pending"]) {
            completion(nil, YES, interval, nil);
        } else if ([code isEqualToString:@"slow_down"]) {
            completion(nil, YES, interval + 5, nil);
        } else if ([code isEqualToString:@"expired_token"] || [code isEqualToString:@"code_expired"]) {
            completion(nil, NO, interval, FAOTAuthError(@"登录验证码已过期，请重新获取。"));
        } else if ([code isEqualToString:@"authorization_declined"] || [code isEqualToString:@"access_denied"]) {
            completion(nil, NO, interval, FAOTAuthError(@"登录已被取消。"));
        } else {
            completion(nil, NO, interval, FAOTAuthError(FAOTErrorMessage(json) ?: @"Microsoft 登录未完成，请重试。"));
        }
    });
}

- (void)verifyMicrosoftAccessToken:(NSString *)microsoftToken
                      refreshToken:(NSString *)refreshToken
                        completion:(FAOTAccountCompletion)completion {
    [self xboxUserToken:microsoftToken completion:^(NSString *userToken, NSString *userHash, NSError *error) {
        if (error) { completion(nil, error); return; }
        [self xstsToken:userToken completion:^(NSString *xstsToken, NSString *xstsHash, NSError *xstsError) {
            if (xstsError) { completion(nil, xstsError); return; }
            if (!userHash.length || ![userHash isEqualToString:xstsHash]) {
                completion(nil, FAOTAuthError(@"Xbox 身份校验不一致，请重新登录。"));
                return;
            }
            [self minecraftTokenWithUserHash:userHash xsts:xstsToken completion:^(NSString *gameToken, NSTimeInterval lifetime, NSError *gameError) {
                if (gameError) { completion(nil, gameError); return; }
                [self checkEntitlements:gameToken completion:^(NSError *entitlementError) {
                    if (entitlementError) { completion(nil, entitlementError); return; }
                    [self minecraftProfile:gameToken completion:^(NSDictionary *profile, NSError *profileError) {
                        if (profileError) { completion(nil, profileError); return; }
                        FAOTAccount *account = [FAOTAccount new];
                        account.kind = FAOTAccountKindMicrosoft;
                        account.name = profile[@"name"];
                        account.uuid = [profile[@"id"] lowercaseString];
                        account.accessToken = gameToken;
                        account.refreshToken = refreshToken;
                        account.expiresAt = NSDate.date.timeIntervalSince1970 + MAX(60, MIN(lifetime - 60, 3600));
                        NSArray *skins = profile[@"skins"];
                        if ([skins isKindOfClass:NSArray.class]) {
                            for (NSDictionary *skin in skins) {
                                if (![skin isKindOfClass:NSDictionary.class]) continue;
                                if ([skin[@"state"] isEqual:@"ACTIVE"] || !account.skinURL) {
                                    if ([skin[@"url"] isKindOfClass:NSString.class]) account.skinURL = skin[@"url"];
                                }
                                if ([skin[@"state"] isEqual:@"ACTIVE"]) break;
                            }
                        }
                        [self downloadSkinForAccount:account completion:^(UIImage *image, NSError *skinError) {
                            completion(account, nil);
                        }];
                    }];
                }];
            }];
        }];
    }];
}

- (void)xboxUserToken:(NSString *)microsoftToken
           completion:(void (^)(NSString *token, NSString *userHash, NSError *error))completion {
    NSDictionary *body = @{
        @"Properties": @{@"AuthMethod": @"RPS", @"SiteName": @"user.auth.xboxlive.com",
                          @"RpsTicket": [@"d=" stringByAppendingString:microsoftToken]},
        @"RelyingParty": @"http://auth.xboxlive.com",
        @"TokenType": @"JWT",
    };
    NSURLRequest *request = FAOTJSONRequest([NSURL URLWithString:@"https://user.auth.xboxlive.com/user/authenticate"], @"POST", body, nil);
    FAOTJSONCall(request, ^(NSDictionary *json, NSInteger status, NSError *error) {
        if (error) { completion(nil, nil, error); return; }
        NSString *token = json[@"Token"];
        NSArray *xui = [json[@"DisplayClaims"] isKindOfClass:NSDictionary.class] ? json[@"DisplayClaims"][@"xui"] : nil;
        NSString *hash = [xui isKindOfClass:NSArray.class] && xui.count && [xui[0] isKindOfClass:NSDictionary.class]
            ? xui[0][@"uhs"] : nil;
        if (status != 200 || ![token isKindOfClass:NSString.class] || ![hash isKindOfClass:NSString.class]) {
            completion(nil, nil, FAOTAuthError(status == 401 || status == 403
                ? @"Xbox Live 拒绝了登录请求，请确认该 Client ID 已获准入。"
                : @"Xbox Live 登录失败，请稍后重试。"));
            return;
        }
        completion(token, hash, nil);
    });
}

- (void)xstsToken:(NSString *)userToken
       completion:(void (^)(NSString *token, NSString *userHash, NSError *error))completion {
    NSDictionary *body = @{
        @"Properties": @{@"SandboxId": @"RETAIL", @"UserTokens": @[userToken]},
        @"RelyingParty": @"rp://api.minecraftservices.com/",
        @"TokenType": @"JWT",
    };
    NSURLRequest *request = FAOTJSONRequest([NSURL URLWithString:@"https://xsts.auth.xboxlive.com/xsts/authorize"], @"POST", body, nil);
    FAOTJSONCall(request, ^(NSDictionary *json, NSInteger status, NSError *error) {
        if (error) { completion(nil, nil, error); return; }
        NSString *token = json[@"Token"];
        NSArray *xui = [json[@"DisplayClaims"] isKindOfClass:NSDictionary.class] ? json[@"DisplayClaims"][@"xui"] : nil;
        NSString *hash = [xui isKindOfClass:NSArray.class] && xui.count && [xui[0] isKindOfClass:NSDictionary.class]
            ? xui[0][@"uhs"] : nil;
        if (status != 200 || ![token isKindOfClass:NSString.class] || ![hash isKindOfClass:NSString.class]) {
            NSNumber *xerr = json[@"XErr"];
            NSString *message = @"Xbox 登录失败，请稍后重试。";
            NSInteger code = [xerr integerValue];
            if (code == 2148916233) message = @"此 Microsoft 账号尚未建立 Xbox 档案。";
            else if (code == 2148916236 || code == 2148916237 ||
                     code == 2148916238 || code == 2148916229) {
                message = @"此账号需要先完成 Microsoft / Xbox 年龄或家庭权限设置。";
            }
            completion(nil, nil, FAOTAuthError(message));
            return;
        }
        completion(token, hash, nil);
    });
}

- (void)minecraftTokenWithUserHash:(NSString *)userHash xsts:(NSString *)xsts
                        completion:(void (^)(NSString *token, NSTimeInterval lifetime, NSError *error))completion {
    NSDictionary *body = @{@"identityToken": [NSString stringWithFormat:@"XBL3.0 x=%@;%@", userHash, xsts]};
    NSURLRequest *request = FAOTJSONRequest([NSURL URLWithString:@"https://api.minecraftservices.com/authentication/login_with_xbox"], @"POST", body, nil);
    FAOTJSONCall(request, ^(NSDictionary *json, NSInteger status, NSError *error) {
        if (error) { completion(nil, 0, error); return; }
        NSString *token = json[@"access_token"];
        if (status != 200 || ![token isKindOfClass:NSString.class]) {
            completion(nil, 0, FAOTAuthError(status == 401 || status == 403
                ? @"Minecraft 服务拒绝了登录请求，该应用可能尚未通过 Minecraft AppID 审核。"
                : @"Minecraft 登录失败，请稍后重试。"));
            return;
        }
        completion(token, MAX(0, [json[@"expires_in"] doubleValue]), nil);
    });
}

- (void)checkEntitlements:(NSString *)token completion:(void (^)(NSError *error))completion {
    NSString *requestId = NSUUID.UUID.UUIDString.lowercaseString;
    NSURL *url = [NSURL URLWithString:[@"https://api.minecraftservices.com/entitlements/license?requestId=" stringByAppendingString:requestId]];
    FAOTJSONCall(FAOTJSONRequest(url, @"GET", nil, token), ^(NSDictionary *json, NSInteger status, NSError *error) {
        if (error) { completion(error); return; }
        if (status != 200) {
            completion(FAOTAuthError(@"无法验证 Minecraft Java 版资格，请稍后重试。"));
            return;
        }
        NSArray *items = json[@"items"];
        BOOL owned = NO;
        if ([items isKindOfClass:NSArray.class]) {
            for (NSDictionary *item in items) {
                if (![item isKindOfClass:NSDictionary.class]) continue;
                NSString *name = item[@"name"];
                if ([name isEqual:@"game_minecraft"] || [name isEqual:@"product_minecraft"]) { owned = YES; break; }
            }
        }
        completion(owned ? nil : FAOTAuthError(@"此账号没有 Minecraft Java Edition 正版资格。"));
    });
}

- (void)minecraftProfile:(NSString *)token completion:(void (^)(NSDictionary *profile, NSError *error))completion {
    NSURL *url = [NSURL URLWithString:@"https://api.minecraftservices.com/minecraft/profile"];
    FAOTJSONCall(FAOTJSONRequest(url, @"GET", nil, token), ^(NSDictionary *json, NSInteger status, NSError *error) {
        if (error) { completion(nil, error); return; }
        if (status == 404) {
            completion(nil, FAOTAuthError(@"此账号尚未创建 Minecraft Java 版档案。"));
            return;
        }
        NSString *identifier = json[@"id"];
        NSString *name = json[@"name"];
        if (status != 200 || ![identifier isKindOfClass:NSString.class] || identifier.length != 32 ||
            ![name isKindOfClass:NSString.class] || name.length == 0) {
            completion(nil, FAOTAuthError(@"Minecraft 档案无效，请先在官网完成档案设置。"));
            return;
        }
        completion(json, nil);
    });
}

#pragma mark Yggdrasil

+ (NSString *)normalizedServerURL:(NSString *)input error:(NSError **)error {
    NSString *raw = [input stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!raw.length) {
        if (error) *error = FAOTAuthError(@"请输入外置登录服务器地址。");
        return nil;
    }
    if (![raw containsString:@"://"]) raw = [@"https://" stringByAppendingString:raw];
    NSURLComponents *components = [NSURLComponents componentsWithString:raw];
    NSString *host = components.host.lowercaseString;
    BOOL local = [host isEqual:@"localhost"] || [host isEqual:@"127.0.0.1"];
    BOOL schemeOK = [components.scheme.lowercaseString isEqual:@"https"] ||
                    ([components.scheme.lowercaseString isEqual:@"http"] && local);
    if (!components || !host.length || !schemeOK || components.user.length || components.password.length) {
        if (error) *error = FAOTAuthError(@"服务器地址必须是 HTTPS；本机调试可使用 http://localhost。");
        return nil;
    }
    NSString *path = components.path.length ? components.path : @"";
    if (path.length == 0 || [path isEqual:@"/"]) path = @"/api/yggdrasil";
    while (path.length > 1 && [path hasSuffix:@"/"]) path = [path substringToIndex:path.length - 1];
    components.path = path;
    components.query = nil;
    components.fragment = nil;
    return components.URL.absoluteString;
}

- (void)authenticateYggdrasil:(NSString *)server
                     username:(NSString *)username
                     password:(NSString *)password
                   completion:(void (^)(NSDictionary<NSString *, id> *session,
                                        NSArray<NSDictionary<NSString *, id> *> *profiles,
                                        NSError *error))completion {
    NSError *urlError = nil;
    NSString *root = [FAOTAuthService normalizedServerURL:server error:&urlError];
    if (!root) { completion(nil, nil, urlError); return; }
    if (!username.length || !password.length) {
        completion(nil, nil, FAOTAuthError(@"请输入用户名和密码。"));
        return;
    }
    FAOTJSONCall(FAOTJSONRequest([NSURL URLWithString:root], @"GET", nil, nil), ^(NSDictionary *meta, NSInteger metaStatus, NSError *metaError) {
        if (metaError) { completion(nil, nil, metaError); return; }
        if (metaStatus != 200 || ![meta isKindOfClass:NSDictionary.class]) {
            completion(nil, nil, FAOTAuthError(@"无法读取外置登录服务器信息，请确认地址填写正确。"));
            return;
        }
        NSString *clientToken = NSUUID.UUID.UUIDString.lowercaseString;
        NSDictionary *body = @{
            @"agent": @{@"name": @"Minecraft", @"version": @1},
            @"username": username,
            @"password": password,
            @"clientToken": clientToken,
            @"requestUser": @YES,
        };
        NSURL *url = [NSURL URLWithString:[root stringByAppendingString:@"/authserver/authenticate"]];
        FAOTJSONCall(FAOTJSONRequest(url, @"POST", body, nil), ^(NSDictionary *json, NSInteger status, NSError *error) {
            if (error) { completion(nil, nil, error); return; }
            NSString *token = json[@"accessToken"];
            if (status != 200 || ![token isKindOfClass:NSString.class] || !token.length) {
                NSString *message = FAOTErrorMessage(json);
                if (status == 401 || status == 403) {
                    message = message.length ? [NSString stringWithFormat:@"登录失败：%@", message]
                                             : @"用户名或密码错误，或账号尚未完成邮箱验证。";
                }
                completion(nil, nil, FAOTAuthError(message ?: @"外置登录失败，请稍后重试。"));
                return;
            }
            NSMutableDictionary *session = [@{@"accessToken": token, @"clientToken": clientToken} mutableCopy];
            if ([json[@"selectedProfile"] isKindOfClass:NSDictionary.class]) session[@"selectedProfile"] = json[@"selectedProfile"];
            NSMutableArray<NSDictionary *> *profiles = [NSMutableArray array];
            if ([json[@"availableProfiles"] isKindOfClass:NSArray.class]) {
                for (NSDictionary *profile in json[@"availableProfiles"]) {
                    if (![profile isKindOfClass:NSDictionary.class]) continue;
                    NSString *identifier = profile[@"id"];
                    NSString *name = profile[@"name"];
                    if ([identifier isKindOfClass:NSString.class] && [name isKindOfClass:NSString.class] &&
                        identifier.length == 32 && name.length) {
                        [profiles addObject:@{@"id": [identifier lowercaseString], @"name": name}];
                    }
                }
            }
            session[@"profiles"] = profiles;
            completion(session, profiles, nil);
        });
    });
}

- (void)completeYggdrasilSession:(NSDictionary<NSString *, id> *)session
                         profile:(NSDictionary<NSString *, id> *)profile
                          server:(NSString *)server
                      completion:(FAOTAccountCompletion)completion {
    NSString *uuid = [profile[@"id"] isKindOfClass:NSString.class] ? [profile[@"id"] lowercaseString] : nil;
    NSString *name = profile[@"name"];
    if (!uuid.length || ![name isKindOfClass:NSString.class] || !name.length) {
        completion(nil, FAOTAuthError(@"该账号没有可用的游戏档案。"));
        return;
    }
    NSError *urlError = nil;
    NSString *root = [FAOTAuthService normalizedServerURL:server error:&urlError];
    if (!root) { completion(nil, urlError); return; }
    FAOTAccount *account = [FAOTAccount new];
    account.kind = FAOTAccountKindYggdrasil;
    account.name = name;
    account.uuid = uuid;
    account.server = root;
    account.accessToken = session[@"accessToken"];
    account.clientToken = session[@"clientToken"];
    account.expiresAt = NSDate.date.timeIntervalSince1970 + 6 * 3600;
    [self refreshYggdrasilProfileForAccount:account completion:^(FAOTAccount *updated, NSError *error) {
        if (updated) updated.expiresAt = NSDate.date.timeIntervalSince1970 + 6 * 3600;
        completion(updated ?: account, error);
    }];
}

- (void)refreshYggdrasilProfileForAccount:(FAOTAccount *)account completion:(FAOTAccountCompletion)completion {
    NSString *root = account.server;
    NSString *uuid = account.uuid;
    if (!root.length || !uuid.length) {
        completion(nil, FAOTAuthError(@"外置登录信息不完整，请重新登录。"));
        return;
    }
    NSString *encoded = [uuid stringByAddingPercentEncodingWithAllowedCharacters:NSCharacterSet.URLPathAllowedCharacterSet];
    NSString *path = [NSString stringWithFormat:@"%@/sessionserver/session/minecraft/profile/%@?unsigned=false", root, encoded];
    FAOTJSONCall(FAOTJSONRequest([NSURL URLWithString:path], @"GET", nil, nil), ^(NSDictionary *json, NSInteger status, NSError *error) {
        if (error) { completion(nil, error); return; }
        NSString *name = json[@"name"];
        if (status != 200 || ![name isKindOfClass:NSString.class]) {
            completion(nil, FAOTAuthError(@"无法读取外置登录档案，请重新登录。"));
            return;
        }
        account.name = name;
        NSString *skinURL = FAOTTexturesSkinURL(json);
        if (skinURL.length) {
            if ([skinURL hasPrefix:@"/"]) {
                NSURL *base = [NSURL URLWithString:root];
                skinURL = [[NSURL URLWithString:skinURL relativeToURL:base] absoluteString];
            }
            account.skinURL = skinURL;
        }
        if (!account.skinURL.length) {
            completion(account, nil);
            return;
        }
        FAOTDownloadImage(account.skinURL, ^(UIImage *image, NSError *skinError) {
            if (image) [FAOTAccountStore.shared storeSkinData:UIImagePNGRepresentation(image) forAccount:account];
            completion(account, nil);
        });
    });
}

- (void)refreshAccount:(FAOTAccount *)account completion:(FAOTAccountCompletion)completion {
    if (!account || account.kind == FAOTAccountKindOffline) { completion(account, nil); return; }
    if (account.kind == FAOTAccountKindMicrosoft) {
        NSString *client = FAOTClientID();
        if (!client.length || !account.refreshToken.length) {
            completion(nil, FAOTAuthError(@"登录已过期，请重新使用 Microsoft 登录。"));
            return;
        }
        NSURL *url = [NSURL URLWithString:[FAOTMicrosoftAuthBase stringByAppendingString:@"token"]];
        NSURLRequest *request = FAOTFormRequest(url, @{
            @"grant_type": @"refresh_token",
            @"client_id": client,
            @"scope": FAOTMicrosoftScope,
            @"refresh_token": account.refreshToken,
        });
        FAOTJSONCall(request, ^(NSDictionary *json, NSInteger status, NSError *error) {
            if (error) { completion(nil, error); return; }
            NSString *token = json[@"access_token"];
            NSString *refresh = [json[@"refresh_token"] isKindOfClass:NSString.class] ? json[@"refresh_token"] : account.refreshToken;
            if (status != 200 || ![token isKindOfClass:NSString.class]) {
                completion(nil, FAOTAuthError(@"Microsoft 登录已过期，请重新登录。"));
                return;
            }
            [self verifyMicrosoftAccessToken:token refreshToken:refresh completion:completion];
        });
        return;
    }

    if (!account.server.length || !account.accessToken.length) {
        completion(nil, FAOTAuthError(@"外置登录信息不完整，请重新登录。"));
        return;
    }
    NSURL *url = [NSURL URLWithString:[account.server stringByAppendingString:@"/authserver/refresh"]];
    NSDictionary *body = @{@"accessToken": account.accessToken,
                           @"clientToken": account.clientToken ?: NSUUID.UUID.UUIDString.lowercaseString};
    FAOTJSONCall(FAOTJSONRequest(url, @"POST", body, nil), ^(NSDictionary *json, NSInteger status, NSError *error) {
        if (error) { completion(nil, error); return; }
        NSString *token = json[@"accessToken"];
        if (status != 200 || ![token isKindOfClass:NSString.class]) {
            completion(nil, FAOTAuthError(@"外置登录已过期，请重新输入密码登录。"));
            return;
        }
        account.accessToken = token;
        if ([json[@"clientToken"] isKindOfClass:NSString.class]) account.clientToken = json[@"clientToken"];
        [self refreshYggdrasilProfileForAccount:account completion:completion];
    });
}

- (void)downloadSkinForAccount:(FAOTAccount *)account completion:(FAOTSkinCompletion)completion {
    if (!account) { completion(nil, FAOTAuthError(@"没有可用账号。")); return; }
    if (account.kind == FAOTAccountKindOffline) {
        completion(nil, FAOTAuthError(@"离线账号没有远程皮肤。"));
        return;
    }
    void (^download)(NSString *) = ^(NSString *url) {
        if (!url.length) {
            completion(nil, FAOTAuthError(@"该账号没有设置皮肤。"));
            return;
        }
        FAOTDownloadImage(url, ^(UIImage *image, NSError *error) {
            if (image) [FAOTAccountStore.shared storeSkinData:UIImagePNGRepresentation(image) forAccount:account];
            completion(image, error);
        });
    };
    if (account.kind == FAOTAccountKindMicrosoft) {
        if (account.skinURL.length) { download(account.skinURL); return; }
        if (!account.accessToken.length) { completion(nil, FAOTAuthError(@"登录已失效。")); return; }
        [self minecraftProfile:account.accessToken completion:^(NSDictionary *profile, NSError *error) {
            if (error) { completion(nil, error); return; }
            NSArray *skins = profile[@"skins"];
            NSString *url = nil;
            if ([skins isKindOfClass:NSArray.class]) {
                for (NSDictionary *skin in skins) {
                    if ([skin isKindOfClass:NSDictionary.class] && [skin[@"url"] isKindOfClass:NSString.class]) {
                        if (!url || [skin[@"state"] isEqual:@"ACTIVE"]) url = skin[@"url"];
                        if ([skin[@"state"] isEqual:@"ACTIVE"]) break;
                    }
                }
            }
            account.skinURL = url;
            download(url);
        }];
        return;
    }
    [self refreshYggdrasilProfileForAccount:account completion:^(FAOTAccount *updated, NSError *error) {
        completion([FAOTAccountStore.shared cachedSkinForAccount:account], error);
    }];
}

@end
