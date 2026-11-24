$ErrorActionPreference='Stop'
$sdk='C:/Users/Yugo/pico'
$python='C:/Users/Yugo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $python "$PSScriptRoot/gen_rom.py"
if($LASTEXITCODE){throw 'ROM generation failed'}
$work="$sdk/mic-controller-20261124/source"
New-Item -ItemType Directory -Force $work | Out-Null
Copy-Item "$PSScriptRoot/main.c","$PSScriptRoot/CMakeLists.txt","$PSScriptRoot/rom.h","$PSScriptRoot/playback.h" $work -Force
Copy-Item "$PSScriptRoot/../boards" $work -Recurse -Force
Copy-Item "$PSScriptRoot/../power_guard.h","$PSScriptRoot/../standalone_video/baseline/cpu_m2.pio","$PSScriptRoot/../host_test/tusb_config.h" $work -Force
$env:PATH="$sdk/gcc/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin;$sdk/cmake/cmake-4.4.3-windows-x86_64/bin;$sdk/ninja;"+$env:PATH
$env:PICO_SDK_PATH="$sdk/pico-sdk/pico-sdk-2.3.1"
$env:PICO_TOOLCHAIN_PATH="$sdk/gcc/xpack-arm-none-eabi-gcc-15.2.1-1.1"
cmake -G Ninja -S $work -B "$work/../build" -DCMAKE_BUILD_TYPE=Release "-DPICO_TINYUSB_PATH=$sdk/tinyusb-0.21.0" "-Dpicotool_DIR=$sdk/picotool/picotool" "-Dpioasm_DIR=$sdk/pico-sdk-tools/pioasm"
if($LASTEXITCODE){throw 'configure failed'}
cmake --build "$work/../build" --target mic_controller
if($LASTEXITCODE){throw 'build failed'}
