# 2026-10-12 ファームウェア修正

監査後に製品コードを修正し、合成入力による回帰テストとRP2350向けビルドを実行した。実機への書込みは行っていない。

## 変更

- CPU/PPU PIOは `pull block` の無期限待ちを廃止。bit31付きの返答を非ブロックで待ち、M2または/RDの有効期間が終われば出力を停止し、そのSMを停止ループへ入れる。古い返答を次サイクルへ流さない。期限超過後はファミコン電源を切って入れ直すかMCUを再起動する。FCのリセットボタンだけでは復旧しない。これは実機動作確認済みという意味ではない。追加命令による応答遅延と信号境界の余裕は要測定。
- MMC3のA12資格判定をPIO2 SM1へ移した。A12を継続監視し、Low期間内でM2下降3回を確認してからA12上昇をイベントとしてコア1へ渡す。読み出し回数の近似はホスト試験台にだけ残した。PIOはイベントFIFOを8段持つが、極端な処理停止時にイベントを失う可能性は残る。エッジ近傍のサンプリング、MMC3の種類によるIRQ差、CPU書込みとイベントの順序は実機テストROMで確認する。
- MMC3 $A001 のWRAM有効・書込み保護、およびMMC1 PRGレジスタbit4のWRAM無効を反映。
- $2000/$2005のtレジスタ更新を実装。通常の描画停止中のCHR転送に加え、監査で再現した内部状態の不一致を修正。ただし描画中のv更新・tからvへのコピーは未実装。現在の配線とCPUレジスタ横読みだけでは、この部分の完全互換を保証できない。CHR-RAMの描画中書込みは引き続き制限事項。
- cart_load時にPPU追跡、MMC1、MMC3、WRAM/CHR-RAM、書込み継続状態を初期化。
- 空のNSFを除数0になる前に拒否。
- 4画面VRAM、NES2の拡張マッパー/submapper/RAM指定/指数容量等はpackと本体双方で拒否。これらの機能自体を実装したわけではない。短いヘッダー、PRG空、切れたNESもpackで拒否。
- USB受信待ち中もaudio_pollを呼び、デバイスUSBのブロック読込みは最大1msごとに区切る。音声位置のuint32折返し比較も修正。DMA波形と長時間再生は未試験。

## 検証

- `firmware/tests/test_cart_audit.py`: PASS。実cart.cをZigでコンパイルし、PPU t更新、MMC3保護、MMC1無効、状態初期化、入力拒否を合成入力で確認。
- `firmware/tests/test_pio_logic.py`: PASS。実PIOソースの命令制御を簡易モデルで実行。正常返答、期限超過時の無出力、CPU書込み時の無出力、A12 Low期間の資格判定を確認。GPIO同期段・外部遅延・FIFO競合・実バスの電圧をモデル化していない。
- `firmware/tests/test_power_guard.py`: 3ケースPASS。
- pico-sdk 2.3.1 + GCC 15.2.1による `magicon` / `magicon_wifi` / `chr_test` / `bus_test` ビルド成功。PIO命令数の制約・PIOアセンブルも通過。

成果物は `firmware/out-protected/`。通常の `out/` は旧版の可能性があるため、今回の修正版を試す際は out-protected のUF2を使う。

実機動作は未確認。特にPIOの追加命令による応答時間、MMC3 IRQ、CHR-RAMの描画中アクセスは残る検証項目。

## 白画面の実機切り分け（追加）

ユーザー実機ではFC電源OFF時LED点滅、ON時点灯、画面白。COM11は認識されたが読み取れたデータは0byte。点灯はcart_startの直前であり、初期化完了の証明ではない。電源断時のPC接続音は電源保護のwatchdog再起動によるUSB再列挙と整合する。

PIOを有効化してからcore1を起動していた順序を修正。CPU/PPU PIOを停止状態で設定し、core1の準備通知後に有効化する。起動直後の無応答で期限超過停止する可能性への対処で、白画面の原因と断定したわけではない。

`build_protected.ps1 -Diagnostic` で `out-diagnostic/magicon.uf2` を生成。保存されたROMは変更せず、RAM上の内蔵テストROMを使い、cart_startの各段階とPIO PC/FIFO状態をUSBへ出す。診断版ビルドと既存回帰テストは成功。今回の起動順変更を含むUF2はout-diagnostic側。out-protectedの通常版はこの追加変更後にはまだ再ビルドしていない。

診断版を実機へ書込み照合成功。COM11でログを取得（diagnostic_usb_20261012.txt）。sense=1、M2は0/1に変化、継続カウンターcpu/ppu/writesは0。CPU PC29～31はプログラム配置offset8を加味すると期限超過停止ループに対応。PPU PC14～15はアドレス待ちループ（offset9）で、/RDはサンプル時High。バス初期化自体は完了したと判断できる。起動時M2が既にHighだと途中サイクルへ入る問題への対処として、次の完全なM2周期から開始するwait Lowを追加し、診断版を再ビルド・PIO回帰確認した。追加版はまだ実機に書いていない。

### 続く実機試験

- M2同期・CPU返答先行だけでは、初回CPU本体RAM読出し $00FF の後に期限超過停止した。TX FIFOに返答1件が残った。
- CPU読出し期限超過時は無出力で古い返答を回収・破棄し次周期へ再同期するよう変更。返答を既にpullした場合とまだ待っている場合を区別する。書込み超過は停止を維持。PIO命令モデルで再同期・書込み停止を確認。
- この版では約1518万CPUアクセス・341万書込みまで進んだが停止。PPUは8件で停止しTX FIFOに返答1件が残った。画面は崩れ、正常なROM実行と判断できなかった。
- CPU単独診断（FC_DIAG_CPU_ONLY=1、PPU出力無効）では約179万サイクル/秒を継続。既知の6502ループの$8000書込みは約250万件、連番エラー0。先頭32件のCPU処理計測は最大29cycles/250MHz=116ns。PIO起床・キュー待ち・外部信号遅延を含む総応答時間ではない。記録: diagnostic_cpu_only_20261012.txt。
- 次の診断はFC_DIAGNOSTIC=1、FC_DIAG_CPU_ONLY=1、FC_DIAG_SPLIT=1を同時指定。内蔵NROM専用。core0はCPU、core1はPPUに専念し、実行中は両コアの割込みを停止する。電源断検出はcore0のループ内GPIO46ポーリングで継続し、出力を隔離してからwatchdog scratchへ処理数・ループ確認・PC・PPU処理計測を保存して再起動する。OFF時のUSBログで結果を読む。これは製品用マッパー/USB同時動作の実装ではない。
- 分離版はout-split-diagnostic/magicon.uf2。ビルド・既存回帰テスト・実機書込み照合成功。分離版の実機結果はまだ未取得。

### 分離試験とライブ診断への移行

CPU0/PPU1ではPPU5～38件で停止。診断保存のscratch[4]がSDKのwatchdog_enableに上書きされることを確認し、使用しないよう修正。CPU1/PPU0に変更するとCPUループ約682万回・連番エラー0、PPUは初回で停止し最大630cycles。PPUの遅れた返答も出力せず回収・破棄して次周期へ再同期させると、PPU約7096万件の継続処理に改善したが、CPU連番エラー54件・PPU期限超過あり。表示は格子にならなかった。

固定FF CHRでもユーザー報告ではほぼ同じ表示に走るノイズが加わった。アドレス下位の誤読だけでは説明できないが、データ出力・タイミング・CPU初期化を特定した結果ではない。ロジックアナライザ・オシロはユーザー手元にない。

