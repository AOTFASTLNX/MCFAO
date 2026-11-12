#include "pointer_state.h"

#include <string.h>

void faot_pointer_reset(FAOTPointerState *state) {
    if (state) memset(state, 0, sizeof *state);
}

void faot_pointer_set_captured(FAOTPointerState *state, int captured) {
    if (state) state->captured = !!captured;
}

void faot_pointer_set_active(FAOTPointerState *state, int active) {
    if (state) state->active = !!active;
}

void faot_pointer_set_scene_full_screen(FAOTPointerState *state, int full_screen) {
    if (state) state->scene_full_screen = !!full_screen;
}

void faot_pointer_set_locked(FAOTPointerState *state, int locked) {
    if (state) state->pointer_locked = !!locked;
}

void faot_pointer_set_mouse_connected(FAOTPointerState *state, int connected) {
    if (state) state->mouse_connected = !!connected;
}

int faot_pointer_prefers_lock(const FAOTPointerState *state) {
    return state && state->captured && state->active && state->scene_full_screen;
}

int faot_pointer_should_forward_motion(const FAOTPointerState *state) {
    /* The camera follows capture, not the system's lock decision. */
    return state && state->captured && state->active;
}

int faot_pointer_should_forward_hover_delta(const FAOTPointerState *state) {
    /* GCMouse is the accurate path. Hover deltas only cover devices that do not
       appear in GCMouse.mice (notably some built-in Magic Keyboard trackpads). */
    return state && state->captured && state->active && !state->mouse_connected;
}

int faot_pointer_should_forward_button(const FAOTPointerState *state) {
    return state && state->captured && state->active;
}

int faot_pointer_should_send_menu_cursor(const FAOTPointerState *state) {
    return state && !state->captured;
}

void faot_pointer_note_lock_request(FAOTPointerState *state) {
    if (state) state->lock_requests++;
}

void faot_pointer_note_motion(FAOTPointerState *state, int forwarded) {
    if (!state) return;
    if (forwarded) state->motion_forwarded++;
    else state->motion_dropped++;
}

void faot_pointer_note_button(FAOTPointerState *state, int forwarded) {
    if (state && forwarded) state->buttons_forwarded++;
}
