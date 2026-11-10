#ifndef FAOT_INPUT_MAPPING_H
#define FAOT_INPUT_MAPPING_H
/* USB keyboard usage page to GLFW key tokens. Text composition remains in UIKit. */
static inline int faot_glfw_key_from_hid(unsigned usage) {
    if (usage>=0x04 && usage<=0x1d) return 'A'+(int)(usage-0x04);
    if (usage>=0x1e && usage<=0x26) return '1'+(int)(usage-0x1e);
    if (usage>=0x3a && usage<=0x45) return 290+(int)(usage-0x3a);
    switch (usage) {
    case 0x27:return '0'; case 0x28:return 257; case 0x29:return 256;
    case 0x2a:return 259; case 0x2b:return 258; case 0x2c:return ' ';
    case 0x2d:return '-'; case 0x2e:return '='; case 0x2f:return '[';
    case 0x30:return ']'; case 0x31:return '\\'; case 0x33:return ';';
    case 0x34:return '\''; case 0x35:return '`'; case 0x36:return ',';
    case 0x37:return '.'; case 0x38:return '/'; case 0x39:return 280;
    case 0x49:return 260; case 0x4a:return 268; case 0x4b:return 266;
    case 0x4c:return 261; case 0x4d:return 269; case 0x4e:return 267;
    case 0x4f:return 262; case 0x50:return 263; case 0x51:return 264; case 0x52:return 265;
    case 0xe0:return 341; case 0xe1:return 340; case 0xe2:return 342; case 0xe3:return 343;
    case 0xe4:return 345; case 0xe5:return 344; case 0xe6:return 346; case 0xe7:return 347;
    default:return -1;
    }
}
#endif
