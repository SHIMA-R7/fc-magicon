# PPU開始待ちの比較版

直前のCPU窓診断はCPU受信不一致0、NTは最初の試験だけ936回不一致、残る51試験は一致した。その起動直後の条件を調べるため、同じ試験の開始待ちのみを変更する。

`--cpu-window --settle-ppu` の生成プログラムは、起動後に約51k FC CPUサイクルの固定待ちを行い、PPUSTATUSを読んで残存VBlankフラグと書き込みラッチをクリアし、さらに2回のVBlank待ちを行う。その後PPUCTRL/PPUMASKへ0を書き直し、描画停止を再指定してから試験へ入る。通常版や他の保存済みUF2は変更しない。

参考：[NESdev PPU power up state](https://www.nesdev.org/wiki/PPU_power_up_state)。PPUには起動直後のレジスタ書き込み抑止期間があるが、今回の実機不一致原因として確定したものではない。電気的な未給電入力保護の追加でもない。

実C/6502の52試験は正常・不一致0。PPUSTATUSが常にVBlankを返す最短待ちモデルでも、最初のPPUADDR書き込みは52390 CPUサイクル以降となることを確認した。ホストモデルは起動時の実PPU挙動を完全に再現していないので、これだけで実機の改善は保証しない。

生成：`gen_nt_stress.py baseline/nt_cpu_window_settled_driver.h --cpu-window --settle-ppu`

ビルド：`build.ps1 -ColdBoot -FastReads -PpuSettle`

UF2：`firmware/out-standalone-video/cpu-window-settled-cold-fast-20261015.uf2`

SHA256：`7f5764b6efb4139eca0deef54c7b3d636da075ef1a3a4ae5fbc4e32b61c38804`

実機はまだ書き換えていない。FC OFF・BOOTSEL準備確認後に書き込む。
