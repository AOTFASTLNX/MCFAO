#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../../ios/C0Harness/log_file.h"

int main(void) {
    char path[] = "/private/tmp/faot-log-XXXXXX";
    int temp = mkstemp(path);
    if (temp < 0) return 1;
    close(temp);
    int descriptor = faot_open_append_log(path);
    if (descriptor < 0 || !(fcntl(descriptor, F_GETFL) & O_APPEND)) return 2;
    FILE *output = fdopen(descriptor, "w"), *host = fopen(path, "a");
    if (!output || !host) return 3;
    setvbuf(output, NULL, _IONBF, 0);
    setvbuf(host, NULL, _IONBF, 0);
    fputs("host start\n", host);
    fputs("java entry\n", output);
    fputs("host returned 0\n", host);
    fputs("delayed system output\n", output);
    fclose(host);
    fclose(output);
    FILE *reader = fopen(path, "r");
    if (!reader) return 4;
    char data[256] = {0};
    size_t bytes = fread(data, 1, sizeof(data) - 1, reader);
    int failed = ferror(reader);
    fclose(reader);
    unlink(path);
    const char *expected = "host start\njava entry\nhost returned 0\ndelayed system output\n";
    if (failed || bytes != strlen(expected) || strcmp(data, expected)) return 5;
    puts("C0_APPEND_LOG_PASS");
    return 0;
}
