"""Generate fixed C JNI adapters from the pinned LWJGL base class descriptors.

No libffi, executable allocation, assembly emission, or runtime function generation.
Only GLFW/core primitive JNI invocations are admitted; unsupported descriptors fail the build.
"""
from __future__ import annotations
import re

CALLBACKS=[
    ("Error","IJ"),("Monitor","JI"),("WindowPos","JII"),("WindowSize","JII"),
    ("FramebufferSize","JII"),("WindowClose","J"),("WindowFocus","JZ"),
    ("WindowIconify","JZ"),("CursorEnter","JZ"),("Key","JIIII"),("Char","JI"),
    ("MouseButton","JIII"),("CursorPos","JDD"),("Scroll","JDD"),("Drop","JIJ"),
    ("IMEStatus","J"),("Preedit","JIJIJII"),("STBIWrite","JJI")]
JTYPES={"V":"void","Z":"jboolean","B":"jbyte","C":"jchar","S":"jshort",
        "I":"jint","J":"jlong","F":"jfloat","D":"jdouble"}
CTYPES={"V":"void","Z":"uint8_t","B":"int8_t","C":"uint16_t","S":"int16_t",
        "I":"int32_t","J":"uintptr_t","F":"float","D":"double"}
ARRAYS={"Z":"Boolean","B":"Byte","C":"Char","S":"Short","I":"Int","J":"Long","F":"Float","D":"Double"}

def mangle(value: str)->str:
    return ''.join({'_':'_1',';':'_2','[':'_3','/':'_'}.get(c,c if c.isascii() and c.isalnum() else '_0%04x'%ord(c)) for c in value)

def descriptor(value: str)->tuple[list[str],str]:
    if not re.fullmatch(r'\((?:[ZBCSIJFD]|\[[ZBCSIJFD])*\)[VZBCSIJFD]',value):
        raise ValueError('Unsupported primitive JNI descriptor: '+value)
    args,ret=value[1:].split(')')
    return re.findall(r'\[?[ZBCSIJFD]',args),ret

def parse_natives(javap: str)->list[tuple[str,str]]:
    return re.findall(r'\bnative\s+\S+\s+(\w+)\([^\n]*\);\s+descriptor:\s*(\S+)',javap)

def generate_jni(methods: list[tuple[str,str]])->str:
    lines=['/* Generated from verified LWJGL JNI.class descriptors, not runtime codegen. */',
           '#include <jni.h>','#include <stdint.h>']
    for name,desc in methods:
        if not name.startswith(('invoke','call')): raise ValueError('Unexpected JNI entry: '+name)
        args,ret=descriptor(desc)
        if not args or args[-1]!='J':raise ValueError('Function pointer must be the final long: '+desc)
        declaration=[];converted=[];native_types=[];release=[]
        for i,t in enumerate(args):
            if t.startswith('['):
                base=t[1];declaration.append(f'{JTYPES[base]}Array a{i}')
                lines_arg=f'{JTYPES[base]} *p{i}=a{i}?(*e)->Get{ARRAYS[base]}ArrayElements(e,a{i},NULL):NULL;'
                converted.append((lines_arg,f'({CTYPES[base]} *)p{i}'))
                release.append(f'if(a{i}&&p{i})(*e)->Release{ARRAYS[base]}ArrayElements(e,a{i},p{i},0);')
                native_types.append(CTYPES[base]+' *')
            else:
                declaration.append(f'{JTYPES[t]} a{i}')
                converted.append(('',f'({CTYPES[t]})a{i}'))
                native_types.append(CTYPES[t])
        symbol='Java_org_lwjgl_system_JNI_'+mangle(name)+'__'+mangle(desc[1:desc.index(')')])
        lines.append(f'JNIEXPORT {JTYPES[ret]} JNICALL {symbol}(JNIEnv *e,jclass cls,'+','.join(declaration)+'){')
        lines.append('(void)e;(void)cls;')
        lines.append(f'if(!a{len(args)-1})'+'{jclass error=(*e)->FindClass(e,"java/lang/UnsatisfiedLinkError");if(error)(*e)->ThrowNew(e,error,"Missing native function pointer: '+name+desc+'");'+('return;' if ret=='V' else 'return 0;')+'}')
        for statement,_ in converted:
            if statement:lines.append(statement)
        # Pinning failures must not call a native function with null pointers in place of arrays.
        for i,t in enumerate(args):
            if t.startswith('['):
                lines.append(f'if(a{i}&&!p{i}){{'+''.join(release[:sum(a.startswith('[') for a in args[:i])])+('return;' if ret=='V' else 'return 0;')+'}')
        call=f'(({CTYPES[ret]} (*)('+(','.join(native_types[:-1]) or 'void')+f'))(uintptr_t)a{len(args)-1})('+','.join(v for _,v in converted[:-1])+')'
        lines.append(call+';' if ret=='V' else f'{CTYPES[ret]} result={call};')
        lines.extend(release)
        if ret!='V':lines.append(f'return ({JTYPES[ret]})result;')
        lines.append('}')
    return '\n'.join(lines)+'\n'

