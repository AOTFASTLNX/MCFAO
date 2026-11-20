#ifndef FAOT_TEST_VERSION_H
#define FAOT_TEST_VERSION_H
#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
static inline NSString *FAOTTestVersionFromInfo(NSDictionary *info) {
    id value = info[@"FAOTTestVersion"];
    if (![value isKindOfClass:NSString.class]) return @"";
    NSString *label = [value stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (label.length && [label rangeOfString:@"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$" options:NSRegularExpressionSearch].location == NSNotFound) return @"";
    return label;
}
static inline NSString *FAOTCurrentTestVersion(void) {
    return FAOTTestVersionFromInfo(NSBundle.mainBundle.infoDictionary ?: @{});
}
static inline NSString *FAOTTestVersionSubtitle(NSString *label) {
    NSString *base = @"你的方块世界，随身出发。\nMinecraft Java 26.1.2 · Fabric";
    return label.length ? [base stringByAppendingFormat:@"\n测试版本：%@", label] : base;
}
static inline NSString *FAOTTestVersionLogName(NSString *label, double milliseconds) {
    return label.length ? [NSString stringWithFormat:@"run-%.0f-%@.log", milliseconds, label]
                        : [NSString stringWithFormat:@"run-%.0f.log", milliseconds];
}
NS_ASSUME_NONNULL_END
#endif
