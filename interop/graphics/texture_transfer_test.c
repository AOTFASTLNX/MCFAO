#include "texture_transfer.h"
#include <assert.h>
#include <stdio.h>
int main(void){
    const uint8_t input[]={17,33,65,99,111,127,151,199};uint8_t output[8];
    for(int components=1;components<=4;components++){
        assert(faot_expand_rgba(output,input,2,components));
        for(int pixel=0;pixel<2;pixel++){
            assert(output[pixel*4]==input[pixel*components]);
            assert(output[pixel*4+1]==(components>=2?input[pixel*components+1]:0));
            assert(output[pixel*4+2]==(components>=3?input[pixel*components+2]:0));
            assert(output[pixel*4+3]==(components==4?input[pixel*components+3]:255));
        }
    }
    assert(!faot_expand_rgba(output,input,2,0));assert(!faot_expand_rgba(output,input,SIZE_MAX,4));
    puts("METAL_PIXEL_LAYOUT_PASS");return 0;
}
