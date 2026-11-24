#pragma once
#include "esp_adc/adc_continuous.h"
#include "esp_timer.h"

// Armed only by an explicit PC UART command. PCM is streamed to PC storage;
// the C6 does not silently record into its flash or send microphone audio online.
namespace micrec {
static bool armed, recording, playing, play_started, play_confirmed;
static bool released[2], stable[2], candidate[2];
static unsigned repetitions[2];
static constexpr unsigned RELAY_GPIO = 1; // NC wiring: HIGH disconnects 45/46.
static uint32_t last_upload;
static uint8_t upload[527];
static unsigned upload_used, upload_expected;
static uint32_t upload_begun;
static uint32_t sequence, samples, last_keepalive, last_controller;
static uint8_t rx[12];
static unsigned rx_used;
static volatile uint32_t overflow;
static adc_continuous_handle_t adc;
static uint8_t channel;

static uint32_t hash(const uint8_t *p, size_t n, uint32_t h = 2166136261u) {
  while (n--) h = (h ^ *p++) * 16777619u;
  return h;
}
static void packet(char type, const void *payload, uint16_t size) {
  uint8_t header[11] = {'M','2','P','K',(uint8_t)type,
    (uint8_t)size,(uint8_t)(size >> 8)};
  uint32_t seq = sequence++;
  for (unsigned i = 0; i < 4; i++) header[7+i] = seq >> (8*i);
  uint32_t h = hash((const uint8_t *)payload, size, hash(header, sizeof header));
  uint8_t tail[4]; for (unsigned i = 0; i < 4; i++) tail[i] = h >> (8*i);
  Serial0.write(header, sizeof header); Serial0.write((const uint8_t *)payload, size);
  Serial0.write(tail, sizeof tail);
}
static void text(char type, const char *s) { packet(type, s, strlen(s)); }
static void relay(bool disconnect) {
  gpio_set_level((gpio_num_t)RELAY_GPIO, disconnect ? 1 : 0);
}
static void init_relay() {
  // Arduino 3.x ignores digitalWrite before pinMode. Set the hardware output
  // latch LOW first, then enable the output, independent of Arduino ownership.
  const gpio_num_t pin=(gpio_num_t)RELAY_GPIO;
  gpio_set_level(pin,0);
  gpio_config_t cfg={};
  cfg.pin_bit_mask=1ULL<<RELAY_GPIO;
  cfg.mode=GPIO_MODE_INPUT_OUTPUT;
  cfg.pull_up_en=GPIO_PULLUP_DISABLE;
  cfg.pull_down_en=GPIO_PULLDOWN_ENABLE;
  cfg.intr_type=GPIO_INTR_DISABLE;
  gpio_config(&cfg);
  gpio_set_level(pin,0);
  gpio_set_drive_capability(pin, GPIO_DRIVE_CAP_2);
}
static void status() {
  const uint8_t message[5] = {'M','2','S','T',(uint8_t)(recording ? 1 : playing ? 2 : 0)};
  Serial.write(message, sizeof message);
}
static void usb_upload(char type, const void *payload, uint16_t size) {
  uint8_t header[7]={'M','2','U','P',(uint8_t)type,(uint8_t)size,(uint8_t)(size>>8)};
  uint32_t h=hash((const uint8_t *)payload,size,hash(header,7));
  uint8_t tail[4]; for (unsigned i=0;i<4;i++) tail[i]=h>>(8*i);
  Serial.write(header,7); if(size)Serial.write((const uint8_t *)payload,size); Serial.write(tail,4);
}
static void stop_play(const char *reason) {
  if (!playing) return;
  usb_upload('X',nullptr,0); playing=play_started=play_confirmed=false; relay(false); status(); text('L',reason);
}
static bool IRAM_ATTR lost(adc_continuous_handle_t,
                          const adc_continuous_evt_data_t *, void *) {
  overflow++; return false;
}
static void cleanup() {
  if (adc) { adc_continuous_stop(adc); adc_continuous_deinit(adc); adc = nullptr; }
}
static bool drain() {
  alignas(4) uint8_t frame[1024]; uint16_t pcm[256]; uint32_t bytes = 0;
  esp_err_t e = adc_continuous_read(adc, frame, sizeof frame, &bytes, 0);
  if (e == ESP_ERR_TIMEOUT) return false;
  if (e != ESP_OK) { overflow++; return false; }
  unsigned n = 0;
  for (unsigned i = 0; i + SOC_ADC_DIGI_RESULT_BYTES <= bytes; i += SOC_ADC_DIGI_RESULT_BYTES) {
    const auto *v = reinterpret_cast<const adc_digi_output_data_t *>(frame + i);
    if (v->type2.channel == channel) pcm[n++] = v->type2.data;
  }
  if (n) { packet('D', pcm, n * 2); samples += n; }
  return true;
}
static void stop(const char *reason) {
  if (!recording) return;
  // Bound draining so a failed/full UART cannot make the stop button hang.
  for (unsigned i = 0; i < 32 && drain(); i++) {}
  cleanup(); recording = false; relay(false); status();
  char end[160];
  snprintf(end, sizeof end, "{\"samples\":%lu,\"overflow\":%lu,\"reason\":\"%s\"}",
    (unsigned long)samples, (unsigned long)overflow, reason);
  text('E', end);
}
static void start() {
  stop_play("record"); relay(true); delay(20); // Let NC contacts open before ADC starts.
  adc_unit_t unit; adc_channel_t ch;
  esp_err_t e = adc_continuous_io_to_channel(0, &unit, &ch);
  if (e == ESP_OK && unit != ADC_UNIT_1) e = ESP_ERR_INVALID_ARG;
  if (e == ESP_OK) {
    channel = ch;
    adc_continuous_handle_cfg_t hc = {};
    hc.max_store_buf_size = 32768; hc.conv_frame_size = 1024;
    e = adc_continuous_new_handle(&hc, &adc);
  }
  adc_digi_pattern_config_t pattern = {};
  pattern.atten = ADC_ATTEN_DB_12; pattern.channel = channel;
  pattern.unit = ADC_UNIT_1; pattern.bit_width = ADC_BITWIDTH_12;
  adc_continuous_config_t cfg = {};
  cfg.sample_freq_hz = 16000; cfg.conv_mode = ADC_CONV_SINGLE_UNIT_1;
  cfg.format = ADC_DIGI_OUTPUT_FORMAT_TYPE2; cfg.pattern_num = 1; cfg.adc_pattern = &pattern;
  if (e == ESP_OK) e = adc_continuous_config(adc, &cfg);
  overflow = 0; samples = 0;
  adc_continuous_evt_cbs_t cb = {}; cb.on_pool_ovf = lost;
  if (e == ESP_OK) e = adc_continuous_register_event_callbacks(adc, &cb, nullptr);
  if (e == ESP_OK) e = adc_continuous_start(adc);
  if (e != ESP_OK) { cleanup(); relay(false); text('X', esp_err_to_name(e)); return; }
  recording = true;
  text('B', "{\"rate\":16000,\"format\":\"u12le\",\"channels\":1}"); status();
}
static void button(unsigned b, bool a) {
  if (a != candidate[b]) { candidate[b] = a; repetitions[b] = 1; }
  else if (repetitions[b] < 2) repetitions[b]++;
  if (repetitions[b] < 2 || stable[b] == a) {
    if (repetitions[b] >= 2 && !a) released[b] = true;
    return;
  }
  stable[b] = a;
  if (!a) { released[b] = true; return; }
  if (!released[b]) return;
  if (b==0) { if (recording) stop("button"); else start(); }
  else if (playing) stop_play("button");
  else {
    stop("button"); relay(false); delay(20);
    playing=true; play_started=play_confirmed=false; last_upload=millis(); status(); text('P',"latest");
  }
}
static void arm() {
  Serial0.println("MIC2 BAUD 460800"); Serial0.flush();
  Serial0.updateBaudRate(460800);
  delay(100);
  armed = true; recording=playing=play_started=play_confirmed=false; relay(false);
  memset(released,0,sizeof released); memset(stable,0,sizeof stable);
  memset(candidate,0,sizeof candidate); memset(repetitions,0,sizeof repetitions);
  upload_used=upload_expected=0;
  sequence = samples = rx_used = 0;
  last_keepalive = last_controller = millis();
  text('R', "2P A: record, B: replay"); status();
}
static void disarm(const char *reason) {
  stop(reason); stop_play(reason); relay(false); text('Q', reason); Serial0.flush();
  armed = false; Serial0.updateBaudRate(115200);
}
static bool poll() {
  if (!armed) return false;
  while (Serial0.available()) {
    int c = Serial0.read();
    if (upload_used || c=='M') {
      if (!upload_used) upload_begun=millis();
      upload[upload_used++]=c;
      if (upload_used==4 && memcmp(upload,"M2UP",4)) { upload_used=upload_expected=0; continue; }
      if (upload_used==7) {
        unsigned n=upload[5]|((unsigned)upload[6]<<8);
        if(n>516){upload_used=upload_expected=0;stop_play("bad_packet");continue;}
        upload_expected=n+11;
      }
      if (upload_expected && upload_used==upload_expected) {
        unsigned n=upload_expected-11; uint32_t h=hash(upload,7+n), expected=0;
        for(unsigned i=0;i<4;i++)expected|=(uint32_t)upload[7+n+i]<<(8*i);
        if(h!=expected)stop_play("checksum");
        else if(playing) {
          if(upload[4]=='X')stop_play("pc_stop");
          else {
            Serial.write(upload,upload_expected); last_upload=millis();
            if(upload[4]=='S')play_started=true;
          }
        }
        upload_used=upload_expected=0;
      }
    } else if (c == 'K') last_keepalive = millis();
    else if (c == 'Q') { disarm("pc_stop"); return true; }
  }
  if(upload_used && millis()-upload_begun>500) {upload_used=upload_expected=0;stop_play("packet_timeout");}
  if (millis() - last_keepalive > 3000) { disarm("pc_lost"); return true; }
  while (Serial.available()) {
    memmove(rx, rx+1, 11); rx[11] = Serial.read(); if (rx_used < 12) rx_used++;
    if (rx_used >= 8 && !memcmp(rx+4, "M2BT", 4) &&
        (uint8_t)~rx[8] == rx[10] && rx[11] == 0xa5 && rx[8] <= 3) {
      last_controller = millis(); button(0,rx[8]&1); button(1,rx[8]&2);
    } else if(rx_used==12 && !memcmp(rx,"M2FC",4) && rx[11]==0xa5) {
      if (playing) {
        packet('C',rx+4,7);
        if(rx[10]==1)play_confirmed=true;
        if(play_confirmed && rx[10]==3)stop_play("finished");
        else if(play_confirmed && rx[10]==4)stop_play("underrun_or_invalid_data");
      }
    }
  }
  if (recording) {
    drain();
    if (overflow) stop("overflow");
    else if (millis() - last_controller > 750) { stop("controller_lost"); memset(released,0,sizeof released); }
  }
  if(playing && (millis()-last_controller>750 || (play_started && millis()-last_upload>3000)))stop_play("connection_lost");
  delay(0);
  return true;
}
} // namespace micrec
