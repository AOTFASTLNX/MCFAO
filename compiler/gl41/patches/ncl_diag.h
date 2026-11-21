/* SPDX-License-Identifier: MIT */
#ifndef NCL_ZINK_DIAG_H
#define NCL_ZINK_DIAG_H
#include "zink_screen.h"

VkResult ncl_allocate_memory(struct zink_screen *, const VkMemoryAllocateInfo *, const VkAllocationCallbacks *, VkDeviceMemory *, const char *, unsigned);
void ncl_FreeMemory(struct zink_screen *, VkDeviceMemory, const VkAllocationCallbacks *);
VkResult ncl_create_buffer(struct zink_screen *, const VkBufferCreateInfo *, const VkAllocationCallbacks *, VkBuffer *, const char *, unsigned);
void ncl_DestroyBuffer(struct zink_screen *, VkBuffer, const VkAllocationCallbacks *);
VkResult ncl_create_image(struct zink_screen *, const VkImageCreateInfo *, const VkAllocationCallbacks *, VkImage *, const char *, unsigned);
void ncl_DestroyImage(struct zink_screen *, VkImage, const VkAllocationCallbacks *);
VkResult ncl_BindBufferMemory(struct zink_screen *, VkBuffer, VkDeviceMemory, VkDeviceSize);
VkResult ncl_BindImageMemory(struct zink_screen *, VkImage, VkDeviceMemory, VkDeviceSize);
VkResult ncl_MapMemory(struct zink_screen *, VkDeviceMemory, VkDeviceSize, VkDeviceSize, VkMemoryMapFlags, void **);
void ncl_diag_frame(void);
VkResult ncl_create_framebuffer(struct zink_screen *, const VkFramebufferCreateInfo *, const VkAllocationCallbacks *, VkFramebuffer *, const char *, unsigned);
void ncl_DestroyFramebuffer(struct zink_screen *, VkFramebuffer, const VkAllocationCallbacks *);
#define ncl_CreateFramebuffer(s, a, c, o) ncl_create_framebuffer(s, a, c, o, __func__, __LINE__)
#define ncl_AllocateMemory(s, a, c, o) ncl_allocate_memory(s, a, c, o, __func__, __LINE__)
#define ncl_CreateBuffer(s, a, c, o) ncl_create_buffer(s, a, c, o, __func__, __LINE__)
#define ncl_CreateImage(s, a, c, o) ncl_create_image(s, a, c, o, __func__, __LINE__)
#endif
