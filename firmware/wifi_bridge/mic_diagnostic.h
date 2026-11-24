#pragma once
#include "esp_adc/adc_continuous.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_timer.h"
#include <stdlib.h>

// Explicit UART-only diagnostic: ETX + "MIC1 <milliseconds>\n".
// GPIO0 is the user's AC-coupled, biased microphone input. No GPIO is driven.
// Capture into RAM first, then transmit: 115200 baud cannot stream 16 kHz PCM.
// The normal bridge is paused during this bounded command; no automatic recording.
namespace micdiag {
static constexpr unsigned PIN = 0, RATE = 16000, MAX_MS = 2000;
static volatile uint32_t overflows;
static bool IRAM_ATTR pool_overflow(adc_continuous_handle_t,
                                   const adc_continuous_evt_data_t *, void *) {
  overflows++;
  return false;
}

static void capture(unsigned ms) {
  const unsigned wanted = RATE * ms / 1000;
  auto *pcm = static_cast<uint16_t *>(malloc(wanted * sizeof(uint16_t)));
  if (!pcm) { Serial0.println("MIC1 ERROR memory"); return; }
  adc_unit_t unit;
  adc_channel_t channel;
  adc_continuous_handle_t adc = nullptr;
  adc_cali_handle_t cal = nullptr;
  esp_err_t error = adc_continuous_io_to_channel(PIN, &unit, &channel);
  unsigned got = 0;
  bool started = false;
  uint64_t elapsed = 0;
  if (error == ESP_OK && unit != ADC_UNIT_1) error = ESP_ERR_INVALID_ARG;
  if (error == ESP_OK) {
    adc_continuous_handle_cfg_t cfg = {};
    cfg.max_store_buf_size = 8192;
    cfg.conv_frame_size = 1024;
    error = adc_continuous_new_handle(&cfg, &adc);
  }
  if (error == ESP_OK) {
    adc_digi_pattern_config_t pattern = {};
    pattern.atten = ADC_ATTEN_DB_12;
    pattern.channel = channel;
    pattern.unit = unit;
    pattern.bit_width = ADC_BITWIDTH_12;
    adc_continuous_config_t cfg = {};
    cfg.sample_freq_hz = RATE;
    cfg.conv_mode = ADC_CONV_SINGLE_UNIT_1;
    cfg.format = ADC_DIGI_OUTPUT_FORMAT_TYPE2;
    cfg.pattern_num = 1;
    cfg.adc_pattern = &pattern;
    error = adc_continuous_config(adc, &cfg);
  }
  if (error == ESP_OK) {
    adc_continuous_evt_cbs_t callbacks = {};
    callbacks.on_pool_ovf = pool_overflow;
    overflows = 0;
    error = adc_continuous_register_event_callbacks(adc, &callbacks, nullptr);
  }
  if (error == ESP_OK) {
    error = adc_continuous_start(adc);
    started = error == ESP_OK;
  }
  if (started) {
    const int64_t begun = esp_timer_get_time();
    alignas(4) uint8_t frame[1024];
    while (got < wanted) {
      if (esp_timer_get_time() - begun > (int64_t)(ms + 1000) * 1000) {
        error = ESP_ERR_TIMEOUT; break;
      }
      uint32_t bytes = 0;
      error = adc_continuous_read(adc, frame, sizeof frame, &bytes, 200);
      if (error != ESP_OK) break;
      for (uint32_t i = 0; i + SOC_ADC_DIGI_RESULT_BYTES <= bytes && got < wanted;
           i += SOC_ADC_DIGI_RESULT_BYTES) {
        const auto *sample = reinterpret_cast<const adc_digi_output_data_t *>(frame + i);
        // C6 has one ADC unit; unlike S3 its result has no unit field.
        if (sample->type2.channel == (unsigned)channel)
          pcm[got++] = sample->type2.data;
      }
    }
    elapsed = esp_timer_get_time() - begun;
    adc_continuous_stop(adc);
  }
  if (adc) adc_continuous_deinit(adc);
  const uint32_t lost = overflows;
  if (error != ESP_OK || got != wanted || lost) {
    Serial0.printf("MIC1 ERROR capture code=%s samples=%u overflow=%lu\n",
                   esp_err_to_name(error), got, (unsigned long)lost);
    free(pcm); return;
  }
  uint64_t sum = 0;
  unsigned lo = 4095, hi = 0, clipped = 0;
  for (unsigned i = 0; i < got; i++) {
    unsigned v = pcm[i]; sum += v;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
    if (v <= 4 || v >= 4091) clipped++;
  }
  int dc_mv = -1;
  adc_cali_curve_fitting_config_t cc = {};
  cc.unit_id = unit; cc.chan = channel;
  cc.atten = ADC_ATTEN_DB_12; cc.bitwidth = ADC_BITWIDTH_12;
  if (adc_cali_create_scheme_curve_fitting(&cc, &cal) == ESP_OK) {
    adc_cali_raw_to_voltage(cal, (int)(sum / got), &dc_mv);
    adc_cali_delete_scheme_curve_fitting(cal);
  }
  const auto *bytes = reinterpret_cast<const uint8_t *>(pcm);
  uint32_t hash = 2166136261u;
  for (unsigned i = 0; i < got * 2; i++) hash = (hash ^ bytes[i]) * 16777619u;
  Serial0.printf("\nMIC1 {\"rate\":%u,\"samples\":%u,\"bytes\":%u,"
                 "\"dc_mv\":%d,\"min\":%u,\"max\":%u,\"clipped\":%u,"
                 "\"overflow\":%lu,\"capture_us\":%llu,\"fnv1a\":%lu}\n",
                 RATE, got, got * 2, dc_mv, lo, hi, clipped,
                 (unsigned long)lost, (unsigned long long)elapsed, (unsigned long)hash);
  Serial0.write(bytes, got * 2);
  Serial0.print("\nMIC1 END\n");
  Serial0.flush();
  free(pcm);
}

static bool poll(bool busy) {
  static bool receiving;
  static char line[32];
  static unsigned used;
  static uint32_t begun;
  if (!receiving) {
    if (swd_active || swd_uart_active || Serial0.peek() != 3) return false;
    Serial0.read(); receiving = true; used = 0; begun = millis();
  }
  if (millis() - begun > 1000) {
    receiving = false; Serial0.println("MIC1 ERROR command_timeout"); return true;
  }
  while (Serial0.available()) {
    int c = Serial0.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[used] = 0; receiving = false;
      if (!strcmp(line, "MIC2 RELAYCYCLE")) {
        micrec::relay(false);
        Serial0.printf("MIC2 RELAYCYCLE BEGIN gpio1=%d\n",gpio_get_level(GPIO_NUM_1));
        Serial0.flush();
        for(unsigned i=1;i<=3;i++) {
          micrec::relay(true);
          Serial0.printf("MIC2 RELAYCYCLE %u ON gpio1=%d\n",i,gpio_get_level(GPIO_NUM_1));
          Serial0.flush(); delay(2000);
          micrec::relay(false);
          Serial0.printf("MIC2 RELAYCYCLE %u OFF gpio1=%d\n",i,gpio_get_level(GPIO_NUM_1));
          Serial0.flush(); delay(2000);
        }
        Serial0.printf("MIC2 RELAYCYCLE END gpio1=%d\n",gpio_get_level(GPIO_NUM_1));
        return true;
      }
      if (!strcmp(line, "MIC2 RELAYOFF")) {
        micrec::relay(false);
        Serial0.printf("MIC2 RELAYOFF gpio1=%d uptime=%lu\n",gpio_get_level(GPIO_NUM_1),(unsigned long)millis());
        return true;
      }
      if (!strcmp(line, "MIC2 RELAYTEST")) {
        if (busy) { Serial0.println("MIC1 ERROR bridge_busy"); return true; }
        micrec::relay(true); delay(200); micrec::relay(false); delay(50);
        Serial0.printf("MIC2 RELAYTEST OK gpio1=%d uptime=%lu\n", gpio_get_level(GPIO_NUM_1), (unsigned long)millis());
        return true;
      }
      if (!strcmp(line, "MIC2 ARM")) {
        if (busy) Serial0.println("MIC1 ERROR bridge_busy");
        else micrec::arm();
        return true;
      }
      char *end = nullptr;
      unsigned long ms = used > 5 ? strtoul(line + 5, &end, 10) : 0;
      if (strncmp(line, "MIC1 ", 5) || !end || *end || ms < 100 || ms > MAX_MS) {
        Serial0.println("MIC1 ERROR command"); return true;
      }
      if (busy) { Serial0.println("MIC1 ERROR bridge_busy"); return true; }
      Serial0.printf("MIC1 CAPTURING %lu\n", ms);
      Serial0.flush();
      capture(ms);
      return true;
    }
    if (used == sizeof line - 1 || c < 32 || c > 126) {
      receiving = false; Serial0.println("MIC1 ERROR command"); return true;
    }
    line[used++] = (char)c;
  }
  return true;
}
} // namespace micdiag
