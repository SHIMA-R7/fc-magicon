#pragma once
// First C6-native browser: CP932 text, a JPEG portrait, internal links and FCFR.
#include <HTTPClient.h>
#include <NetworkClientSecure.h>
#include <esp32c6/rom/tjpgd.h>
#include <vector>
#include "web_font.h"

namespace fcweb {
static const char *origin="https://abehiroshi.la.coocan.jp";
static String path="/top.htm",html,message="WAIT WIFI";
static uint8_t frame[15463],sending[15463],photo[112*132*3];
static int photo_w,photo_h,photo_y,scroll,extent,selected=-1;
static String links[48];static int link_y[48],link_count;
static uint32_t changed=1,last_send,retry_at;
static size_t tx;
static bool loaded;
static WiFiServer inspector(5002);
static const uint8_t pals[16]={0x30,0x0f,0x01,0x10, 0x30,0x0f,0x00,0x0c,
                              0x30,0x0f,0x00,0x36, 0x30,0x0f,0x00,0x10};
// RGB values from the same agnes NES palette used by the host preview.
static const uint8_t rgb[16][3]={{252,252,252},{0,0,0},{0,0,252},{188,188,188},{252,252,252},{0,0,0},{124,124,124},{0,64,88},{252,252,252},{0,0,0},{124,124,124},{240,208,176},{252,252,252},{0,0,0},{124,124,124},{188,188,188}};
static void pixel(int x,int y,int v) {
 if(x<0||x>=256||y<0||y>=240)return;
 int at=4+(y*32+x/8)*2;uint8_t mask=0x80>>(x&7);
 frame[at]=(frame[at]&~mask)|((v&1)?mask:0);
 frame[at+1]=(frame[at+1]&~mask)|((v&2)?mask:0);
}
static void bank(int x,int y,int n) {
 int bx=x/16,by=y/16,at=15396+(by/2)*8+bx/2,shift=((by&1)*2+(bx&1))*2;
 frame[at]=(frame[at]&~(3<<shift))|(n<<shift);
}
static void glyph(int x,int y,uint16_t key,int ink=1) {
 int lo=0,hi=sizeof(web_font_keys)/sizeof(*web_font_keys);
 while(lo<hi){int m=(lo+hi)/2;if(web_font_keys[m]<key)lo=m+1;else hi=m;}
 if(lo>=int(sizeof(web_font_keys)/sizeof(*web_font_keys))||web_font_keys[lo]!=key)return;
 for(int j=0;j<14;j++)for(int i=0;i<12;i++)if(web_font_rows[lo][j]&(1<<(11-i)))pixel(x+i,y+j,ink);
}
static String attr(String tag,const char *name) {
 String low=tag;low.toLowerCase();int at=0;
 while((at=low.indexOf(name,at))>=0){
  if(at&&isalnum((unsigned char)low[at-1])){at++;continue;}
  int k=at+strlen(name);while(k<int(tag.length())&&isspace((unsigned char)tag[k]))k++;
  if(tag[k++]!='='){at++;continue;}
  while(k<int(tag.length())&&isspace((unsigned char)tag[k]))k++;
  char q=tag[k];if(q=='\''||q=='"'){int e=tag.indexOf(q,k+1);return e>=0?tag.substring(k+1,e):String();}
  int e=k;while(e<int(tag.length())&&!isspace((unsigned char)tag[e])&&tag[e]!='>')e++;
  return tag.substring(k,e);
 }return String();
}
static String resolve(String value) {
 value.trim();int hash=value.indexOf('#');if(hash>=0)value=value.substring(0,hash);
 if(!value.length())return String();
 if(value.startsWith(origin))value=value.substring(strlen(origin));
 else if(value.startsWith("http://abehiroshi.la.coocan.jp/"))value=value.substring(30);
 else if(value.indexOf(":")>=0||value.startsWith("//"))return String();
 if(!value.startsWith("/"))value=path.substring(0,path.lastIndexOf('/')+1)+value;
 std::vector<String> parts;int begin=1;
 for(int i=1;i<=int(value.length());i++)if(i==int(value.length())||value[i]=='/'){
  String part=value.substring(begin,i);begin=i+1;
  if(part==".."){if(!parts.empty())parts.pop_back();}else if(part!="."&&part.length())parts.push_back(part);
 }
 String result;for(auto &p:parts)result+="/"+p;
 return result.length()?result:String("/");
}
class Sink:public Stream {
 public:String data;size_t cap;bool overflow=false;Sink(size_t n):cap(n){data.reserve(4096);}
 int available()override{return 0;}int read()override{return -1;}int peek()override{return -1;}
 size_t write(uint8_t c)override{return write(&c,1);}
 size_t write(const uint8_t*p,size_t n)override{
  if(data.length()+n>cap){overflow=true;return 0;}
  return data.concat((const char*)p,n)?n:0;
 }
};
static bool fetch(const String &target,String &out,size_t cap) {
 NetworkClientSecure tls;tls.useBuiltinCACertBundle();HTTPClient http;
 http.setConnectTimeout(7000);http.setTimeout(7000);http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
 if(!http.begin(tls,String(origin)+target)){message="HTTP BEGIN FAILED";return false;}
 http.setUserAgent("FC-MAGICON-C6/0.1");int status=http.GET();
 if(status!=200){message="HTTP "+String(status);http.end();return false;}
 Sink sink(cap);int size=http.writeToStream(&sink);http.end();
 if(size<0||sink.overflow){message="DOWNLOAD LIMIT/ERROR";return false;}
 out=std::move(sink.data);return true;
}
struct JpegInput{const uint8_t*p;size_t n,at;};
static UINT jpeg_read(JDEC*j,BYTE*dest,UINT n) {
 auto *s=(JpegInput*)j->device;n=std::min(size_t(n),s->n-s->at);
 if(dest)memcpy(dest,s->p+s->at,n);s->at+=n;return n;
}
static UINT jpeg_out(JDEC*,void*data,JRECT*r) {
 auto *p=(uint8_t*)data;int width=r->right-r->left+1;
 for(int y=r->top;y<=r->bottom;y++)for(int x=r->left;x<=r->right;x++)
  if(x<photo_w&&y<photo_h)memcpy(photo+(y*photo_w+x)*3,p+((y-r->top)*width+x-r->left)*3,3);
 return 1;
}
static void get_photo() {
 photo_w=photo_h=0;int at=html.indexOf("<img");if(at<0)at=html.indexOf("<IMG");
 if(at<0)return;int end=html.indexOf('>',at);String target=resolve(attr(html.substring(at,end),"src"));
 if(!target.endsWith(".jpg")&&!target.endsWith(".jpeg"))return;
 String bytes;if(!fetch(target,bytes,96*1024))return;
 JpegInput input{(const uint8_t*)bytes.c_str(),bytes.length(),0};JDEC dec;static uint8_t work[8192];
 if(jd_prepare(&dec,jpeg_read,work,sizeof work,&input)!=JDR_OK)return;
 int scale=0;while(scale<3&&((dec.width>>scale)>112||(dec.height>>scale)>132))scale++;
 photo_w=dec.width>>scale;photo_h=dec.height>>scale;
 if(!photo_w||!photo_h||photo_w>112||photo_h>132){photo_w=photo_h=0;return;}
 if(jd_decomp(&dec,jpeg_out,scale)!=JDR_OK)photo_w=photo_h=0;
}
static int nearest(const uint8_t*p,int b,int *error=nullptr) {
 int best=0,cost=0x7fffffff;
 for(int k=0;k<4;k++){int e=0;for(int c=0;c<3;c++){int d=int(p[c])-rgb[b*4+k][c];e+=d*d;}
  if(e<cost){cost=e;best=k;}}
 if(error)*error=cost;return best;
}
static void draw_photo(int doc_y) {
 int left=80,top=24+doc_y-scroll;
 for(int by=std::max(16,top);by<std::min(216,top+photo_h);by+=16)
 for(int bx=left;bx<left+photo_w;bx+=16){
  int best=3,best_error=0x7fffffff;
  for(int b=1;b<4;b++){int error=0;for(int y=std::max(24,by);y<std::min(216,std::min(by+16,top+photo_h));y++)
   for(int x=bx;x<std::min(bx+16,left+photo_w);x++){int e;nearest(photo+((y-top)*photo_w+x-left)*3,b,&e);error+=e;}
   if(error<best_error){best_error=error;best=b;}}
  bank(bx,by,best);
  for(int y=std::max(24,by);y<std::min(216,std::min(by+16,top+photo_h));y++)for(int x=bx;x<std::min(bx+16,left+photo_w);x++)
   pixel(x,y,nearest(photo+((y-top)*photo_w+x-left)*3,best));
 }
}
static void render() {
 memset(frame,0,sizeof frame);memcpy(frame,"FCFR",4);
 for(int i=0;i<32;i++)frame[15364+i]=pals[i%16];
 int x=8,y=0,current=-1;bool hidden=false,image_done=false;link_count=0;
 auto newline=[&](){if(x!=8){y+=16;x=8;}};
 for(unsigned at=0;at<html.length()&&y<16000;){
  uint8_t c=html[at++];
  if(c=='<'){
   if(html.substring(at,at+3)=="!--"){int close=html.indexOf("-->",at+3);if(close<0)break;at=close+3;continue;}
   int end=html.indexOf('>',at);if(end<0)break;
   String tag=html.substring(at,end),lower=tag;lower.toLowerCase();at=end+1;
   int space=lower.indexOf(' ');String name=space<0?lower:lower.substring(0,space);
   if(name=="head"||name=="script"||name=="style")hidden=true;
   if(name=="/head"||name=="/script"||name=="/style"){hidden=false;continue;}
   if(hidden)continue;
   if(name=="a"){
    String target=resolve(attr(tag,"href"));current=-1;
    if(target.length()&&link_count<48){current=link_count;links[current]=target;link_y[current]=y;link_count++;}
   }else if(name=="/a")current=-1;
   if(name=="br"||name=="p"||name=="/p"||name=="tr"||name=="/td"||name=="h1"||name=="/h1"||name=="div"||name=="/div")newline();
   if(name=="img"&&!image_done&&photo_h){newline();y=((y+24+15)/16)*16-24;photo_y=y;draw_photo(y);y+=((photo_h+15)/16)*16+16;image_done=true;}
   continue;
  }
  if(hidden)continue;
  if(c=='&'){int end=html.indexOf(';',at);if(end>=0&&end-int(at)<12){String e=html.substring(at,end);at=end+1;c=e=="amp"?'&':e=="lt"?'<':e=="gt"?'>':e=="quot"?'"':' ';}}
  if(c<=32){if(x==8)continue;c=' ';}
  uint16_t code=c;int width=8;
  if((c>=0x81&&c<=0x9f)||c>=0xe0){if(at>=html.length())break;code=(c<<8)|(uint8_t)html[at++];width=12;}
  if(x+width>248)newline();
  int sy=24+y-scroll;
  if(sy>=24&&sy+14<=216){
   if(current>=0&&current==selected){for(int yy=sy;yy<sy+16;yy++)for(int xx=x;xx<x+width;xx++)pixel(xx,yy,1);glyph(x,sy,code,0);}
   else glyph(x,sy,code,current>=0?2:1);
   if(current>=0)for(int xx=x;xx<x+width;xx++)pixel(xx,sy+14,current==selected?0:2);
  }x+=width;
 }
 extent=y+16;String label="FC WEB / ABE HIROSHI";
 for(unsigned i=0;i<label.length();i++)glyph(4+i*8,4,label[i]);
 label=String(scroll)+" B:MENU A:OPEN";for(unsigned i=0;i<label.length();i++)glyph(4+i*8,224,label[i]);
 changed=1;
}
static bool load(String next) {
 String source;if(!fetch(next,source,64*1024))return false;
 path=next;html=std::move(source);scroll=0;selected=-1;get_photo();render();loaded=true;
 message="PAGE READY";Serial0.printf("WEB PAGE_READY path=%s html=%u photo=%dx%d links=%d heap=%u\r\n",path.c_str(),html.length(),photo_w,photo_h,link_count,ESP.getFreeHeap());return true;
}
static void input(uint8_t buttons) {
 static uint8_t old;uint8_t pressed=buttons&~old;old=buttons;if(!pressed)return;
 if(pressed&0x08)scroll=std::max(0,scroll-32);
 if(pressed&0x04)scroll=std::min(std::max(0,extent-192),scroll+32);
 scroll&=~15;
 if((pressed&3)&&link_count){selected=(selected+(pressed&1?1:-1)+link_count)%link_count;scroll=std::max(0,(link_y[selected]-32)&~15);}
 if(pressed&0x80&&selected>=0){String next=links[selected];load(next);}
 else if(pressed&0x40)load("/menu.htm");
 else if(pressed&0x10)load("/top.htm");
 else if(pressed&0x20)load(path);
 render();
}
static void receive(uint8_t c) {
 static uint8_t bytes[20];static int count;
 if(count<4){bytes[count++]=c;if(count==4&&memcmp(bytes,"FCIN",4)){memmove(bytes,bytes+1,3);count=3;}return;}
 bytes[count++]=c;if(count==20){input(bytes[4]);count=0;}
}
static void poll(bool paused) {
 if(paused){
  if(tx){size_t n=std::min(sizeof(sending)-(tx-1),size_t(512));tx+=Serial.write(sending+tx-1,n);
   if(tx==sizeof(sending)+1){tx=0;last_send=millis();}}
  return;
 }
 if(WiFi.status()!=WL_CONNECTED)return;
 static bool clock_started;
 if(!clock_started){configTime(0,0,"pool.ntp.org","time.google.com");inspector.begin();clock_started=true;}
 if(!loaded&&time(nullptr)<=1700000000)message="WAIT CLOCK";
 if(!loaded&&millis()>retry_at&&time(nullptr)>1700000000){retry_at=millis()+30000;if(!load(path))Serial0.printf("WEB FAILED %s heap=%u\r\n",message.c_str(),ESP.getFreeHeap());}
 WiFiClient observer=inspector.accept();
 if(observer){
  observer.setTimeout(100);String request=observer.readStringUntil('\n');
  if(request.startsWith("GET /frame ")&&loaded){
   observer.printf("HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nContent-Length: %u\r\nConnection: close\r\n\r\n",sizeof frame);observer.write(frame,sizeof frame);
  }else{
   String json=String("{\"loaded\":")+(loaded?"true":"false")+",\"message\":\""+message+"\",\"epoch\":"+String((unsigned long)time(nullptr))+",\"html_bytes\":"+String(html.length())+",\"photo_width\":"+String(photo_w)+",\"photo_height\":"+String(photo_h)+",\"heap\":"+String(ESP.getFreeHeap())+"}";
   observer.printf("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %u\r\nConnection: close\r\n\r\n",json.length());observer.print(json);
  }observer.stop();
 }
 if(!loaded||!Serial)return;
 while(Serial.available())receive(Serial.read());
 if(!tx&&(changed||millis()-last_send>=1000)){memcpy(sending,frame,sizeof frame);tx=1;changed=0;}
 if(tx){size_t left=sizeof(frame)-(tx-1),n=std::min(left,size_t(512));size_t sent=Serial.write(sending+tx-1,n);tx+=sent;
  if(tx==sizeof(frame)+1){tx=0;last_send=millis();}}
}
}