ユーザー希望によりFC_DIAG_LIVE=1、FC_DIAG_SPLIT=0、FC_DIAG_CPU_ONLY=1、FC_DIAGNOSTIC=1のライブ版を追加。CPUはcore1、固定FFのPPU応答はcore0 PIO1 IRQ0の最高優先度割込み、USB IRQは低優先度。ON中にUSBログを読む設計。handler_cyclesはIRQ発生からの総遅延ではない。out-live-diagnostic/magicon.uf2をビルド・PIO回帰確認・書込み照合成功。ライブ版の実機動作はまだ未確認。

### PIO単独固定応答版

ライブ版はON中ログ取得に成功。本体RESET後にCPUテストループは進むが、連番不一致とPPU期限超過が残り、固定FFでも表示が崩れた。以前ユーザーが押していたRESETはRP2350モジュール側だったことも確認。本体RESETとモジュールRESETを区別して試験する。

ネット調査をwhite_garbled_screen_research_20261012.mdへ保存。続いてFC_DIAG_DIRECT_CHR=1を追加し、ppu_constant.pioで/RD LowかつA13 Lowの間にFFを出す。CPU/FIFO/割込み返答待ちとアドレス下位捕捉は使わない。/RD Highで入力方向へ戻し、ネームテーブルでは出力しない。USBログはON中も使える。PPUカウンターは更新されず0となるため、それを停止と解釈しない。

out-direct-pio-diagnostic/magicon.uf2をビルド、PIOモデルで固定FF方向・ネームテーブル非駆動を確認、カートリッジ回帰もPASS。実機結果は次の試験待ち。これは通常ROMを処理する製品版ではなく、出力経路と応答時間を切り分けるNROM診断版。

PIO直接固定FFの実機試験では、ユーザー画像で細かな文字状ノイズが消えて塗りつぶしの色ブロックとなった。固定FFとして期待する形状と一致する方向の改善。データをPPUへ有効に供給できる条件を作れたと判断できるが、全配線・電圧余裕・通常CHRアドレス捕捉を保証するものではない。

その時のUSBログはCPU累計23,214,244、テストループ1,544,651回、連番不一致10、以後CPU/writesの増加0、CPU PC31（書込み期限超過の停止）を確認。PPUは独立PIOで表示を継続し、PPUカウンター0はこの版の仕様。PPUの改善とCPUの継続動作は分けて評価する。ARM/FIFO往復を外す変更は有効だったが、A13の判定タイミングも変更しているため、改善をARM処理時間だけの原因と断定しない。次の課題はCPU書込み捕捉の安定化と通常CHR応答方式。

### CPU write capture independent of ARM ACK
- cpu_m2.pio now classifies reads/writes from the preserved header snapshot and explicitly pushes RX words (autopush disabled).
- Writes capture data at M2 falling before draining the ARM ACK; no output drive occurs on writes. PPU fixed-FF direct response retained.
- PIO model tests cover delayed write ACK, data changing before M2 falling, and write/read resynchronization. Cart regression tests and RP2350 build passed. Model does not simulate electrical delays or FIFO backpressure.
- UF2 loaded and flash verification passed for device EF5E4EB554097CDF; picotool requested return to application mode. COM11 opened successfully with FC OFF; no serial text received in the 3-second window. Real-console execution remains to be checked.

### Real-console result after independent CPU write capture
- Screen remains clean filled squares (expected for constant FF CHR response).
- Five live samples: CPU 1,789,927 to 1,790,866 accesses/s, writes about 358,000/s. loop_marks rose from 3,141,454 to 3,618,988, about 119,000/s. CPU no longer remained halted as in prior run.
- sequence_errors rose from 8 to 9 within the observation window; therefore CPU read/write accuracy is still imperfect. This counter alone does not distinguish sampled write corruption from CPU execution/read errors.
- PPU counter zero is expected for PIO-only constant response. This does not yet validate address-dependent CHR ROM reads.

### Direct PPU A8 diagnostic
- Replaced constant FF with FF when A8=0 and 00 when A8=1. GPIO34 is PPU A8, not multiplexed AD0. This validates only A8-dependent output, not low-address capture or actual CHR ROM lookup.
- Built-in sequential tile numbers should yield alternating filled/blank groups of 16 tiles. Both bitplanes receive the same byte.
- A13-high nametable accesses remain undriven. Instruction-model tests verify both output bytes and nametable exclusion; build passed. Model does not prove electrical timing.
- UF2 flash load and verification succeeded; picotool requested application reboot. Awaiting real-console screen result.

### A8 real-console result
- User photo shows left half filled coloured blocks and right half uniform blank. This matches sequential 0..255 tile numbers: each tile row contains 32 tiles, and A8 changes between tiles 15/16. Supports A8-dependent data output but does not establish full CHR address capture or ROM response.
- Three USB samples: CPU 1.790M accesses/s and loop about119.2k/s. CPU continues running.
- sequence_errors 16004 ->16202 ->16420, around200/s, much higher than the prior short observation. Cause unproven; counter cannot distinguish write-data capture, missed cycles, or CPU read/execution faults. This must be investigated before claiming stable CPU bus service.

### CPU marker error records
- First eight marker sequence errors retain expected/actual bytes, raw write header/data, previous marker raw data and marker index. Records publish after a memory barrier and remain immutable; USB prints repeat for later connection.
- A8 FF/00 PPU response and CPU PIO timing unchanged. Records add bounded work on the first eight errors, so diagnostics can perturb timing; they do not constitute an electrical trace.
- Cart regression tests passed; final RP2350 build and picotool flash verification passed. Awaiting FC ON test.

### Error-recording diagnostic first observation
- User reports same screen. USB samples show CPU bus ~1.790M/s, writes~413k/s, but loop_marks frozen at23 with zero recorded marker errors.
- Therefore bus activity does not imply intended diagnostic program is executing. Intended marker loop stopped or execution departed before an additional $8000 marker arrived. No error records available; zero sequence_errors is not a successful result.
- Need reset of console CPU and fresh observation without firmware change to distinguish restart behavior from recurring loss of execution. PPU can preserve the prior screen while CPU executes elsewhere.

### Console reset of error-recording diagnostic
- After user pressed console RESET, loop_marks increased from23 to48 then stayed48 over four samples. CPU bus remains1.790M/s, writes413k/s, sequence_errors0.
- Reset restarts the intended loop briefly (25 additional markers), but sustained execution again fails. Marker-only error detection misses a failure with no subsequent marker.
- Diagnostic instrumentation may perturb service timing; cannot attribute this to hardware alone or claim the preceding CPU bus counts proved correct execution. Next diagnostic should capture a bounded snapshot of unexpected CPU addresses after loop entry and avoid extra work on every marker where possible.

### Unexpected CPU-address trace diagnostic
- After the first marker, reads other than internal $00 or ROM loop offsets $0070-$0079 trigger a one-shot trace: previous header/reply, unexpected header/reply, then14 further cycle headers/replies. Raw replies are queued values, not electrical observations or CPU PC. Console reset/interrupt reads can also trigger; first capture remains retained.
- Trace is recorded after ACK and after initial32 service-duration measurements. Stores cease when16 records collected; detection itself still adds CPU work and can perturb timing. USB prints immutable records repeatedly for later connection.
- Host tests of actual cart.c pass: initialization ignored, normal loop allowed, first departure and preceding header retained, capture capped16. Cart regressions and PIO tests pass. RP2350 build and flash verification passed; application reboot requested. Awaiting real-console test.

