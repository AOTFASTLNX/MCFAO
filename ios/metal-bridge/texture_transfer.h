#ifndef FAOT_TEXTURE_TRANSFER_H
#define FAOT_TEXTURE_TRANSFER_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
/* Minecraft GlConst maps 1/2/3/4 components to GL_RED/RG/RGB/RGBA.
   Missing green/blue channels are zero and missing alpha is one. */
static inline int faot_expand_rgba(uint8_t *destination,const uint8_t *source,size_t count,int components){
    if(components<1||components>4||count>SIZE_MAX/4)return 0;
    if(components==4){memcpy(destination,source,count*4);return 1;}
    for(size_t i=0;i<count;i++){
        const uint8_t *s=source+i*(size_t)components;uint8_t *d=destination+i*4;
        d[0]=s[0];d[1]=components>=2?s[1]:0;d[2]=components>=3?s[2]:0;d[3]=255;
    }
    return 1;
}
#endif
