#ifndef FAOT_POINTER_MOTION_H
#define FAOT_POINTER_MOTION_H

/* Convert consecutive unlocked hover locations into relative game movement.
 * The first location after a transition establishes a baseline, avoiding jumps. */
typedef struct { double x, y; int valid; } FAOTPointerMotion;
static inline void faot_pointer_reset(FAOTPointerMotion *motion) { motion->valid=0; }
static inline int faot_pointer_hover_delta(FAOTPointerMotion *motion, double x, double y, double *dx, double *dy) {
    int valid=motion->valid;
    *dx=valid?x-motion->x:0;
    *dy=valid?y-motion->y:0;
    motion->x=x; motion->y=y; motion->valid=1;
    return valid && (*dx!=0 || *dy!=0);
}
#endif
