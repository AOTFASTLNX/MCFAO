/* SPDX-License-Identifier: MIT. Real wrappers with deterministic Vulkan dispatch. */
#include <vulkan/vulkan.h>
#include <assert.h>
#include <stdbool.h>
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct zink_screen {
 VkDevice dev;VkPhysicalDevice pdev;
 struct { VkPhysicalDeviceMemoryProperties mem_props; bool have_EXT_memory_budget; } info;
 struct { PFN_vkAllocateMemory AllocateMemory;PFN_vkFreeMemory FreeMemory;
 PFN_vkCreateBuffer CreateBuffer;PFN_vkDestroyBuffer DestroyBuffer;
 PFN_vkCreateImage CreateImage;PFN_vkDestroyImage DestroyImage;
 PFN_vkBindBufferMemory BindBufferMemory;PFN_vkBindImageMemory BindImageMemory;
 PFN_vkMapMemory MapMemory;PFN_vkGetPhysicalDeviceMemoryProperties2 GetPhysicalDeviceMemoryProperties2;
 PFN_vkGetImageMemoryRequirements GetImageMemoryRequirements;
 PFN_vkCreateFramebuffer CreateFramebuffer;PFN_vkDestroyFramebuffer DestroyFramebuffer; } vk;
};
#include "../../compiler/gl41/patches/ncl_diag_impl.h"
static unsigned allocate_calls,budget_calls;
static bool driver_failure;
static VkResult alloc(VkDevice d,const VkMemoryAllocateInfo *a,const VkAllocationCallbacks *c,VkDeviceMemory *out){
 (void)d;(void)a;(void)c;allocate_calls++;*out=(VkDeviceMemory)(uintptr_t)(0x1000+allocate_calls*16);
 return driver_failure?VK_ERROR_OUT_OF_DEVICE_MEMORY:VK_SUCCESS;
}
static void free_mem(VkDevice d,VkDeviceMemory m,const VkAllocationCallbacks *c){(void)d;(void)m;(void)c;}
static VkResult create_buf(VkDevice d,const VkBufferCreateInfo *a,const VkAllocationCallbacks *c,VkBuffer *out){
 (void)d;(void)a;(void)c;*out=(VkBuffer)(uintptr_t)0x5000;return driver_failure?VK_ERROR_OUT_OF_DEVICE_MEMORY:VK_SUCCESS;
}
static void destroy_buf(VkDevice d,VkBuffer m,const VkAllocationCallbacks *c){(void)d;(void)m;(void)c;}
static VkResult create_img(VkDevice d,const VkImageCreateInfo *a,const VkAllocationCallbacks *c,VkImage *out){
 (void)d;(void)a;(void)c;*out=(VkImage)(uintptr_t)0x6000;return driver_failure?VK_ERROR_OUT_OF_DEVICE_MEMORY:VK_SUCCESS;
}
static void destroy_img(VkDevice d,VkImage m,const VkAllocationCallbacks *c){(void)d;(void)m;(void)c;}
static VkResult create_fb(VkDevice d,const VkFramebufferCreateInfo *a,const VkAllocationCallbacks *c,VkFramebuffer *out){
 (void)d;(void)a;(void)c;*out=(VkFramebuffer)(uintptr_t)0x7000;return driver_failure?VK_ERROR_OUT_OF_DEVICE_MEMORY:VK_SUCCESS;
}
static void destroy_fb(VkDevice d,VkFramebuffer m,const VkAllocationCallbacks *c){(void)d;(void)m;(void)c;}
static VkResult bind_buf(VkDevice d,VkBuffer b,VkDeviceMemory m,VkDeviceSize o){(void)d;(void)b;(void)m;(void)o;return VK_ERROR_OUT_OF_DEVICE_MEMORY;}
static VkResult bind_img(VkDevice d,VkImage b,VkDeviceMemory m,VkDeviceSize o){(void)d;(void)b;(void)m;(void)o;return VK_ERROR_OUT_OF_DEVICE_MEMORY;}
static VkResult map_mem(VkDevice d,VkDeviceMemory m,VkDeviceSize o,VkDeviceSize n,VkMemoryMapFlags f,void **p){
 (void)d;(void)m;(void)o;(void)n;(void)f;*p=(void *)1;return VK_ERROR_MEMORY_MAP_FAILED;
}
static void requirements(VkDevice d,VkImage i,VkMemoryRequirements *r){(void)d;(void)i;r->size=8192;}
static void budget(VkPhysicalDevice d,VkPhysicalDeviceMemoryProperties2 *p){
 (void)d;budget_calls++;p->memoryProperties.memoryHeapCount=1;
 VkPhysicalDeviceMemoryBudgetPropertiesEXT *b=p->pNext;b->heapBudget[0]=123456789;b->heapUsage[0]=4096;
}
int main(int argc,char **argv){
 assert(argc==2);
 struct zink_screen s={0};
 s.vk.AllocateMemory=alloc;s.vk.FreeMemory=free_mem;s.vk.CreateBuffer=create_buf;s.vk.DestroyBuffer=destroy_buf;
 s.vk.CreateImage=create_img;s.vk.DestroyImage=destroy_img;s.vk.CreateFramebuffer=create_fb;s.vk.DestroyFramebuffer=destroy_fb;
 s.vk.BindBufferMemory=bind_buf;s.vk.BindImageMemory=bind_img;s.vk.MapMemory=map_mem;
 s.vk.GetImageMemoryRequirements=requirements;s.vk.GetPhysicalDeviceMemoryProperties2=budget;
 s.info.have_EXT_memory_budget=true;s.info.mem_props.memoryTypeCount=1;s.info.mem_props.memoryHeapCount=1;
 s.info.mem_props.memoryHeaps[0].size=999999999;s.info.mem_props.memoryTypes[0].propertyFlags=VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT;
 VkMemoryAllocateInfo a={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,.allocationSize=13794176,.memoryTypeIndex=0};
 VkDeviceMemory memory;
 for(unsigned i=0;i<4;i++){
  memory=(VkDeviceMemory)(uintptr_t)1;
  VkResult r=ncl_allocate_memory(&s,&a,NULL,&memory,"fixture",100+i);
  bool failure=(!strcmp(argv[1],"once")&&i==0)||(!strcmp(argv[1],"persistent"))||(!strcmp(argv[1],"after")&&(i==2||i==3));
  assert((r!=VK_SUCCESS)==failure);
  if(failure)assert(!memory);else {assert(memory);ncl_FreeMemory(&s,memory,NULL);}
 }
 assert(allocate_calls==(!strcmp(argv[1],"once")?3:!strcmp(argv[1],"persistent")?0:!strcmp(argv[1],"after")?2:4));
 a.allocationSize=64;assert(ncl_allocate_memory(&s,&a,NULL,&memory,"filter",1)==VK_SUCCESS);ncl_FreeMemory(&s,memory,NULL);
 driver_failure=true;
 assert(ncl_allocate_memory(&s,&a,NULL,&memory,"driver",2)!=VK_SUCCESS&&!memory);
 VkBuffer buffer;VkBufferCreateInfo b={.size=32};
 assert(ncl_create_buffer(&s,&b,NULL,&buffer,"buffer",3)!=VK_SUCCESS&&!buffer);
 VkImage image;VkImageCreateInfo im={0};
 assert(ncl_create_image(&s,&im,NULL,&image,"image",4)!=VK_SUCCESS&&!image);
 VkFramebuffer fb;VkFramebufferCreateInfo f={0};
 assert(ncl_create_framebuffer(&s,&f,NULL,&fb,"framebuffer",5)!=VK_SUCCESS&&!fb);
 void *mapped=(void *)1;assert(ncl_MapMemory(&s,memory,0,64,0,&mapped)!=VK_SUCCESS&&!mapped);
 assert(ncl_BindBufferMemory(&s,VK_NULL_HANDLE,VK_NULL_HANDLE,0)!=VK_SUCCESS);
 assert(ncl_BindImageMemory(&s,VK_NULL_HANDLE,VK_NULL_HANDLE,0)!=VK_SUCCESS);
 driver_failure=false;
 assert(ncl_create_buffer(&s,&b,NULL,&buffer,"buffer",6)==VK_SUCCESS);
 assert(ncl_create_image(&s,&im,NULL,&image,"image",7)==VK_SUCCESS);
 assert(ncl_create_framebuffer(&s,&f,NULL,&fb,"framebuffer",8)==VK_SUCCESS);
 if(ncl_enabled){assert(ncl_live_bytes[NCL_IMAGE]==8192);assert(ncl_live_bytes[NCL_BUFFER]==32);}
 ncl_DestroyBuffer(&s,buffer,NULL);ncl_DestroyImage(&s,image,NULL);ncl_DestroyFramebuffer(&s,fb,NULL);
 if(ncl_enabled){
  for(unsigned i=0;i<NCL_KINDS;i++)assert(ncl_created[i]==ncl_destroyed[i]&&!ncl_live_bytes[i]);
  ncl_add(&s,NCL_MEMORY,0x100,11,0,"collision",1);ncl_add(&s,NCL_MEMORY,0x100+16*NCL_RECORDS,22,0,"collision",2);
  ncl_del(&s,NCL_MEMORY,0x100);ncl_del(&s,NCL_MEMORY,0x100+16*NCL_RECORDS);assert(!ncl_live_bytes[NCL_MEMORY]);
 }
 ncl_diag_frame();assert(budget_calls);puts("ZINK_DIAGNOSTICS_PASS");return 0;
}