### Address trace result and interpretation
- Screen arrangement changed; loop_marks stayed3, stat_wr stayed12229, while bus reads continued~1.79M/s. Not successful diagnostic execution.
- Captured header/reply pairs:
  8b40784c/8000ff70, 03807000/80000000, 17807000/80000000,
  03807100/80000000, 63800003/80000000, 1a800003/80010000,
  2a800003/80010000, 67407906/8000ffc0, 4b407ac0/8000ff40,
  03407b40/8000ff0f, 1b407c0f/8000ff30, 03407d30/8000ff16,
  6f9630ff/80000000, 1a9630ff/80010000, ea9630ff/80010000,
  73407efe/8000ff2a.
- First record is ROM $C078, reply70. Then reads $0070 twice/$0071/$0000 and two writes to$0000, followed by ROM$C079. This pattern is consistent with unofficial opcode03 SLO($70,X), not the intended JMP4C at$C077. The most recent marker byte was03, so a missed/late opcode response leaving preceding write data on the bus is a plausible cause. This is inference, not a measured opcode or proof of open bus.
- ARM queued replies do not prove data arrived before CPU sampling. Added marker bookkeeping can delay service of immediately following opcode read. Prior32-startup-cycle DWT timing does not cover that transition. Prior suggestion of bus-release hold timing remains a hypothesis, not an established cause.

### Lightweight built-in NROM diagnostic write handling
- In CPU_ONLY + DIRECT_CHR diagnostic builds, bus_loop now consumes writes with diag_nrom_bookkeeping instead of the general cpu_access/cpu_write mapper/PPU/WRAM path. It only counts cycles/writes and $8000 markers, compares sequence and clears write-pending state. The first-eight marker-detail capture is bypassed; unexpected-address trace remains.
- This is a synthetic-NROM timing experiment, not general cartridge support or a demonstrated fix. Production and other diagnostic modes retain their general mapper/WRAM/PPU behavior. PIO read/write timing and A8 FF/00 output unchanged.
- Tests pass for write header/data pairing, marker wrap and mismatch, unrelated writes and reads, bounded trace, general cart regressions and PIO behavior.
- Final RP2350 build passed; bus_loop still in SRAM. UF2 flash verification passed and application reboot requested. Awaiting console power-on test. Initial32-cycle latency metric still does not measure worst-case steady-state response.

### Lightweight NROM initial real-console success
- Four samples after power-on: loop_marks2736069 ->3094344, about119.4k/s, sequence_errors0, no unexpected-address trace. CPU bus~1.790M/s, writes~358k/s.
- This contrasts with prior3/23/25-marker failures and supports software service timing/bookkeeping as a contributor. It does not establish full mapper support, address-dependent CHR ROM service, or an electrical timing margin.
- Longer observation log stored in diagnostic_nrom_fast_20261012.txt; assess its terminal counts for follow-up.
- Additional20-second observation ended at loop_marks7510726, sequence_errors0 and no unexpected-address trace. This run confirms sustained intended loop execution in the tested diagnostic, rather than bus activity alone.

### Direct pre-/RD A0 stripe diagnostic
- PPU direct PIO now retains an older sample that preceded the last /RD-high check. A0 and A13 are extracted from that same sample. A0=0 returnsFF, A0=1 returns00; both bitplanes equal, so expected pattern is alternating one-pixel horizontal lines across all tiles. A8 selection removed.
- Initial model test exposed final MOV sampling after /RD falling; using the previous verified sample fixes this modeled race. Three-instruction sample loop at250MHz=12ns; this is not proof of physical AD address validity relative to U2-shifted /RD.
- No ARM/FIFO round trip; nametable remains input. PIO checks /RD before output setup to abandon already-expired reads. CPU lightweight NROM path retained.
- Tests pass for address/data inversion at read start, same-snapshot A13 exclusion, consecutive reads, short expired reads and eight edge phases with both A0 values. PIO build passed and UF2 flash verification succeeded; application reboot requested. Awaiting screen and CPU-loop checks.

### A0 stripe real-console result
- User photo shows fine horizontal lines within coloured blocks across both halves, consistent with programmed A0 FF/00 rows. This supports sampled A0 affecting PPU data; photo alone does not prove one-pixel phase or every address bit.
- Four USB samples: loop_marks7630546 ->7988720, sequence_errors0, no CPU trace. CPU~1.790M/s, writes~358k/s. Log: diagnostic_ppu_a0_20261012.txt.
- This remains a synthetic stripe diagnostic, not full CHR ROM reads or a playable game. Next step must validate remaining address/bitplane handling and actual CHR-data response while retaining lightweight CPU service.

### Correction of A0 interpretation and unambiguous A2 diagnostic
- User observed prior A0 photo essentially identical to an earlier13:32 screen. Fine photographed lines cannot distinguish synthetic A0 response from television scanlines/camera artefacts. Withdraw the prior A0-success interpretation: A0 capture remains unconfirmed. Sustained marker-loop logs are valid CPU diagnostic evidence only.
- New direct PIO selects FF/00 with pre-/RD A2, giving four white pixel rows/four black rows per8-row tile if working. Both bitplanes equal. Built-in ROM palettes at mirrored$807B/$C07B made identical black/white for all attributes to remove coloured-block ambiguity. No flash ROM-slot modification.
- PIO model tests cover A2 address/data inversion, edge phases, nametable exclusion, expired/consecutive reads. Actual cart tests verify both mirrored palettes and unchanged JMP bytes. Tests and RP2350 build pass; UF2 flash verification passed and application reboot requested. Awaiting real screen, not claiming PPU success before it.

### A2 black/white screen observation
- Photo clearly differs from prior coloured blocks: repeated full-width black/white horizontal bands. Intended four white pixel rows/four black pixel rows repeat every8, yielding roughly30 white bands in240 visible rows, not four bands across the screen.
- Supports address-dependent A2 response. Does not verify A0 or entire CHR-address capture/ROM lookup. Dark upper region in photo needs distinction between real display defect and capture artefact before declaring full-screen correctness.
- USB loop_marks8943193 ->9301370, sequence_errors0 and no unexpected-address trace. Log diagnostic_ppu_a2_bw_20261012.txt. Intended CPU loop continues during PPU stripe output.

### Confirmed A2 bands and A0-A2 triangle diagnostic
- User confirms bands display correctly to the eye; dark region was photograph artefact. A2 diagnostic succeeded in intended display; A0 and full CHR lookup remain unverified.
- New PIO computes low-byte FF>>row for sampled A0-A2 row0..7: FF,7F,3F,1F,0F,07,03,01. Both planes equal, with uniform black/white palettes: expected repeated white right triangles/staircase diagonal edges on black. No ARM/ROM lookup yet, nor A3-plane distinction.
- Model tests cover all8 rows with post-/RD AD inversion,8 edge phases (46 ticks/184ns pulse), same-snapshot A13 exclusion, short expired reads and successive reads. Variable row calculation increases response time; physical margin remains unmeasured. Default model IN-source bug corrected to support actual Y-source input.
- PIO tests and RP2350 build pass; UF2 flash verification passed; application reboot requested. Lightweight CPU bookkeeping retained. Awaiting screen and CPU-loop log.

### Triangle diagnostic real-console failure
- User photo shows distorted repeated motifs, not confidently uniform intended right triangles. Do not claim A0-A2 success.
- CPU loop continues8.9M->9.15M with sequence_errors1. Saved trace at mark346656 shows reads$00FF, stack-page reads and reset-vector$FFFC/$FFFD followed by$C000 initialization. This resembles a reset sequence; may be an intentional console RESET or an external reset, not sufficient to label CPU instruction corruption. Need user reset history.
- Variable row-shift loop adds21 instruction cycles/84ns between row0 androw7. Model timings do not include input synchronization, output delay or console data-sampling instant. Even a write before/RD release can be too late for PPU sampling. Next experiment should use constant-time output generation with the same sampler, rather than attribute the failure solely to address capture.

