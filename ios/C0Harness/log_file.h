#ifndef FAOT_LOG_FILE_H
#define FAOT_LOG_FILE_H
#include <fcntl.h>
#include <sys/stat.h>

/* stdout/stderr and the host's separate append stream share this pathname.
   Every writer must use O_APPEND so delayed OS/Java output cannot overwrite host records. */
static inline int faot_open_append_log(const char *path) {
    return open(path, O_WRONLY | O_CREAT | O_APPEND, S_IRUSR | S_IWUSR);
}
#endif
