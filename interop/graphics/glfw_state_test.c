/* First-party host fixture only. Not an iOS surface or Minecraft acceptance test. */
#include "glfw_lite.h"
#include "input_mapping.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int sizes, pixels, focused, chars, destroyed;
static GLFWwindow *window;
static int keyDown,keyUp;static double cursorX,cursorY;
static void key(GLFWwindow *w,int k,int scan,int action,int mods){(void)scan;(void)mods;assert(w==window&&k=='W');if(action)keyDown++;else keyUp++;}
static void cursor(GLFWwindow *w,double x,double y){assert(w==window);cursorX=x;cursorY=y;}
void *faot_surface_create(GLFWwindow *w,int *a,int *b,int *c,int *d){(void)w;*a=390;*b=844;*c=1170;*d=2532;return malloc(1);}
void faot_surface_destroy(void *p){free(p);destroyed++;}
void faot_surface_screen(GLFWvidmode *m){*m=(GLFWvidmode){390,844,8,8,8,120};}
void faot_surface_input(void *p,int a,int b){(void)p;(void)a;(void)b;}
void faot_surface_ime_rect(void *p,int a,int b,int c,int d){(void)p;(void)a;(void)b;(void)c;(void)d;}
void faot_surface_title(void *p,const char *s){(void)p;(void)s;}
void *faot_surface_layer(void *p){return p;}
void faot_surface_clipboard_set(const char *s){(void)s;}
char *faot_surface_clipboard_copy(void){return strdup("fixture");}
static void size(GLFWwindow *w,int a,int b){assert(w==window&&a==390&&b==844);sizes++;}
static void framebuffer(GLFWwindow *w,int a,int b){assert(w==window&&a==1170&&b==2532);pixels++;}
static void focus(GLFWwindow *w,int f){assert(w==window&&f==1);focused++;}
static void character(GLFWwindow *w,unsigned int c){assert(w==window&&c==0x1f600);chars++;}
static void destroyOnResize(GLFWwindow *w,int a,int b){(void)a;(void)b;glfwDestroyWindow(w);}
int main(void){
    assert(!glfwCreateWindow(1,1,"test",NULL,NULL));
    const char *error;assert(glfwGetError(&error)==GLFW_NOT_INITIALIZED&&error);
    assert(glfwGetError(&error)==0&&error==NULL);
    assert(glfwInit());
    assert(!glfwCreateWindow(1,1,"GL is unsupported",NULL,NULL));
    assert(glfwGetError(NULL)==GLFW_API_UNAVAILABLE);
    glfwWindowHint(GLFW_CLIENT_API,GLFW_NO_API);
    window=glfwCreateWindow(100,100,"fixture",NULL,NULL);assert(window);
    assert(glfwSetWindowSizeCallback(window,size)==NULL);
    glfwSetFramebufferSizeCallback(window,framebuffer);glfwSetWindowFocusCallback(window,focus);
    glfwSetCharCallback(window,character);
    assert(faot_glfw_enqueue(window,FAOT_EVENT_CHAR,0x1f600,0,0,0));
    glfwPollEvents();assert(sizes==1&&pixels==1&&focused==1&&chars==1);
    glfwPollEvents();assert(sizes==1&&chars==1); /* No invented recurring events. */
    int a=0,b=0;glfwGetFramebufferSize(window,&a,&b);assert(a==1170&&b==2532);
    glfwMakeContextCurrent(window);assert(glfwGetCurrentContext()==window);
    GLFWmonitor *m=glfwGetPrimaryMonitor();assert(m);
    glfwSetWindowMonitor(window,m,0,0,1,1,60);assert(glfwGetWindowMonitor(window)==m);
    glfwSetWindowMonitor(window,NULL,0,0,1,1,60);assert(glfwGetWindowMonitor(window)==NULL);
    assert(glfwGetTime()>=0);assert(glfwGetTimerValue()>0);
    assert(glfwGetPlatform()==FAOT_GLFW_PLATFORM_IOS);
    assert(faot_glfw_key_from_hid(0x1a)=='W'&&faot_glfw_key_from_hid(0x29)==256&&faot_glfw_key_from_hid(0xffff)==-1);
    glfwSetKeyCallback(window,key);glfwSetCursorPosCallback(window,cursor);glfwSetWindowFocusCallback(window,NULL);
    glfwSetCursorPos(window,20,30);faot_glfw_enqueue(window,FAOT_EVENT_CURSOR_DELTA,4,-6,0,0);glfwPollEvents();
    assert(cursorX==20&&cursorY==30); /* A menu never consumes captured movement. */
    glfwSetInputMode(window,GLFW_CURSOR,GLFW_CURSOR_DISABLED);
    faot_glfw_enqueue(window,FAOT_EVENT_CURSOR_DELTA,4,-6,0,0);
    faot_glfw_enqueue(window,FAOT_EVENT_KEY,'W',0x1a,1,0);glfwPollEvents();
    assert(cursorX==24&&cursorY==24&&glfwGetKey(window,'W')&&keyDown==1);
    faot_glfw_enqueue(window,FAOT_EVENT_FOCUS,0,0,0,0);glfwPollEvents();
    assert(!glfwGetKey(window,'W')&&keyUp==1);
    glfwSetWindowSizeCallback(window,destroyOnResize);
    faot_glfw_enqueue(window,FAOT_EVENT_RESIZE,0,0,0,0);glfwPollEvents();
    assert(destroyed==1&&glfwGetCurrentContext()==NULL);
    assert(!faot_glfw_enqueue(window,FAOT_EVENT_CHAR,65,0,0,0));
    glfwTerminate();assert(!glfwGetPrimaryMonitor());
    puts("GLFW_STATE_PASS");return 0;
}
