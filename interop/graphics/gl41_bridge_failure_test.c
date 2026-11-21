/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include "../../ios/glfw-lite/osmesa_gl.c"
static void *bound;
static int bind_fails,sticky,finish_fails,presents,destroys;
static unsigned char make(void *ctx,void *pixels,int type,int w,int h) {
 (void)type;(void)w;(void)h;
 if(bound) { volatile unsigned char old=*(unsigned char *)bound; (void)old; }
 if(!ctx){bound=NULL;return 1;}
 bound=pixels;return !bind_fails;
}
static unsigned error(void *ctx){(void)ctx;return (unsigned)sticky;}
static void destroy(void *ctx){assert(ctx);if(bound){volatile unsigned char v=*(unsigned char *)bound;(void)v;}bound=NULL;destroys++;}
static void pixel_store(int a,int b){(void)a;(void)b;}
static void finish(void){if(finish_fails)sticky=1;}
int faot_surface_present_bgra(void *s,const void *p,int w,int h){(void)s;assert(p&&w&&h);presents++;return 1;}
static void setup(void){
 api=(OSMesaAPI){.make_current=make,.destroy=destroy,.pixel_store=pixel_store,.finish=finish,.readback_error=error};
 attempted=api_ready=qos_set=1;context=(void *)1;bind_fails=sticky=finish_fails=0;
 assert(faot_gl41_make_current((void *)2,4,4));
}
static void *other_thread(void *allowed){
 assert(faot_gl41_make_current((void *)2,4,4)==(allowed!=NULL));
 if(!allowed){assert(!faot_gl41_release());assert(context&&frame);}
 if(allowed)assert(faot_gl41_detach());
 return NULL;
}
int main(void){
 setup();void *old=frame;assert(faot_gl41_make_current((void *)2,8,8));assert(frame!=old);
 assert(faot_gl41_swap(NULL)&&presents==1);
 finish_fails=1;assert(!faot_gl41_swap(NULL)&&render_failed&&presents==1);
 assert(!faot_gl41_swap(NULL)&&presents==1);faot_gl41_release();
 setup();old=frame;bind_fails=1;assert(!faot_gl41_make_current((void *)2,8,8));
 assert(frame==old&&failed_frame&&bound==failed_frame&&render_failed);
 faot_gl41_release();assert(!frame&&!failed_frame);
 setup();pthread_t t;assert(!pthread_create(&t,NULL,other_thread,NULL));pthread_join(t,NULL);
 assert(faot_gl41_detach());assert(!pthread_create(&t,NULL,other_thread,(void *)1));pthread_join(t,NULL);
 assert(faot_gl41_make_current((void *)2,4,4));faot_gl41_release();
 setup();assert(faot_gl41_detach());bind_fails=1;
 assert(!faot_gl41_make_current((void *)2,4,4)&&owner_set);
 assert(!pthread_create(&t,NULL,other_thread,NULL));pthread_join(t,NULL);
 assert(faot_gl41_release());
 assert(destroys==4);puts("GL41_BRIDGE_FAILURE_PATHS_PASS");return 0;
}
