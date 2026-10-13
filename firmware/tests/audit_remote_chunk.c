#include <assert.h>
#include <stdio.h>
#include "../magicon/remote_chunk.h"
int main(void){
 remote_chunk_state state={0};
 uint8_t frame[REMOTE_FRAME_BYTES],back[REMOTE_FB_BYTES];
 for(unsigned pass=0;pass<100;pass++){
  for(unsigned i=0;i<sizeof frame;i++)frame[i]=(uint8_t)(i*13+pass*37);
  for(unsigned offset=0;offset<sizeof frame;offset+=REMOTE_CHUNK_BYTES){
   unsigned len=sizeof frame-offset;if(len>REMOTE_CHUNK_BYTES)len=REMOTE_CHUNK_BYTES;
   assert(remote_chunk_accept(&state,back,offset,len,frame+offset)==(offset+len==sizeof frame));
  }
  assert(!memcmp(back,frame,sizeof back));assert(!memcmp(state.meta,frame+sizeof back,sizeof state.meta));
 }
 assert(remote_chunk_accept(&state,back,0,1024,frame)==0);
 assert(remote_chunk_accept(&state,back,2048,1024,frame+2048)==-1); // lost chunk
 assert(remote_chunk_accept(&state,back,1024,1024,frame+1024)==-1); // cannot finish stale frame
 assert(remote_chunk_accept(&state,back,0,1024,frame)==0); // explicit new frame recovers
 assert(remote_chunk_accept(&state,back,0,0,frame)==-1);
 assert(remote_chunk_accept(&state,back,0,1025,frame)==-1);
 assert(remote_chunk_accept(&state,back,15459,1,frame)==-1);
 assert(remote_chunk_accept(&state,NULL,0,1,frame)==-1);
 puts("PASS 100 chunked frames, metadata, missing/out-of-order chunks, bounds and recovery");
}
