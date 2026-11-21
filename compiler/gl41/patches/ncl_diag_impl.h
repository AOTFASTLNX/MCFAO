/* SPDX-License-Identifier: MIT
 * Included once by zink_bo.c. Tracking is opt-in, fixed-capacity, and never
 * allocates host memory inside Vulkan allocation hooks. */
#include <pthread.h>
#include <time.h>
#ifdef __APPLE__
#include <mach/mach.h>
#endif

enum { NCL_MEMORY, NCL_BUFFER, NCL_IMAGE, NCL_FRAMEBUFFER, NCL_KINDS, NCL_RECORDS = 32768 };
struct ncl_record {
   struct zink_screen *screen;
   uint64_t handle, bytes;
   const char *site;
   unsigned kind, line, memory_type;
};
static struct ncl_record ncl_records[NCL_RECORDS];
static uint64_t ncl_created[NCL_KINDS], ncl_destroyed[NCL_KINDS];
static uint64_t ncl_live_bytes[NCL_KINDS], ncl_overflow, ncl_frames;
static uint64_t ncl_attempts, ncl_fail_size, ncl_fail_after, ncl_fail_count;
static bool ncl_enabled, ncl_inject;
static pthread_mutex_t ncl_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t ncl_once = PTHREAD_ONCE_INIT;
static time_t ncl_last_report;

static void ncl_init(void)
{
   const char *value = getenv("FAOT_GL41_DIAGNOSTICS");
   ncl_enabled = value && !strcmp(value, "1");
   value = getenv("FAOT_VK_FAIL_AFTER");
   ncl_inject = value != NULL;
   if (value) ncl_fail_after = strtoull(value, NULL, 10);
   value = getenv("FAOT_VK_FAIL_SIZE");
   if (value) ncl_fail_size = strtoull(value, NULL, 10);
   value = getenv("FAOT_VK_FAIL_COUNT");
   ncl_fail_count = value ? strtoull(value, NULL, 10) : 1;
   ncl_enabled |= ncl_inject;
}

static bool ncl_on(void)
{
   pthread_once(&ncl_once, ncl_init);
   return ncl_enabled;
}

/* All table operations hold ncl_lock. A zero handle is a reusable empty slot. */
static void ncl_add(struct zink_screen *screen, unsigned kind, uint64_t handle,
                    uint64_t bytes, unsigned type, const char *site, unsigned line)
{
   if (!ncl_on() || !handle) return;
   pthread_mutex_lock(&ncl_lock);
   ncl_created[kind]++;
   ncl_live_bytes[kind] += bytes;
   unsigned start = (unsigned)((handle >> 4) ^ (handle >> 32)) % NCL_RECORDS;
   unsigned i;
   for (i = 0; i < NCL_RECORDS; i++) {
      struct ncl_record *r = &ncl_records[(start + i) % NCL_RECORDS];
      if (!r->handle) {
         *r = (struct ncl_record){screen, handle, bytes, site, kind, line, type};
         break;
      }
   }
   if (i == NCL_RECORDS) ncl_overflow++;
   pthread_mutex_unlock(&ncl_lock);
}

static void ncl_del(struct zink_screen *screen, unsigned kind, uint64_t handle)
{
   if (!ncl_on() || !handle) return;
   pthread_mutex_lock(&ncl_lock);
   ncl_destroyed[kind]++;
   unsigned start = (unsigned)((handle >> 4) ^ (handle >> 32)) % NCL_RECORDS;
   for (unsigned i = 0; i < NCL_RECORDS; i++) {
      struct ncl_record *r = &ncl_records[(start + i) % NCL_RECORDS];
      if (!r->handle && !r->site) break;
      if (r->screen == screen && r->kind == kind && r->handle == handle) {
         ncl_live_bytes[kind] -= r->bytes;
         r->handle = 0;
         break;
      }
   }
   pthread_mutex_unlock(&ncl_lock);
}

static void ncl_summary_locked(void)
{
   fprintf(stderr, "[GL41-DIAG] frames=%"PRIu64" tableOverflow=%"PRIu64,
           ncl_frames, ncl_overflow);
   const char *names[] = {"memory", "buffer", "image", "framebuffer"};
   for (unsigned k = 0; k < NCL_KINDS; k++)
      fprintf(stderr, " %s(created/destroyed/live/liveBytes)=%"PRIu64"/%"PRIu64"/%"PRIu64"/%"PRIu64,
              names[k], ncl_created[k], ncl_destroyed[k], ncl_created[k]-ncl_destroyed[k], ncl_live_bytes[k]);
#ifdef __APPLE__
   task_vm_info_data_t vm;
   mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
   if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&vm, &count) == KERN_SUCCESS)
      fprintf(stderr, " physicalFootprint=%llu resident=%llu", vm.phys_footprint, vm.resident_size);
