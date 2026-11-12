#ifndef FAOT_POINTER_STATE_H
#define FAOT_POINTER_STATE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Platform-independent policy for the iPadOS pointer input bridge.
 *
 * Keeping this state machine out of uikit_surface.m lets the host test cover the
 * transitions that matter on a real device without pretending that a macOS
 * fixture is an iPad acceptance test.
 *
 * Rules:
 *  - Pointer lock is only requested while the game is captured, the scene is
 *    foreground-active, and the scene fills the screen. iPadOS silently refuses
 *    a lock request from a windowed scene.
 *  - Relative camera motion is forwarded whenever the game is captured, even if
 *    the system refuses the lock. This is the fallback for a Magic Keyboard
 *    trackpad that exposes hover/indirect events but no GCMouse stream. The
 *    cursor may remain visible in that fallback; the input log records it.
 *  - Menu motion is absolute hover, never relative camera motion.
 *  - Pointer buttons are game input only while captured; menus use UIKit
 *    indirect-pointer touches.
 */
typedef struct {
    int captured;
    int active;
    int scene_full_screen;
    int pointer_locked;
    int mouse_connected;
    uint64_t lock_requests;
    uint64_t motion_forwarded;
    uint64_t motion_dropped;
    uint64_t buttons_forwarded;
} FAOTPointerState;

void faot_pointer_reset(FAOTPointerState *state);
void faot_pointer_set_captured(FAOTPointerState *state, int captured);
void faot_pointer_set_active(FAOTPointerState *state, int active);
void faot_pointer_set_scene_full_screen(FAOTPointerState *state, int full_screen);
void faot_pointer_set_locked(FAOTPointerState *state, int locked);
void faot_pointer_set_mouse_connected(FAOTPointerState *state, int connected);

int faot_pointer_prefers_lock(const FAOTPointerState *state);
int faot_pointer_should_forward_motion(const FAOTPointerState *state);
int faot_pointer_should_forward_hover_delta(const FAOTPointerState *state);
int faot_pointer_should_forward_button(const FAOTPointerState *state);
int faot_pointer_should_send_menu_cursor(const FAOTPointerState *state);

void faot_pointer_note_lock_request(FAOTPointerState *state);
void faot_pointer_note_motion(FAOTPointerState *state, int forwarded);
void faot_pointer_note_button(FAOTPointerState *state, int forwarded);

#ifdef __cplusplus
}
#endif

#endif
