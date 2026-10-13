# Third-party code used by validation

- `agnes/`: upstream https://github.com/kgabis/agnes; its license is retained in `agnes/LICENSE`.
- The cycle-level validation core uses https://github.com/libretro/nestopia. The upstream tree is downloaded locally to `ref/nestopia-timing/nestopia-master` and is not vendored here.
- `mmc3-sequence-20261013/nestopia-validation.patch` modifies Nestopia's MMC3 counter, PPU fetch hooks, and A12 timing. This patch and the resulting validation core are GPL-2.0-or-later; the GPL text is in that directory's `COPYING`. The bridge links the project's cartridge logic into this GPL validation core; this does not change the separately distributed firmware's license.
- The validation core is experimental: save states and other mapper families are not validated. It must not be presented as a general replacement for Nestopia.
- Build helpers currently contain paths from the development machine. Adapt compiler/SDK paths before reproduction.
- External test ROMs, game ROMs, source PV/media, downloaded executable tools, and private credentials are omitted from the public checkpoint. Use your own authorized inputs.

Reference projects reviewed but not copied into firmware: PiPU (https://github.com/rasteri/PiPU), PPUppy (https://sourceforge.net/p/tom7misc/svn/HEAD/tree/trunk/ppuppy/), and NESFlix (https://github.com/no-carrier/NESFlix).
