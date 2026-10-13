#include <assert.h>
#include <stdio.h>
#include "../magicon/remote_position.h"
int main(void){
 remote_position p={0};uint16_t offset;
 assert(!remote_position_byte(&p,0,&offset));
 for(unsigned mirror=0;mirror<4;mirror++)for(unsigned row=0;row<30;row++)for(unsigned col=0;col<32;col++){
  remote_position_name(&p,(uint16_t)(0x2000+mirror*1024+row*32+col));
  for(unsigned y=0;y<8;y++)for(unsigned plane=0;plane<2;plane++){
   assert(remote_position_byte(&p,(uint16_t)(col*16+y+plane*8),&offset));
   assert(offset==((row*8+y)*32+col)*2+plane);
  }
  remote_position previous=p;remote_position_name(&p,(uint16_t)(0x23c0+mirror*1024));
  assert(p.coarse_y==previous.coarse_y && p.column==previous.column);
  assert(!remote_position_byte(&p,0x1000,&offset));
 }
 puts("PASS all 4 mirrors, 30 rows, 32 columns, 8 fine rows and both planes; attributes/sprites ignored");
}