#endif
   fputc('\n', stderr);
}

void ncl_diag_frame(void)
{
   if (!ncl_on()) return;
   pthread_mutex_lock(&ncl_lock);
   ncl_frames++;
   time_t now = time(NULL);
   if (now - ncl_last_report >= 5) { ncl_last_report = now; ncl_summary_locked(); }
   pthread_mutex_unlock(&ncl_lock);
}

static void ncl_failure(struct zink_screen *screen, const char *operation,
                        VkResult result, uint64_t bytes, unsigned type)
{
   fprintf(stderr, "[GL41-DIAG] %s result=%d bytes=%"PRIu64" memoryType=%u",
           operation, result, bytes, type);
   if (type < screen->info.mem_props.memoryTypeCount) {
      unsigned heap = screen->info.mem_props.memoryTypes[type].heapIndex;
      fprintf(stderr, " physicalHeap=%u flags=0x%x heapSize=%"PRIu64,
              heap, screen->info.mem_props.memoryTypes[type].propertyFlags,
              screen->info.mem_props.memoryHeaps[heap].size);
   }
   fputc('\n', stderr);
   if (screen->info.have_EXT_memory_budget && screen->vk.GetPhysicalDeviceMemoryProperties2) {
      VkPhysicalDeviceMemoryBudgetPropertiesEXT budget = {
         .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MEMORY_BUDGET_PROPERTIES_EXT};
      VkPhysicalDeviceMemoryProperties2 props = {
         .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MEMORY_PROPERTIES_2, .pNext = &budget};
      screen->vk.GetPhysicalDeviceMemoryProperties2(screen->pdev, &props);
      for (unsigned i = 0; i < props.memoryProperties.memoryHeapCount; i++)
         fprintf(stderr, "[GL41-DIAG] heap=%u budget=%"PRIu64" usage=%"PRIu64"%c",
                 i, budget.heapBudget[i], budget.heapUsage[i], 10);
   }
   if (!ncl_on()) return;
   pthread_mutex_lock(&ncl_lock);
   ncl_summary_locked();
   unsigned printed = 0;
   for (unsigned i = 0; i < NCL_RECORDS && printed < 32; i++) {
      struct ncl_record *r = &ncl_records[i];
      if (r->screen != screen || !r->handle || r->kind != NCL_MEMORY) continue;
      fprintf(stderr, "[GL41-DIAG] outstanding memory=0x%"PRIx64" bytes=%"PRIu64" type=%u site=%s:%u%c",
              r->handle, r->bytes, r->memory_type, r->site, r->line, 10);
      printed++;
   }
   const char *home = getenv("HOME");
   char path[1024];
   FILE *dump = NULL;
   if (home && snprintf(path, sizeof(path), "%s/gl41-resources.txt", home) < (int)sizeof(path))
      dump = fopen(path, "w");
   if (dump) {
      fprintf(dump, "trackingOverflow=%"PRIu64" (nonzero means incomplete byte totals)%c", ncl_overflow, 10);
      for (unsigned i = 0; i < NCL_RECORDS; i++) {
         struct ncl_record *r = &ncl_records[i];
         if (r->screen == screen && r->handle)
            fprintf(dump, "kind=%u handle=0x%"PRIx64" bytes=%"PRIu64" type=%u site=%s:%u%c",
                    r->kind, r->handle, r->bytes, r->memory_type, r->site, r->line, 10);
      }
      fclose(dump);
   }
   pthread_mutex_unlock(&ncl_lock);
}

VkResult ncl_allocate_memory(struct zink_screen *s, const VkMemoryAllocateInfo *a,
                             const VkAllocationCallbacks *c, VkDeviceMemory *o,
                             const char *site, unsigned line)
{
   bool inject = false;
   ncl_on();
   if (ncl_inject && (!ncl_fail_size || ncl_fail_size == a->allocationSize)) {
      pthread_mutex_lock(&ncl_lock);
      inject = ncl_attempts++ >= ncl_fail_after && ncl_fail_count;
      if (inject && ncl_fail_count != UINT64_MAX) ncl_fail_count--;
      pthread_mutex_unlock(&ncl_lock);
   }
   *o = VK_NULL_HANDLE;
   VkResult r = inject ? VK_ERROR_OUT_OF_DEVICE_MEMORY : s->vk.AllocateMemory(s->dev, a, c, o);
   if (r == VK_SUCCESS) ncl_add(s, NCL_MEMORY, (uintptr_t)*o, a->allocationSize, a->memoryTypeIndex, site, line);
   else { *o = VK_NULL_HANDLE; fprintf(stderr, "[GL41-DIAG] site=%s:%u%c", site, line, 10); ncl_failure(s, inject ? "vkAllocateMemory(injected)" : "vkAllocateMemory", r, a->allocationSize, a->memoryTypeIndex); }
   return r;
}