### Fixed-time triangle diagnostic
- User confirms one console RESET during previous run: reset-vector trace and one marker discontinuity are consistent with this intentional action, not evidence of CPU crash.
- Replaced per-row shift loop with dynamically encoded OUT NULL,(8+row), injected via MOV EXEC. Constructed instruction6068|row and OSR FF00 produce the same FF>>row low byte. SDK pio_instructions.h confirms OUT opcode6000 and NULL destination3. Same address sampler, palettes and lightweight CPU path retained.
- Instruction model includes one additional cycle for injected instruction. All8 rows now enable output96ns after the modeled/RD edge at the tested phase vs prior68..152ns. This excludes electrical/synchronizer delay and does not prove PPU sampling margin.
- Persistent tests require identical enable time for all8 rows at each of8 edge phases, correct bytes, pre-read sample usage, nametable exclusion and bounded/expired reads. Tests/build pass; flash load and verification succeeded and application reboot requested. Awaiting real-console comparison.

### Fixed-time triangle real-console result
- Photo and user report show some correct triangles, other motifs distorted/waving. Constant instruction count did not eliminate rendering faults. Do not claim A0-A2 sampling verified, or attribute distortion exclusively to variable response delay.
- USB: loop_marks54288270 ->54527048, sequence_errors0, no unexpected-address trace. CPU diagnostic loop remains sustained; PPU rendering path is the next focus, though counters do not prove every CPU/PPU interaction correct.
- Log diagnostic_triangle_fixed_20261012.txt. Next discriminating experiment: fixed F0 byte with identical sampler/response instruction count, producing uniform vertical four-white/four-black pixel stripes. This distinguishes low-address-dependent generation from data bus/delivery faults better than fixed FF/00, which cannot show individual bit corruption clearly.

### Fixed F0 comparison prepared, flash NOT executed
- Same instruction count/output sequencing as fixed-time triangles. Encoded6068 OUT NULL,8 and constructedF000 produce fixedF0 irrespective of sampled row. Both planes equal: expected4 white/4 black pixels horizontally, forming vertical stripes.
- Sampler/A13 classification, release timing, palettes and CPU path unchanged. Direction-mask assertion remainsFF; data-output assertions expectF0. Local PIO model tests pass.
- Escalated build/flash command was NOT executed: automatic approval review failed due account usage limit, explicitly not a safety rejection. No new build or flash success claimed. Device retains previous fixed-time triangle firmware; console should remain OFF pending resumed approved build/flash.

### Fixed F0 diagnostic resumed and flashed
- User explicitly resumed after permissions changed. PIO tests passed again, but build failed because temporary source CMakeLists.txt was missing. No flash executed at this stage.
- Restoring temporary build sources before retrying; do not claim new firmware flashed until verification succeeds.

- Temporary source files restored from workspace (excluding wifi_bridge/secrets). Retry build succeeded, fixedF0 UF2 flash verification passed. Device was already in BOOTSEL so explicit picotool reboot executed successfully. Awaiting console ON test.

### Fixed F0 display result
- User reports same noise as triangle mode; photo shows broadly correct vertical stripes with white dots in black stripes and jagged/missing edges. Fixed data ignoring A0-A2 also fails, so low-address sampling alone is insufficient to explain rendering faults.
- Same-time fixedF0 experiment does not distinguish late effective data delivery, direction/release timing, A13 qualification, bit integrity, or display chain artefacts. Next comparison should keep fixedF0 but substantially reduce response instructions. No hardware defect concluded solely from image.
- USB observation saved to diagnostic_fixed_f0_20261012.txt.

### Fast fixed F0 diagnostic flashed
- Removed encoded-OUT construction, FF00/F000 staging and MOV EXEC; now constructF0 with SET Y,30/MOV ISR,Y/IN NULL,3/MOV OSR,ISR. Same sampler/A13 classification, read-expiry check, output ordering and release instructions; reduces response by10 modeled cycles40ns vs prior fixedF0.
- FixedF0 instruction-model tests pass for all rows/edge phases, nametable exclusion, successive/expired reads. Build and flash verification passed; picotool requested application reboot. Awaiting console ON screen comparison.

### Fast fixedF0 successful display, fastA0 checker flashed
- User confirms clean fixedF0 vertical stripes and console alreadyOFF. Same fixed byte/sampler/release with shorter preparation removed visible defects: strong evidence of response/delivery timing contribution, not proof of exact PPU deadline or complete electrical correctness. No liveCPU log since consoleOFF.
- Saved successful UF2 as out-direct-pio-diagnostic/magicon-fast-f0-confirmed.uf2 and PIO as ppu-fast-f0-confirmed.pio before changes.
- New short diagnostic returnsF0 on even A0 rows,0F on odd rows, equal branch length. Expected four-pixel-wide, one-pixel-high black/white checker cells across screen. Model output enable68ns vs fastfixedF0 56ns at previous phase; excludes electrical delay. Verifies only A0 if screen correct, not allCHR address bits.
- PIO tests pass all8 sampled rows/eight phases, equal enable timing, pre-read address selection, nametable exclusion and successive/expired reads. Build/flash verification passed; picotool requested application reboot. Awaiting userON image.

### Fast A0 screen matches; fast A1 diagnostic flashed
- User supplied uniformly repeated fine black/white checker photo and confirmed consoleOFF. Image matches A0-checker expectation, unlike distorted triangles. Supports correct A0-dependent output in this diagnostic; no liveCPU check after shutdown, and no fullCHR claim.
- Saved A0 UF2/PIO as magicon-fast-a0-checker.uf2 and ppu-fast-a0-checker.pio.
- Next mode selects F0/0F using A1, adding one OUT NULL,1 instruction (4ns modeled). Expected cells4 pixels wide and2 pixels tall, twice the A0-mode height. Equal branch lengths, other sampler/output/release and CPU behavior unchanged.
- PIO tests for all8 rows/eight phases, equal output timing, address/data inversion, exclusion/expired/consecutive reads pass. Build and UF2 verification passed, application reboot requested. Awaiting real image.

### A1 matches and user image-display objective
- User reports A1 checker appears successful, supplies uniform photo and confirmsOFF. Saved magicon-fast-a1-checker.uf2/ppu-fast-a1-checker.pio. User requests JN7xCleD_400x400.jpg displayed on actual console once feasible; found and visually inspected FC-MAGICON/JN7xCleD_400x400.jpg. Do not mark image displayed: arbitraryCHR response still required. Existing remote_pc.py/nesframe encoder available.
- Next fast A3 diagnostic returnsF0 for low pattern plane,0F for high plane at identical short branch timing. All four palettes now black/white/gray/black. Expected four-pixel-wide white/gray vertical stripes; if planes not distinguished, palette3 black helps expose failure.
- Tests cover all16 low-address values, post-read data changes,8 edge phases, nametable exclusion, equal timing and mirrored palette/loop preservation. Regression/PIO tests and build pass. UF2 verification passed and application reboot requested. Awaiting real image.

