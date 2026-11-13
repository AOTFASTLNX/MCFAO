#ifndef FAOT_PERF_WINDOW_H
#define FAOT_PERF_WINDOW_H
#include <math.h>
#include <stddef.h>
#include <stdlib.h>

enum { FAOT_PERF_WINDOW_SIZE=300 };
typedef struct { double last, intervals[FAOT_PERF_WINDOW_SIZE], sum; unsigned count, invalid; } FAOTPerfWindow;
typedef struct { double mean, p95, p99; unsigned intervals, invalid; } FAOTPerfSummary;
static inline int faot_perf_compare(const void *a,const void *b) {
    double x=*(const double *)a,y=*(const double *)b;
    return (x>y)-(x<y);
}
/* Caller owns synchronization. Times are monotonic host seconds; 0 is unavailable. */
static inline int faot_perf_present(FAOTPerfWindow *window,double time,FAOTPerfSummary *out) {
    if(!isfinite(time)||time<=0||(window->last>0&&time<=window->last)){window->invalid++;return 0;}
    if(window->last>0){double value=time-window->last;window->intervals[window->count++]=value;window->sum+=value;}
    window->last=time;
    if(window->count<FAOT_PERF_WINDOW_SIZE)return 0;
    qsort(window->intervals,window->count,sizeof(double),faot_perf_compare);
    *out=(FAOTPerfSummary){window->sum/window->count,window->intervals[284],window->intervals[296],window->count,window->invalid};
    window->count=0;window->sum=0;window->invalid=0;
    return 1;
}
#endif