def generate_callbacks(slots: int=32)->str:
    if not 1<=slots<=64:raise ValueError('Static bank must contain 1..64 slots per ABI')
    lines=['/* Precompiled callback bank. No executable memory is allocated at runtime. */',
           '#include <jni.h>','#include <stdint.h>','#include <pthread.h>','#include <stdio.h>',
           f'#define KINDS {len(CALLBACKS)}',f'#define SLOTS {slots}',
           'typedef struct {jobject object;jmethodID method;} Slot;',
           'static Slot bank[KINDS][SLOTS];static JavaVM *vm;static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;',
           'JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *v,void *r){(void)r;vm=v;return JNI_VERSION_1_8;}',
           'static void invoke(int kind,int slot,jvalue *args){',
           'JNIEnv *e=NULL;if(!vm||(*vm)->GetEnv(vm,(void **)&e,JNI_VERSION_1_8)!=JNI_OK){fprintf(stderr,"[LWJGL-lite] callback on unattached thread\\n");return;}',
           'pthread_mutex_lock(&lock);jobject o=bank[kind][slot].object?(*e)->NewLocalRef(e,bank[kind][slot].object):NULL;jmethodID m=bank[kind][slot].method;pthread_mutex_unlock(&lock);',
           'if(!o){fprintf(stderr,"[LWJGL-lite] stale callback\\n");return;}if(!(*e)->ExceptionCheck(e))(*e)->CallVoidMethodA(e,o,m,args);(*e)->DeleteLocalRef(e,o);}',
           'static void error(JNIEnv *e,const char *s){jclass c=(*e)->FindClass(e,"java/lang/IllegalStateException");if(c)(*e)->ThrowNew(e,c,s);}']
    for kind,(name,args) in enumerate(CALLBACKS):
        for slot in range(slots):
            params=','.join(f'{CTYPES[t]} a{i}' for i,t in enumerate(args))
            values=','.join('{.'+t.lower()+f'=({JTYPES[t]})a{i}'+'}' for i,t in enumerate(args))
            lines.append(f'static void cb_{kind}_{slot}({params})'+'{jvalue values[]={'+values+'};'+f'invoke({kind},{slot},values);'+'}')
    lines.append('static void *functions[KINDS][SLOTS]={')
    for kind in range(len(CALLBACKS)):lines.append('{'+','.join(f'(void *)cb_{kind}_{slot}' for slot in range(slots))+'},')
    lines.append('};')
    lines.append('static const char *classes[]={'+','.join('"org/lwjgl/stb/STBIWriteCallbackI"' if name=="STBIWrite" else '"org/lwjgl/glfw/GLFW'+name+'CallbackI"' for name,_ in CALLBACKS)+'};')
    lines.append('static const char *signatures[]={'+','.join('"('+args+')V"' for _,args in CALLBACKS)+'};')
    lines += [
        'JNIEXPORT jlong JNICALL Java_org_lwjgl_system_IOSNative_callbackCreate(JNIEnv *e,jclass cls,jobject o,jint kind){(void)cls;',
        'if(kind<0||kind>=KINDS||!o){error(e,"Unregistered callback ABI");return 0;}',
        'jclass c=(*e)->FindClass(e,classes[kind]);if(!c)return 0;jmethodID m=(*e)->GetMethodID(e,c,"invoke",signatures[kind]);(*e)->DeleteLocalRef(e,c);if(!m)return 0;',
        'pthread_mutex_lock(&lock);for(int s=0;s<SLOTS;s++)if(!bank[kind][s].object){jobject ref=(*e)->NewGlobalRef(e,o);if(!ref){pthread_mutex_unlock(&lock);return 0;}bank[kind][s]=(Slot){ref,m};pthread_mutex_unlock(&lock);return (jlong)(uintptr_t)functions[kind][s];}pthread_mutex_unlock(&lock);error(e,"Static iOS callback bank exhausted (32 slots per ABI)");return 0;}',
        'JNIEXPORT jobject JNICALL Java_org_lwjgl_system_IOSNative_callbackGet(JNIEnv *e,jclass c,jlong p){(void)c;',
        'pthread_mutex_lock(&lock);for(int k=0;k<KINDS;k++)for(int s=0;s<SLOTS;s++)if((uintptr_t)functions[k][s]==(uintptr_t)p){jobject o=bank[k][s].object?(*e)->NewLocalRef(e,bank[k][s].object):NULL;pthread_mutex_unlock(&lock);return o;}pthread_mutex_unlock(&lock);error(e,"Unknown static callback address");return NULL;}',
        'JNIEXPORT void JNICALL Java_org_lwjgl_system_IOSNative_callbackFree(JNIEnv *e,jclass c,jlong p){(void)c;',
        'pthread_mutex_lock(&lock);for(int k=0;k<KINDS;k++)for(int s=0;s<SLOTS;s++)if((uintptr_t)functions[k][s]==(uintptr_t)p){jobject o=bank[k][s].object;bank[k][s]=(Slot){0};pthread_mutex_unlock(&lock);if(o)(*e)->DeleteGlobalRef(e,o);return;}pthread_mutex_unlock(&lock);error(e,"Unknown static callback address");}',
    ]
    return '\n'.join(lines)+'\n'