### A3 successful; DMA-backed lookup and image assets
- User confirms perfect white/gray stripes, supplies photo, consoleOFF. Saved magicon-fast-a3-plane.uf2/ppu-fast-a3-plane.pio. Supports distinct A3 bitplanes with fast output, not complete image display.
- New FC_DIAG_DMA_CHR diagnostic: ppu_lookup.pio retains verified pre-/RD snapshot, excludes A13, forms a32-bit pointer into32K-aligned8192-word table with 13 address bits and2 alignment bits. DMA RX channel writes pointers to another channel READ_ADDR_TRIG; single-word SRAM reads return FF00|data through TX. No ARM per-access response. Late answers drained/discarded while bus input.
- Initial tableFF>>(address&7) recreates triangle bytes, both planes equal; palettes restored black/white. Synthetic table tests do not yet exercise image/mapper updates. Requires physical timing validation. SDK confirms READ_ADDR_TRIG reload/start and endless-mode encoded transfer count. ELF table20008000, size8000; image table pointer confinement tested with addresses0..8191 including boundaries.
- Model tests validate pointers/data, nametable exclusion and late response discard; they model supplied FIFO replies, not DMA arbitration/electrical behavior. RP2350 build and flash verification passed, application reboot requested.
- prepare_static_image.py generated JN7xCleD CHR/nametable/palette and preview in out-image-diagnostic:128x128 centered64,56, four gray levels,174 unique tiles. Decoded every pixel from generated tile data to verify round trip; preview inspected. Assets NOT uploaded/displayed on console yet. Twifork Python lacksPillow; used bundled workspace Python.

### DMA triangle display still distorted; early-request variant prepared
- Photo shows correct triangle columns interspersed with malformed columns; user reports jagged/distorted. Not success. USB3-second capture had no text, so no current CPU correctness claim.
- Prepared variant starts SRAM lookup immediately after verified address capture, overlapping DMA with A13 classification instead of waiting for classification. Nametable accesses now also request a lookup but discard result without output. Tests verify pointer boundaries/bytes, nametable request-without-drive and late response discard.
- Local PIO tests pass. NOT FLASHED: awaiting consoleOFF. User image assets remain ready but real-console image display is pending stable arbitrary-data response.
- Early-request DMA variant: user confirmedOFF; RP2350 build and flash verification succeeded, picotool requested application reboot. Awaiting same triangle screen comparison without consoleRESET. No image-display success claim.

### Early DMA triangles successful; requested image firmware flashed
- User confirms success andOFF; photo shows uniform triangle pattern. Saved confirmed DMA triangle UF2/PIO. Lookup success now supports proceeding to arbitrary image test, not all mapper/general-game support.
- prepare_static_image.py now emits complete NROM image PRG, CHR, nametable, palette, NES and generatedstatic_image.h. PRG disablesPPU/APU, initializesmarker RAM, waits2vblanks, loads16palette bytes and1024nametable bytes, enablesbackground and enterssame10-byte marker loop. Gray128x128 image centered64,56 uses174tiles. Host tests actual cart.c verify mirroredPRG/all8192CHR bytes/resetvectors/loopbounds; image decode verifies everypixel.
- FC_DIAG_IMAGE selects generatedPRG/CHR without changing external ROM slot. EarlyDMA table populatedfromstatic_image_chr. Palettes suppliedbygeneratedROM; prior diagnostic palette patch skipped. Tracebounds adaptedtogeneratedloop. PIO sampler/DMA timing unchangedfromsuccessfultriangleversion.
- PIO tests, hostimageaudit and RP2350build pass. magicon-image.uf2 flashverification passed and picotool requestedapplicationreboot. Actualimage display awaitsconsoleON/photo; do not claim displayedyet.

### Requested image displayed successfully on real console
- User confirms success with recognizable JN7xCleD portrait photo, consistent with128x128 grayscale preview. Saved confirmed imageUF2. Actual image-display objective achieved for this diagnostic.
- User now requests game execution. Next target is fixedCHR NROM/mapper0: generic ROM loading and CPU WRAM/NMI/sprite behavior need verification. Static image/marker diagnostic alone is not proof of arbitrary games/mappers working. Console power state not yet confirmedOFF for next flash.

### First game attempt: F1 Race NROM
- User authorizes selecting ROM from FC/FC-ROM and confirmsOFF. Header scan identified f1race/mario/pacland/xevious as mapper0 with8KCHR-ROM. Selectedf1race.nes becausePRG16K (others32K), fixed8KCHR, verticalmirroring.
- FC_DIAG_NROM_GAME loads normal flashROM instead of forcingfallback, fillsDMA lookup fromloadedCHR and useslightweightCPUwrite path withWRAMenabled/protected handling. Syntheticmarker/trace checks bypassed to avoid falsegameerrors; nativeconsole handles internalRAM/PPU/APU/controllers. Mapperbanks/CHR-RAM are not supported by this fixedtable gameexperiment.
- PIO/generalcart tests and RP2350 build pass. f1race ROM packed, loaded0x10800000 and verified. First firmware command raced device reboot; retryaftersettling succeeded, verificationpassed and applicationreboot requested. Firmware savedmagicon-nrom-game.uf2; confirmedimagefirmware retained.
- Awaiting consoleON title/gameplay/sound/controller observation. Do not claim game execution succeeded before real result.

### F1 Race title works, gameplay crash
- User reports perfect audio/video then crash duringplay; deliberately leavesconsoleON. USB logs saveddiagnostic_f1_crash_20261012.txt: CPU1.79M/s reads continue but writes0/s, stat_wr frozen1269168. CPU PIO PCs change, so bus frontend not simplyhalted. Actual CPU executedinstructionunknown. Marker/sequence metrics inactiveingamemode, not proof ofcorrectness.
- PreparedNOTFLASHED CPUtimingtest: reduce decoderwait80ns->40ns at250MHz (nominal33ns /ROMSELdecode source inpriorreport; physical marginnotmeasured), latchlate-readACK flag inPIO0IRQ0 (includesundriveninternalreads), and exposeone lastheader snapshotafterACK forcrashaddressdiagnosis. IRQflagdoesnotcounterrorsnorproverequiredROMreplymissed. AddsonePIOinstruction; instructionmodeltestspass. PPUearlyDMAunchanged.
- Await consoleOFF beforebuild/flash. AskeduserwhethercrashSTARTimmediateorduringdriving and screen/audio state.
- CPU40ns wait/lateACK diagnostic build passed and artifact savedmagicon-nrom-game-m2fast.uf2. Notflashed; currentcrashedconsoleleftunchanged.
- User clarifies crashafterdrivingbriefly: picturefreezeswithoutcorruption, engineaudioheld. CPUexecutionstallconsistentwithread-onlybuslogbutrootcausenotproven.
- User confirmsOFF; CPU40ns wait/lateACK/lastheader diagnosticUF2 loadedandverified, applicationrebootrequested. F1RaceROMunchanged. AwaitrepeatgameplaywithoutconsoleRESET; ifcrashesleaveONforlog.

### F1 Race gameplay success; Mario ROM loaded
- User confirms F1Race gameplay works with CPU40ns-wait diagnostic; duration/comprehensivegamecoverage not specified. Supports improved CPU response margin, not universalmapper support.
- User requests SuperMarioBros and confirmsOFF. PackedFC/FC-ROM/mario.nes: mapper0 NROM, PRG32K, CHR8K, verticalmirroring. LoadedROMslot0x10800000, flashverificationpassed, applicationrebootrequested. WorkingCPU40ns + earlyDMAgamefirmwareunchanged. Awaiting Mario realgameplay result.