void ncl_FreeMemory(struct zink_screen *s, VkDeviceMemory h, const VkAllocationCallbacks *c)
{ ncl_del(s, NCL_MEMORY, (uintptr_t)h); s->vk.FreeMemory(s->dev, h, c); }

VkResult ncl_create_buffer(struct zink_screen *s, const VkBufferCreateInfo *a,
                           const VkAllocationCallbacks *c, VkBuffer *o, const char *site, unsigned line)
{
   *o = VK_NULL_HANDLE;
   VkResult r = s->vk.CreateBuffer(s->dev, a, c, o);
   if (r == VK_SUCCESS) ncl_add(s, NCL_BUFFER, (uintptr_t)*o, a->size, UINT_MAX, site, line);
   else { *o = VK_NULL_HANDLE; ncl_failure(s, "vkCreateBuffer", r, a->size, UINT_MAX); }
   return r;
}
void ncl_DestroyBuffer(struct zink_screen *s, VkBuffer h, const VkAllocationCallbacks *c)
{ ncl_del(s, NCL_BUFFER, (uintptr_t)h); s->vk.DestroyBuffer(s->dev, h, c); }

VkResult ncl_create_image(struct zink_screen *s, const VkImageCreateInfo *a,
                          const VkAllocationCallbacks *c, VkImage *o, const char *site, unsigned line)
{
   *o = VK_NULL_HANDLE;
   VkResult r = s->vk.CreateImage(s->dev, a, c, o);
   /* Requirements describe the image, allocated memory is counted separately. */
   if (r == VK_SUCCESS && ncl_on()) {
      VkMemoryRequirements req = {0};
      s->vk.GetImageMemoryRequirements(s->dev, *o, &req);
      ncl_add(s, NCL_IMAGE, (uintptr_t)*o, req.size, UINT_MAX, site, line);
   } else if (r != VK_SUCCESS) { *o = VK_NULL_HANDLE; ncl_failure(s, "vkCreateImage", r, 0, UINT_MAX); }
   return r;
}
void ncl_DestroyImage(struct zink_screen *s, VkImage h, const VkAllocationCallbacks *c)
{ ncl_del(s, NCL_IMAGE, (uintptr_t)h); s->vk.DestroyImage(s->dev, h, c); }

VkResult ncl_BindBufferMemory(struct zink_screen *s, VkBuffer b, VkDeviceMemory m, VkDeviceSize o)
{
   VkResult r = s->vk.BindBufferMemory(s->dev, b, m, o);
   if (r != VK_SUCCESS) ncl_failure(s, "vkBindBufferMemory", r, o, UINT_MAX);
   return r;
}
VkResult ncl_BindImageMemory(struct zink_screen *s, VkImage b, VkDeviceMemory m, VkDeviceSize o)
{
   VkResult r = s->vk.BindImageMemory(s->dev, b, m, o);
   if (r != VK_SUCCESS) ncl_failure(s, "vkBindImageMemory", r, o, UINT_MAX);
   return r;
}
VkResult ncl_MapMemory(struct zink_screen *s, VkDeviceMemory m, VkDeviceSize o,
                       VkDeviceSize size, VkMemoryMapFlags flags, void **p)
{
   *p = NULL;
   VkResult r = s->vk.MapMemory(s->dev, m, o, size, flags, p);
   if (r != VK_SUCCESS) { *p = NULL; ncl_failure(s, "vkMapMemory", r, size, UINT_MAX); }
   return r;
}

VkResult ncl_create_framebuffer(struct zink_screen *s, const VkFramebufferCreateInfo *a,
                                const VkAllocationCallbacks *c, VkFramebuffer *o,
                                const char *site, unsigned line)
{
   *o = VK_NULL_HANDLE;
   VkResult r = s->vk.CreateFramebuffer(s->dev, a, c, o);
   if (r == VK_SUCCESS) ncl_add(s, NCL_FRAMEBUFFER, (uintptr_t)*o, 0, UINT_MAX, site, line);
   else { *o = VK_NULL_HANDLE; ncl_failure(s, "vkCreateFramebuffer", r, 0, UINT_MAX); }
   return r;
}
void ncl_DestroyFramebuffer(struct zink_screen *s, VkFramebuffer h, const VkAllocationCallbacks *c)
{ ncl_del(s, NCL_FRAMEBUFFER, (uintptr_t)h); s->vk.DestroyFramebuffer(s->dev, h, c); }
