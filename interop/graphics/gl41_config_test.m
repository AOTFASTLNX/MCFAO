#import "../../ios/C0Harness/gl41_diagnostics.h"
#include <assert.h>
static BOOL apply(NSString *s){return FAOTApplyGL41DiagnosticData([s dataUsingEncoding:NSUTF8StringEncoding]);}
int main(void){@autoreleasepool {
 assert(apply(@"{\"enabled\":true}"));assert(!strcmp(getenv("FAOT_GL41_DIAGNOSTICS"),"1"));
 assert(apply(@"{\"enabled\":true,\"failAllocation\":{\"after\":0,\"size\":13794176,\"count\":18446744073709551615}}"));
 assert(!strcmp(getenv("FAOT_VK_FAIL_SIZE"),"13794176"));
 for(NSString *bad in @[@"[]",@"{\"enabled\":1}",@"{\"enabled\":true,\"failAllocation\":{\"after\":-1}}",
   @"{\"enabled\":true,\"failAllocation\":{\"after\":false}}",@"{\"enabled\":true,\"failAllocation\":{\"after\":1.5}}",
   @"{\"enabled\":true,\"failAllocation\":{\"after\":0,\"count\":0}}",@"{\"enabled\":false,\"failAllocation\":{\"after\":0}}"]){
  assert(!apply(bad));assert(!strcmp(getenv("FAOT_VK_FAIL_SIZE"),"13794176"));
 }
 assert(apply(@"{\"enabled\":false}"));assert(!getenv("FAOT_VK_FAIL_AFTER"));
 puts("GL41_CONFIG_PASS");return 0;
}}
