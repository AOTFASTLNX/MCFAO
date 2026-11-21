#ifndef FAOT_GL41_DIAGNOSTICS_H
#define FAOT_GL41_DIAGNOSTICS_H
#import <Foundation/Foundation.h>
#include <errno.h>
#include <stdlib.h>
#include <stdio.h>

/* Parse the entire file before changing any process settings. No arbitrary env keys. */
static inline NSString *FAOTDiagnosticInteger(id value) {
    if (![value isKindOfClass:NSNumber.class] ||
        CFGetTypeID((__bridge CFTypeRef)value) == CFBooleanGetTypeID()) return nil;
    NSString *text = [value stringValue];
    if (!text.length || [text rangeOfCharacterFromSet:
        NSCharacterSet.decimalDigitCharacterSet.invertedSet].location != NSNotFound) return nil;
    errno = 0;
    char *end = NULL;
    (void)strtoull(text.UTF8String, &end, 10);
    if (errno || !end || *end) return nil;
    return text;
}

static inline BOOL FAOTApplyGL41DiagnosticData(NSData *data) {
    id config = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if (![config isKindOfClass:NSDictionary.class]) return NO;
    id enabled = config[@"enabled"];
    if (!enabled || CFGetTypeID((__bridge CFTypeRef)enabled) != CFBooleanGetTypeID()) return NO;
    id fail = config[@"failAllocation"];
    NSString *after = nil, *size = nil, *count = nil;
    if (fail) {
        if (![enabled boolValue] || ![fail isKindOfClass:NSDictionary.class]) return NO;
        after = FAOTDiagnosticInteger(fail[@"after"]);
        size = fail[@"size"] ? FAOTDiagnosticInteger(fail[@"size"]) : @"0";
        count = fail[@"count"] ? FAOTDiagnosticInteger(fail[@"count"]) : @"1";
        if (!after || !size || !count || [count isEqualToString:@"0"]) return NO;
    }
    setenv("FAOT_GL41_DIAGNOSTICS", [enabled boolValue] ? "1" : "0", 1);
    unsetenv("FAOT_VK_FAIL_AFTER"); unsetenv("FAOT_VK_FAIL_SIZE"); unsetenv("FAOT_VK_FAIL_COUNT");
    if (fail) {
        setenv("FAOT_VK_FAIL_SIZE", size.UTF8String, 1);
        setenv("FAOT_VK_FAIL_COUNT", count.UTF8String, 1);
        setenv("FAOT_VK_FAIL_AFTER", after.UTF8String, 1);
    }
    fprintf(stderr, "[GL41-DIAG] config enabled=%d allocationInjection=%d\n", [enabled boolValue], fail != nil);
    return YES;
}

static inline void FAOTLoadGL41Diagnostics(NSString *documents, NSString *resources) {
    NSString *path = [documents stringByAppendingPathComponent:@"gl41-diagnostics.json"];
    if (![NSFileManager.defaultManager fileExistsAtPath:path])
        path = [resources stringByAppendingPathComponent:@"instance-seed/gl41-diagnostics.json"];
    NSData *data = [NSData dataWithContentsOfFile:path];
    if (data && !FAOTApplyGL41DiagnosticData(data))
        fprintf(stderr, "[GL41-DIAG] invalid configuration rejected; no settings applied\n");
}
#endif
