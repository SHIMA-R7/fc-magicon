// Optional FCCH transport. Only complete, contiguous frames can be committed.
#pragma once
#include <stdint.h>
#include <string.h>
#define REMOTE_FB_BYTES 15360u
#define REMOTE_META_BYTES 99u
#define REMOTE_FRAME_BYTES (REMOTE_FB_BYTES + REMOTE_META_BYTES)
#define REMOTE_CHUNK_BYTES 1024u
typedef struct { uint16_t received; uint8_t meta[REMOTE_META_BYTES]; } remote_chunk_state;
static inline int remote_chunk_accept(remote_chunk_state *state, uint8_t *back,
    uint16_t offset, uint16_t length, const uint8_t *data) {
    if (!length || length > REMOTE_CHUNK_BYTES || (uint32_t)offset + length > REMOTE_FRAME_BYTES) {
        state->received = 0; return -1;
    }
    if (offset == 0) state->received = 0;
    if (!back || offset != state->received) { state->received = 0; return -1; }
    uint16_t fb_length = offset < REMOTE_FB_BYTES ?
        (uint16_t)((REMOTE_FB_BYTES - offset < length) ? REMOTE_FB_BYTES - offset : length) : 0;
    if (fb_length) memcpy(back + offset, data, fb_length);
    if (length > fb_length) memcpy(state->meta + offset + fb_length - REMOTE_FB_BYTES,
        data + fb_length, length - fb_length);
    state->received += length;
    return state->received == REMOTE_FRAME_BYTES;
}
