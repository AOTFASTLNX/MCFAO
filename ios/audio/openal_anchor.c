/* Public Apple OpenAL framework anchor. dlsym on this handle also searches its dependencies. */
#include <OpenAL/alc.h>
const void *faot_openal_framework_anchor(void) { return (const void *)alcGetProcAddress; }
