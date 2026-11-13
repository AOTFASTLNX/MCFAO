#include "perf_window.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

int main(void) {
    FAOTPerfWindow w={0};FAOTPerfSummary s={0};
    assert(!faot_perf_present(&w,0,&s));
    assert(!faot_perf_present(&w,100,&s));
    assert(!faot_perf_present(&w,100,&s));
    double time=100;
    for(int i=1;i<=300;i++){
        time+=(double)i/1000;
        int complete=faot_perf_present(&w,time,&s);
        assert(complete==(i==300));
    }
    assert(s.intervals==300&&s.invalid==2);
    assert(fabs(s.mean-.1505)<1e-9&&fabs(s.p95-.285)<1e-9&&fabs(s.p99-.297)<1e-9);
    assert(!faot_perf_present(&w,time+.01,&s)&&w.count==1);
    puts("PERF_WINDOW_PASS");return 0;
}