### MMC3 Mario3 experimental game build
- User confirms Mario1 played through1-2 withoutissues, authorizesMMC3/Mario3 andOFF. mario3.nes header mapper4, PRG256K, CHR128K, horizontalinitialmirror; fits384K ROM SRAMbudget.
- Reviewed MMC3 specification https://www.nesdev.org/wiki/MMC3 and https://www.nesdev.org/wiki/Programming_MMC3 plus fc-pico DMA/PIO source references. Public sources explainbank/IRQbehavior; no claimexistingRPcartridgeimplementationdirectlysolvesourtiming.
- FC_DIAG_MMC3_GAME provides shortPRG/CHRpointerupdates forpower-of-twoROM sizes. CPUcore1 updatesMMC3registers, immediatePRGpointers, WRAMenable/protect andIRQregisters; PIO2SM1 qualifiedA12 monitor suppliesIRQclockevents. PassiveRDmonitor skippedforMMC3 toavoidSM1/programmemoryconflict.
- Core0 foreground compares8CHRslotpointers and expandschanged1Kslots into32KDMAlookupwindow. This is asynchronous: bankswitchlatency and partiallyupdatedslotscanstillproduceglitches, particularlymid-render. Doesnotclaimcycle-accurate/fullMMC3support. Core0 foreground preventsusualperiodicUSBstatusprinting; USBIRQ stillenabled/powerguardstillactive. ROMbankchangesduringstartupnotmissedbecausecachedsourcesstartNULL.
- audit_mmc3_game.c verifies256fastmappingcombinationsagainstexistingmapper implementation, reload/IRQdisable andWRAMprotection; PIOtests pass. Buildpasses. Mario3ROMslot andMMC3firmwareloadedandverified; applicationrebootrequested. Savedmagicon-mmc3-game.uf2; NROM/imagebackupsretained. Awaittitle/map/course/split-screenrealtest.

### First MMC3 attempt gray; revised core split prepared
- User reports gray-onlyscreen andconsoleON. USBcapturediagnostic_mmc3_gray_20261012.txt containsno text. Core0foregrounddoesnotproduceperiodiclogs, so graycause/CPUstateunknown.
- Review found CHR inversion handling stillcomputedallslotpointersinCPUcore1 andcore0continuouslypolledSRAM. Prepared revision: CPUcore1 onlymarksCHRgenerationandSEV; core0calculatesCHRmapping/refillschangedslots, WFEwaitsbetweenupdates. SharedMM C3select/registerbytesvolatile; DMBbeforewake. PRGupdatesremainimmediate. This is timing/contentionexperiment, not provenrootcause/fix.
- FastmappingtestsupdatedtoexplicitlydeferredCHRwork;256mappingcases,IRQ/WRAMtests andRP2350buildpass. Savedmagicon-mmc3-wfe.uf2. NOTFLASHEDpendingconsoleOFF.
- UserconfirmedOFF; MMC3deferredCHR/WFErevisionloadedandverified, applicationrebootrequested. Mario3ROMunchanged. AwaitfirststartupwithoutRESET; graycauseunconfirmed.

### DeferredCHR revision stillgray; MMC3 status diagnostic prepared
- User reports failureagain, noOFFconfirmation. Currentcore0WFEforegroundhasno normalstatus output; cannotdiagnoseCPUaddress/mapper/IRQ state frompriorblankUSBcaptures.
- Prepared1Hz repeatingtimer setsreportflag/SEV; foregroundprintsCPU/writecounts,lastCPUheader,mapperwritecount/lastregister/select,CHRgeneration,IRQcounter/latch/enabled/pin,lateACKflag andPIOPCs. DoesnotprintintimerISR. Addsdiagnosticwork andcanperturbbankrefresh; intendedstartupdiagnosis, notstablegameplaybenchmark.
- Buildpassed; savedmagicon-mmc3-status.uf2. NOTFLASHEDpendingconsoleOFF.
- UserconfirmedOFF; MMC3statusdiagnosticloadedandflashverified, applicationrebootrequested. Mario3ROMunchanged. AwaitONwithoutRESET andUSBstatuscapture.

### MMC3 status evidence and shorter PRG path prepared
- Gray-screenstatus log acquired: cpu57M->62M, writescontinue, mapperwrites~10K, select46/40, chr_request0 throughout, IRQcounter/latch0, lateACK1. Flagincludesundriveninternalreads and isnotproofROMresponsemiss; doesjustifyinspectingCPUservice.
- ROM resetvectorFF30, bootcodewrites8000=40 theninitializeshardwareandcalls96BF; logFF3E/FF42 readsnearbootVBlankwaitandunexpectedFFFFwrites suggestincorrectstartupflow, notprovenCHR/IRQfailure.
- PreparedR6writeupdatesonlyselectedPRGslot; R7onlyslot1; modechangeonlyslots0/2. Previouslyall4pointersupdatedeveryPRGchange. Fixedlastslot3 remainsresetmapping. AddedR6/R7tostatuswithoutpercyclework.
-256mapping/IRQ/WRAMtestsandbuildpass. Savedmagicon-mmc3-prgfast.uf2, NOTFLASHEDpendingOFF. MMC3/fullgameandCHRasyncupdatecorrectnessremainunverified.
- UserconfirmedOFF; shorterPRGupdates/R6R7statusrevisionloadedandverified, applicationrebootrequested. Mario3ROMunchanged; awaitONwithoutRESET andstartupresult.

### ShorterPRG version: CHR/IRQ activity then stuckFFFF; noIRQ comparison prepared
- USBdiagnostic_mmc3_prgfast_20261012.txt: CPU55M->59M, writesfrozen733863, mapperwrites65214, lastwrite800042, select42, chr_request21313, IRQlatch28/counterchanging/enabled1/pin1, R6=94/R7=24, lastheadersallROMFFFFdataF7, lateACK1. ContrastspriornoCHRupdates. CPUcouldbejammed; repeatedFFFF alone notproofcause. R6highbitsmaskto30ontarget32banks, notautomaticallyinvalid.
- PreparedFC_DIAG_MMC3_NO_IRQ: keepbank/CHR/A12counterservice, suppressIRQpinassertion. IntendedtoseparateIRQ-relatedfailurefrombank/CPU/timingfailure, notfullgameorcorrectsplit-screenimplementation. Hosttestsverifycountercontinueswhilepinremainslow andmapping/WRAM. Buildpassed, savedmagicon-mmc3-noirq.uf2, NOTFLASHEDpendingOFF.
- UserconfirmedOFF; IRQ-suppressedcomparisonUF2loadedandverified, applicationrebootrequested. Mario3ROMandbank/CHRpathsunchanged. AwaitONwithoutRESET andscreen/logcomparison.

### IRQ-suppressed version stillgray
- diagnostic_mmc3_noirq_20261012.txt: IRQpin0confirmedsoftware, IRQcounter/latch0, CPUreadscontinue, writes/mapperwritescontinue, select46/40, R6=25 R7=1, chr_request0, lateACK1. Therefore removingIRQassertiondidnotproducecorrectstartup; IRQoutputaloneinsufficientexplanation. Not allphysicalIRQlinebehaviorproven.
- Resetvector/bootVBlank-loopaddressesstillappear, andlastmapperwritesFFFFF8/a00180 suggestabnormal/repeatedstartupflow; exactcorruptedinstructionunknown.
- Next nonflashcomparison: consoleRESEToncewithcartridgealreadyready/consoleON toseparatepower-upsequencefromreproducibleruntimebank/busfault. NoMCUreset, nohotswap. KeepIRQ-suppressedfirmwareforcomparison. Ifstillfails, collectfirstmapperwritesandbank-servicecyclemetricsratherthanadditionalblindtimingchanges.
- Bootwrite diagnostic buildpassedafterrestoringmissingtemporarysourcefiles; NOTFLASHEDpendingOFF. Handlercycles arelocalARMworkonly, notcompleteACKdeadline.

### 2026-10-13 bootwrite diagnostic flashed
- User explicitly confirms consoleOFF. magicon-mmc3-boottrace.uf2 loaded and flash verification succeeded; application reboot requested. Mario3 ROM unchanged; IRQ suppression retained. Await consoleON withoutRESET, then first16writes/perregisterhandlercycle log.

