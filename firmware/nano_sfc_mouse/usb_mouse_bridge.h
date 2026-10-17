// Optional PC bridge. Original SoftwareSerial stream to Pico is unchanged.
// USB data is silent until a host explicitly sends FCNM?\n at 115200 baud.
#pragma once
#include <Arduino.h>

static uint8_t usbMouseSequence=0,usbMouseButtons[2]={0,0},usbMouseType[2]={0,0};
static uint32_t usbLastQuery=0,usbLastReport[2]={0,0};
static bool usbBridgeConnected=false;
static uint16_t usbMouseCRC(const uint8_t *p,uint8_t n) {
  uint16_t c=0xffff;
  while(n--){c^=(uint16_t)*p++<<8;for(uint8_t i=0;i<8;i++)c=(c&0x8000)?(c<<1)^0x1021:c<<1;}
  return c;
}
static void usbMousePacket(uint8_t type,uint8_t port,uint8_t buttons,int8_t dx,int8_t dy) {
  uint8_t b[12]={'F','N','M','1',type,usbMouseSequence++,port,buttons,(uint8_t)dx,(uint8_t)dy,0,0};
  uint16_t c=usbMouseCRC(b,10);b[10]=c&255;b[11]=c>>8;Serial.write(b,sizeof b);
}
static void usbMouseBegin(){Serial.begin(115200);}
static void usbMousePoll() {
  static uint8_t at=0;
  const char query[]="FCNM?\n";
  while(Serial.available()) {
    char c=Serial.read();if(c==query[at])at++;else at=(c==query[0])?1:0;
    if(at==sizeof(query)-1){at=0;usbLastQuery=millis();usbBridgeConnected=true;usbMousePacket(0,0,0,0,0);}
  }
  if(usbBridgeConnected && millis()-usbLastQuery>3000)usbBridgeConnected=false;
}
static void usbMouseReport(uint8_t port,bool present,uint8_t buttons,int8_t dx,int8_t dy) {
  if(!usbBridgeConnected)return;
  uint8_t i=port-1,type=present?1:2;
  uint32_t now=millis();
  if(dx || dy || buttons!=usbMouseButtons[i] || type!=usbMouseType[i] || now-usbLastReport[i]>=100) {
    usbMousePacket(type,port,buttons,dx,dy);usbLastReport[i]=now;
    usbMouseButtons[i]=buttons;usbMouseType[i]=type;
  }
}
