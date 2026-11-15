#ifndef FAOT_OSMESA_GL_H
#define FAOT_OSMESA_GL_H

/* OSMesa context ownership for the OpenGL 4.1 renderer. The context is created lazily on
 * the first MakeCurrent call, which is the render thread, and the CPU frame is presented by
 * the existing UIKit surface. */
int faot_gl41_make_current(void *surface, int width, int height);
void faot_gl41_swap(void *surface);
void faot_gl41_release(void);

#endif