### Boot trace: repeated firstmode write, PRG swap revision prepared
- Boottrace log20261013 shows first16writesall800040; CHRrequest0, R6=0/R7=1, boot-loopreads andlateACK1. First64max8000handler87cycles348ns@250M, otherhandlersunsampled(0notzerolatency). Measurementincludesinstrumentation, excludesotherCPUservice/deadlines. Repeatedreset-likeflowcauseunconfirmed.
- Prepared mode-bit40 transition by swappingprg_map0/2 ratherthanrecomputingaddresses. CachedPRGmaskfromROMload, R6slotindexbranchless. MMC3handlerseparateRAMnoinlinefunction toreducebus-loopinlineregisterpressure. Removedfirst16writes/DWTmeasurementinstrumentation; statuscounterremains. IRQsuppressionretained.
-256mapping/IRQ/WRAMtestspass,buildpassed. magicon-mmc3-prgswap.uf2 preparedNOTFLASHEDpendingOFF. No measurednewtiming/successclaim.
- 2026-10-13 userconfirmedOFF; PRGswaprevisionloadedandflashverified, applicationrebootrequested. Mario3ROMunchanged; IRQsuppressionstillON. AwaitconsoleONwithoutRESET andstartupcomparison.

### PRGswap blackscreen; bus-arbitration comparison prepared
- Userreportsblackscreen. Logdiagnostic_mmc3_prgswap_20261013.txt: CPU128M->132M, writesfrozen378366,lastmapper800046,chr_request34,R6=25/R7=24,IRQpin0,lateACK0, readheaderFFFFdataF7. Atleaststartupadvancedfurther butstillfailed. lateACK0onlymeansnoACKlaterthanPIOedgecheck, notcorrectCPUsetup/data margin.
- PreparedBUSCTRLpriorityPROC1/DMA_R/DMA_W high, PROC0low, ACKwaitbeforebusstart. LocalRP2350SDKregisterdefinitionsconfirmbits. Intendedtoreducecore0CHR-copy contentionwithCPU/PPU; cause/fixunproven. SamePRGswap/IRQsuppression/CHRalgorithmretained.
- Buildpassed; magicon-mmc3-buspriority.uf2 preparedNOTFLASHEDpendingOFF.
- 2026-10-13 userconfirmedOFF; BUSCTRLprioritycomparisonUF2loadedandverified, applicationrebootrequested. Mario3ROMunchanged; IRQsuppressionstillON. AwaitconsoleONwithoutRESET andscreen/logcomparison.

### Offline actual-Mario3 mapper comparison
- Buspriorityrevisionstillgray. Log showsCPU/writeactivity, millionsofmapperwrites/unverifiedflow, chr_request>1M, lateACK0. Notcorrectexecutionevidence.
- Host-only cart_host_cpu bridge nowusesactualfastMMC3writepath andimmediatehostCHRmapping. Compiledwithexistingagnes_magicon.c. ComparisonagainstagnesnativeMMC3 usesactualmario3.nes. First180framehashesallidentical; extended600frameoutputs savedin sim/mmc3-native-20261013 andmmc3-fast-20261013; comparetooloutputforresult. NoPIO/DMA/arbitration/asynchronouscopytimingsimulated.
- Noadditionalfirmwareflashed thisturn; currentbuspriority/IRQ-suppressedfirmwarestillrunning. Nextsteprequiresdiagnosinghardware-sideCPUsetup/data/mapper-service timing ratherthanassumingmapperbankarithmeticwrong.
- Extended600framecomparison:594identical,6differentat348/350/360/364/370/374; bothreachtitle. Do notclaimfullmapperequivalence; PPU/IRQmodeldifferencesorlogicneedfurtheranalysis. ExcludesactualDMA/PIO/asyncCHRlatency.
- PreparedNO_IRQcomparisonalsoomitsphysicalA12SMstartup/core1eventservice. Priorpin-suppressedversionstillspentCPUcore1timeclockingIRQevents. Thisisolatesdeadlineinterferencefromeventhandling, notnormalMMC3support. Buildpassed; magicon-mmc3-noa12.uf2 NOTFLASHEDpendingOFF.
- 2026-10-13 userconfirmedOFF; A12-event-service-disabledcomparisonloadedandverified, applicationrebootrequested. Mario3ROMunchanged. IRQandA12clockingdisabledfordiagnosis; awaitstartupscreenwithoutRESET, notcorrectsplit-screenexpectation.

### NoA12 version playable; restoreIRQ on core0 prepared
- Userconfirmsnormaltitle/playableMario3, withbottomstatus badlycorrupted. Photo showsvalidworldmap/garbledstatus. Consistentwithdisabledsplit-screenIRQ, notfullMMC3success. Savedconfirmedplayable-noIRQ UF2.
- LiveUSB: CPU264M->266M, writes11M->11.17M, normal-lookingreg47/R6=10/R7=26, chr_request53K, IRQenabled1/latch192/pin0,lateACK0. SupportscriticalCPUcore1A12eventwork as contributor (otherpreviouschangesstillpresent).
- PreparedphysicalA12monitorrestored, PIO2IRQ0FIFO-not-emptyhandler oncore0highestpriority (USBlower) clocksMMC3counter/assertsIRQ; CPUcore1eventpollremainsabsent. Counter/latch/reload/enabledsharedvolatile; post-assertdisablecheckhonorssimultaneousE000flag. Crosscoretiming/racesstillrequirevalidation; nostatuscorrectnessclaimyet.
- Mapping/IRQ/WRAMauditandPIOtestspass; RP2350buildpassed. Savedmagicon-mmc3-core0irq.uf2. NOTFLASHEDpendingOFF.
- 2026-10-13 userconfirmedOFF; core0A12IRQrevisionloadedandflashverified, applicationrebootrequested. Mario3ROMunchanged; IRQrestoredwhileCPUcore1A12pollabsent. Awaitworldmap/course/bottomstatusvisualandgameplaytest.

### Core0 IRQ restored: HUD improves, world CHR corrupt; timing diagnostic prepared
- Userreportsgamecontinuesbutgraphicsworse; photoHUDmorereadable/worldmaptileswrong. NofullMMC3success. LiveCHRrequestdelta720/s vs360/spriornoIRQ, CPU/writescontinue, lateACK0. AsyncCHRwindowupdatesmaylag/raceafterIRQbankchanges; exactcauseunknown.
- RecheckedNESdevMMC3spec https://www.nesdev.org/wiki/MMC3: qualificationthreeM2fallingedgesmatchesexistingPIO; donotarbitrarilychangefiltertofour.
- Preparedcore0DWT1Klookupcopymax(includespreemptions),copycount,A12eventcount,IRQpinassert-transitioncount andhandledrequeststatus. Addsboundedcore0diagnosticwork, notexactPPUdotposition/electricalIRQmeasurement. Buildpassed, magicon-mmc3-chrtiming.uf2 NOTFLASHEDpendingOFF.
- 2026-10-13 userconfirmedOFF; CHRtiming/A12event diagnostic loadedandverified, applicationrebootrequested. Mario3ROMunchanged,core0IRQenabled. AwaitON/mapstateandUSBmetrics.

