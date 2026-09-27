// FC-MAGICON 画面転送の Wi-Fi ブリッジ(ESP32-C6)。
//   PC ──Wi-Fi(TCP 5000番)── ESP32-C6 ──USB(C6 の USB Serial/JTAG)── RP2350(USB ホスト)
// 中身は見ずに、TCP で来たバイトを USB へ、USB で来たバイトを TCP へそのまま流すだけ。
// TCP がつながっていない間は、USB に 2 秒ごとに "fc-magicon wifi_bridge ip=..." を出す
// (カセットは "FCFR" を探して読むので邪魔にならない。PC の wifi_bench.py はこれで IP を知る)。
//
// ビルド: build_bridge.ps1(Arduino-ESP32 3.3、FQBN esp32:esp32:esp32c6:CDCOnBoot=cdc)
// Wi-Fi の SSID とパスワードは wifi_secrets.h に書く(wifi_secrets.example.h を写して。GitHub には上げない)。
#include <WiFi.h>
#include <ESPmDNS.h>
#include "esp_flash.h"
#include "hal/spi_flash_hal.h"
#include "hal/spimem_flash_ll.h"
#include "wifi_secrets.h"

// 手持ちの C6 N4 ボードはフラッシュを 80MHz で読むと化ける(パーティションテーブル 0x50AA が 0x500A / 0x502A になる、
// Wi-Fi の初期化が ESP_ERR_NOT_FOUND で失敗する)。Arduino の C6 用ライブラリは 80MHz 固定なので、
// フラッシュのドライバーが初期化された後・Arduino が NVS を読む前(グローバルのコンストラクター)に 40MHz(80MHz ÷ 2)に落とす。
// ブートローダーの方は FQBN の FlashFreq=40 で 40MHz になる(build_bridge.ps1)。
__attribute__((constructor)) static void flash_40mhz() {
  spi_flash_hal_context_t *h = (spi_flash_hal_context_t *)esp_flash_default_chip->host;
  h->clock_conf.spimem = spimem_flash_ll_calculate_clock_reg(2);
}

static const uint16_t TCP_PORT = 5000;
static WiFiServer server(TCP_PORT);
static WiFiClient client;
static uint8_t buf[4096];
static volatile int last_reason;        // 最後に切れた理由(Wi-Fi の reason コード。つながらない時の手がかり)

// つながらない時に、その SSID が見えているか・電波の強さ・暗号方式を USB に出す
static void report_scan() {
  int n = WiFi.scanNetworks();
  bool found = false;
  for (int i = 0; i < n; i++) {
    if (WiFi.SSID(i) == WIFI_SSID) {
      Serial.printf("  scan: %s ch=%d rssi=%d auth=%d\r\n", WiFi.SSID(i).c_str(), WiFi.channel(i), WiFi.RSSI(i), (int)WiFi.encryptionType(i));
      found = true;
    }
  }
  if (!found) Serial.printf("  scan: %s is not visible (%d networks)\r\n", WIFI_SSID, n);
  WiFi.scanDelete();
}

// 様子を UART0(ボードの UART の USB-C = USB-UART 変換チップ)へ 1 秒ごとに出す。USB(Serial)はデータ専用なので使えない
static uint32_t n_tcp_in, n_usb_out, n_usb_zero, n_usb_in;
static void debug_report() {
  static uint32_t last;
  if (millis() - last < 1000) return;
  last = millis();
  Serial0.printf("[%lus] wifi=%d ip=%s tcp=%d usb_conn=%d | tcp_in=%lu usb_out=%lu usb_write0=%lu usb_in=%lu\r\n",
                 (unsigned long)(millis() / 1000), (int)WiFi.status(), WiFi.localIP().toString().c_str(),
                 (int)(client && client.connected()), (int)(bool)Serial,
                 (unsigned long)n_tcp_in, (unsigned long)n_usb_out, (unsigned long)n_usb_zero, (unsigned long)n_usb_in);
}

// USB へ全部書く。RP2350 が読まない間は待つ(その間 TCP から読まないので、PC 側の送信が止まる)
static bool usb_write_all(const uint8_t *p, size_t n) {
  while (n) {
    size_t w = Serial.write(p, n);
    p += w;
    n -= w;
    n_usb_out += w;
    if (!w) {
      n_usb_zero++;
      debug_report();
      if (!client.connected()) return false;
      delay(1);
    }
  }
  return true;
}

void setup() {
  Serial0.begin(115200);                // 様子の表示(debug_report)
  Serial.setRxBufferSize(8192);
  Serial.setTxBufferSize(16384);
  Serial.begin(115200);                 // USB Serial/JTAG(速度の指定は意味を持たない)
  Serial.setTxTimeoutMs(20);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                 // 省電力を切る(切らないと受信が遅れる)
  WiFi.onEvent([](WiFiEvent_t, WiFiEventInfo_t info) { last_reason = info.wifi_sta_disconnected.reason; },
               ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  MDNS.begin("fc-magicon");             // fc-magicon.local で見つかるように
  MDNS.addService("fcbridge", "tcp", TCP_PORT);
  server.begin();
  server.setNoDelay(true);
}

void loop() {
  static uint32_t last_hello;
  debug_report();
  if (!client || !client.connected()) {
    client = server.accept();
    if (client) {
      client.setNoDelay(true);
      while (Serial.available()) Serial.read();   // つながる前に来ていた分は捨てる
    } else {
      if (millis() - last_hello > 2000) {
        last_hello = millis();
        if (WiFi.status() == WL_CONNECTED)
          Serial.printf("fc-magicon wifi_bridge ip=%s port=%u\r\n", WiFi.localIP().toString().c_str(), TCP_PORT);
        else {
          static int tries;
          Serial.printf("fc-magicon wifi_bridge connecting to %s (status=%d reason=%d)\r\n", WIFI_SSID, (int)WiFi.status(), last_reason);
          if (++tries % 5 == 0) report_scan();          // 10 秒ごとに周りを探す
        }
      }
      while (Serial.available()) {
        Serial.read();
        n_usb_in++;
      }
      delay(5);
      return;
    }
  }
  // PC → カセット
  int n = client.available();
  if (n > 0) {
    n = client.read(buf, n < (int)sizeof buf ? n : sizeof buf);
    if (n > 0) {
      n_tcp_in += n;
      usb_write_all(buf, n);
    }
  }
  // カセット → PC
  int m = Serial.available();
  if (m > 0) {
    m = Serial.read(buf, m < (int)sizeof buf ? m : sizeof buf);
    if (m > 0) {
      n_usb_in += m;
      client.write(buf, m);
    }
  }
  if (n <= 0 && m <= 0) delay(0);
}
