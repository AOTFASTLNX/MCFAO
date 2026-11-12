/* Host fixture for the platform-independent iPad pointer policy. Not device acceptance. */
#include "pointer_state.h"

#include <assert.h>
#include <stdio.h>

int main(void) {
    FAOTPointerState state;
    faot_pointer_reset(&state);
    assert(!faot_pointer_prefers_lock(&state));
    assert(!faot_pointer_should_forward_motion(&state));
    assert(faot_pointer_should_send_menu_cursor(&state));

    /* Menu: absolute hover drives the pointer; relative camera motion is rejected. */
    faot_pointer_set_active(&state, 1);
    faot_pointer_set_scene_full_screen(&state, 1);
    assert(!faot_pointer_prefers_lock(&state));
    assert(!faot_pointer_should_forward_motion(&state));
    assert(faot_pointer_should_send_menu_cursor(&state));
    assert(!faot_pointer_should_forward_button(&state));

    /* World entry in a full-screen scene: request the lock and accept camera motion. */
    faot_pointer_set_captured(&state, 1);
    assert(faot_pointer_prefers_lock(&state));
    assert(faot_pointer_should_forward_motion(&state));
    assert(faot_pointer_should_forward_button(&state));
    assert(!faot_pointer_should_send_menu_cursor(&state));
    faot_pointer_note_lock_request(&state);
    assert(state.lock_requests == 1);

    /* The system approves the lock. */
    faot_pointer_set_locked(&state, 1);
    assert(faot_pointer_prefers_lock(&state));
    faot_pointer_note_motion(&state, 1);
    assert(state.motion_forwarded == 1 && state.motion_dropped == 0);

    /* A windowed scene on iPadOS 26/27 cannot be locked, but camera motion still works. */
    faot_pointer_set_scene_full_screen(&state, 0);
    assert(!faot_pointer_prefers_lock(&state));
    assert(faot_pointer_should_forward_motion(&state));
    faot_pointer_note_motion(&state, 1);
    assert(state.motion_forwarded == 2);

    /* Background/foreground transitions must not leave a stale lock request. */
    faot_pointer_set_active(&state, 0);
    assert(!faot_pointer_prefers_lock(&state));
    assert(!faot_pointer_should_forward_motion(&state));
    assert(!faot_pointer_should_forward_button(&state));
    faot_pointer_set_active(&state, 1);
    faot_pointer_set_scene_full_screen(&state, 1);
    assert(faot_pointer_prefers_lock(&state));

    /* GCMouse is preferred; hover deltas are only a fallback for trackpads without GCMouse. */
    assert(faot_pointer_should_forward_hover_delta(&state));
    faot_pointer_set_mouse_connected(&state, 1);
    assert(!faot_pointer_should_forward_hover_delta(&state));
    faot_pointer_set_mouse_connected(&state, 0);
    assert(faot_pointer_should_forward_hover_delta(&state));

    /* Menu release must drop relative motion immediately. */
    faot_pointer_set_captured(&state, 0);
    assert(!faot_pointer_should_forward_motion(&state));
    assert(faot_pointer_should_send_menu_cursor(&state));
    faot_pointer_note_motion(&state, 0);
    assert(state.motion_dropped == 1);

    puts("POINTER_STATE_PASS");
    return 0;
}