## 2026-10-13 MMC3 CHR packed expansion comparison
Live timing logs saved as mmc3-chrtiming-live-20261013.txt. Consecutive one-second reports: A12 events about 26451-26486/s; IRQ assertions 60-61/s; CHR copies about 960-968/s; max 1KiB conversion 10530 cycles (42.12us at 250MHz). CPU writes continued and lateACK=0. This does not prove IRQ scanline accuracy. Several slots updated serially may expose partial old/new CHR during rendering.
Changed conversion to one packed 32-bit source load and four expanded destination stores. Entire actual Mario3 128KiB CHR checked for identical byte expansion. MMC3 fast mapper 256 combinations, IRQ reload and WRAM protection audit passed. Build and picotool load -v succeeded, application reboot requested. Saved magicon-mmc3-chrpacked.uf2. Awaiting physical test; no claim of fixed rendering or measured speedup.

## 2026-10-13 A12 interval diagnostic flashed
Packed CHR live log: max 1KiB copy 5281 cycles (21.124us); user reports no visible improvement, photo shows HUD split above expected bottom position. Timing improvement alone did not fix rendering. Added core0 IRQ-service interval buckets (<8us, 8-40us, 40-80us, >=80us) for qualified A12 events. These measure software service intervals, not electrical edge timestamps, and FIFO backlog can distort them. Build succeeded; saved magicon-mmc3-a12interval.uf2; user confirmed FC OFF; picotool verified flash and requested application reboot. Awaiting physical test/logs.

A12 interval logs show ~9700-9900 events/s under8us, ~1900/s 8-40us, ~13560/s 40-80us on world map. These are handler intervals (backlog not yet excluded), not measured pin edges. Prepared fixed-time A12 low filter comparison: 32 iterations of jmp-pin + nop[9] + jmp-x-- =384 cycles at250MHz, plus setup/final detection (~1.54us). Not exact MMC3 M2 filter and not declared final implementation. Original PIO backed up as mmc3-a12-m2-original.pio. Build successful, not yet flashed.

2026-10-13: User confirmed FC OFF. Fixed-time A12 filter comparison magicon-mmc3-a12fixedtime.uf2 flashed with picotool load -v -f; verified successfully and application reboot requested. Awaiting physical result and interval logs.

2026-10-13: User reports fixed-time A12 comparison unchanged and less stable than around00:29. User confirmed FC OFF. Restored saved magicon-mmc3-playable-noirq-confirmed.uf2 (original build timestamp2026-10-13 00:25:42). picotool verified successfully and requested application reboot. Source still contains experimental filter/timing changes; flashed binary is the saved no-IRQ baseline. MMC3 HUD split remains unsupported in this baseline.

## 2026-10-13 Remote desktop first physical trial
User requested remote desktop test and confirmed FC OFF. Working Mario3 no-IRQ binary and ROM source preserved. Changed remote driver PRG pointer to SRAM copy after two framebuffer buffers (16KiB), avoiding flash reads in CPU critical path. Built normal remote firmware separately with all diagnostic flags OFF; CPU40ns PIO retained, existing software PPU response path used (DMA path not compatible with remote row tracking). This path remains unverified on actual console. Built magicon-remote-trial.uf2 and packed remote marker; both flashed/verified. PC capture/encode dry run 3frames: fit gray ~28.9fps, zoomgray60.2fps. Initial sender planned10fps grayscale, no audio.

Remote first trial: user photo garbled vertical repeated patterns before desktop sender start. COM11 read yielded2980bytes/149 FCIN packets over3s, evidence remote driver runs (not proof all CPU accesses correct). Prepared older PPU address sample (MOV Y,ISR / MOV ISR,PINS then push Y), same address-sampling principle as successful DMA PPU path. Added 1s remote-loop CPU/PPU late-ACK flags and PIO PCs; flags indicate expired service including undriven reads, not exact electrical setup violations. Build succeeded; saved magicon-remote-previoussample.uf2. Await FC OFF before flash. Software PPU response timing remains unverified.

2026-10-13: User confirmed FC OFF. magicon-remote-previoussample.uf2 loaded and verified successfully; application reboot requested. Remote ROM marker remains at0x10800000. Desktop sender is stopped; next check waiting-screen rendering and deadline logs before restarting sender.

## Remote compact DMA physical trial
Previous software PPU trial remained garbled; live flags CPU_late0/PPU_late1, no FCIN packets in3s (earlier trial149/3s). This only establishes at least one expired PPU response, not failure rate or sufficient sole cause.
Added FC_REMOTE_DMA build option, separate generated compact driver. NT has128x120 centered at64,56 with240 unique tiles and blank240 border; grayscale256x240 source sampled at even pixels and converted into DMA lookup CHR. Cursor mapped to compact viewport. Core1 remote CPU no longer touches DMA RX FIFO; core0 updates lookup and swaps metadata. Initial waiting image converted before enablingPIO; PRG inSRAM. DMA startup skips overwriting prefilled table. In-place updates may tear and metadata swaps aren't synchronized toVBlank yet. Color unsupported for this trial; audio not tested. Host verifies generated NT all1024bytes andvectors; RP2350 build successful; user confirmedOFF; picotool verified magicon-remote-dma-compact.uf2 and requested reboot. Remote marker retained. Await waiting-screen test before desktop sender.

Remote DMA gray result: COM11 missing, picotool info -a identified boot type bootsel. Trial was not running. User confirmed FC OFF; explicit picotool reboot succeeded. After1800ms COM11 returned and open succeeded. Await console ON test.

Remote compact DMA now physically shows centered waiting text after explicit application reboot. Sample reportsCPU_late0/PPU_late0, 118FCIN packets in2s. These flags do not prove electrical timing margin; PPU lookup lacks same expired-IRQ instrumentation as software PPU. Started remote_pc.py COM11 grayscale10fps no-audio; exec session77202. User screen result pending. Waiting text was decimated from256x240 and can lose thin font strokes.

## Full-screen remote DMA trial
User confirms compact stream success but requests larger display. Saved compact-confirmed binary. Added FC_REMOTE_FULL: generated 6502 driver initializes full NT from6000 and copies128NT bytes perVBlank across8frames, omits attribute refresh (grayscale zero attributes). Unrolled transfer budget ~1024cycles+palette256+OAM~513+overhead fits nominal NTSC VBlank, not hardware-measured. Full256x240 source tiles deduplicated; most frequent256 retained, extra unique tiles approximated by nearest128-bit Hamming distance. Source pixels no longer downsampled; detail fidelity can vary when >256unique tiles. Core0 lookup/NT in-place updates can mix old/new content transiently; no claim of tear-free display. Cursor no scaling. Reduced remote-only ROM arena to64KiB to fit SRAM and made actual arena size bounds apply to NES/NSF loads. Extracted actual C conversion function host audit checks exact reconstruction with200patterns and overflow case. RP2350 build passed. User confirmedOFF. Fullscreen UF2 verified and COM11 returned (explicit reboot fallback checked). PC sender stopped after FC OFF. Await full waiting-screen before restarting sender at5fps.

2026-10-13 offline work while user away: RetroArch snapshot tests, stable tile identities, color attributes restored, --stretch option, audio codec and WASAPI checks. Full details remote_retroarch_validation_20261013.md. Built magicon-remote-dma-full-stabletiles-colorready.uf2; NOT flashed. In-place updates/8-frame NT transfer still not atomic.

2026-10-13 MMC3 offline comparison: see mmc3_retroarch_validation_20261013.md. Atomic reload-request generations prevent loss during cross-core clock/ack; independent bank vectors and reload race/wrap tests pass. Original three-M2 A12 PIO restored and140-phase ideal-waveform checks pass. Host A12 time/manual address model corrected; tests1/2/3/6 pass, strict scanline timing4 remainsfailed#2, revisionA5 differsasBtarget. Mario3 native comparison594/600 unchanged; RA frame600 RGBmismatch1286. Built magicon-mmc3-reload-generation.uf2; NOT flashed.
