# Build Windows binaries on Linux

The current game mod 0.1.3 is portable GDScript and uses the native libraries shipped by Home: Equestria 0.3.1.2. Build it with `scripts/build.py --platform windows-x86_64`; no mod-native build is needed. The native build instructions below concern the companion runtime and historical native development.

No Windows compiler installation or Windows boot is needed for this build. Native Windows hardware qualification is separate from cross-compilation and Wine checks.

The first candidate uses LLVM MinGW `20261104` UCRT, LLVM 23.1.5, from the [official cross-compiler release](https://github.com/mstorsjo/llvm-mingw/releases/tag/20261104). The Linux x86_64 archive SHA-256 is `919380403de87dca3c581c2053230cd298af5e891286628ba0613b7fed370926`. Unpack it into a user-owned toolchain folder; no system package changes are needed. The release ZIP embeds official Windows CPython 3.14.10, SHA-256 `90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159`.

Pinned source inputs:

- Godot C++ bindings: `e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77` (Godot 4.5).
- Breeze: `87b43667ca5597f826441991e416a279ed7373b9`; ggml submodule: `36da57138425487184aa1da2eee2cde155909c6f`.
- SPIR-V headers: `04f10f650d514df88b76d25e83db360142c7b174`, tag `vulkan-sdk-1.4.341.0`. Newer headers removed the legacy `spirv.hpp` required by this pinned ggml revision.
- Vulkan headers/registry 1.4.363 and nlohmann/json 3.12.0. The local build receipt retains a full header hash inventory. Shader compilation uses the Linux host's `glslc`; the shader-generator executable also runs on Linux.

Stage portable headers and a Windows import library without exposing Linux system headers to the cross-compiler:

```bash
python3 scripts/prepare_windows_sdk.py \
  --toolchain /path/to/llvm-mingw --include /usr/include \
  --spirv-include /path/to/SPIRV-Headers/include \
  --registry /usr/share/vulkan/registry/vk.xml --output build/windows-sdk
export LLVM_MINGW=/path/to/llvm-mingw
python3 scripts/build_native.py --platform windows-x86_64 \
  --toolchain native/windows-llvm-mingw.cmake \
  --godot-cpp /path/to/pinned/godot-cpp --json-include build/windows-sdk/include
```

Build Breeze with `native/breeze/build.py --windows`, the same toolchain file, Vulkan enabled, MP3 disabled and tests enabled. Pass `--skip-tests` only while cross-building; execute the resulting tests under Wine or Windows afterward. Additional CMake arguments are supplied as `--cmake-arg=-DNAME=VALUE`:

```text
CMAKE_TOOLCHAIN_FILE=/absolute/path/to/native/windows-llvm-mingw.cmake
CMAKE_BUILD_TYPE=Release
BUILD_SHARED_LIBS=OFF
BREEZE_BUILD_SHARED=OFF
BREEZE_BUILD_CLI=OFF
GGML_STATIC=ON
GGML_NATIVE=OFF
GGML_AVX=ON
GGML_AVX2=ON
GGML_FMA=ON
GGML_F16C=ON
GGML_BMI2=ON
Vulkan_INCLUDE_DIR=/absolute/path/to/build/windows-sdk/include
Vulkan_LIBRARY=/absolute/path/to/build/windows-sdk/libvulkan-1.a
Vulkan_GLSLC_EXECUTABLE=/usr/bin/glslc
CMAKE_PREFIX_PATH=/path/to/installed/SPIRV-Headers
```

Both compiler/runtime libraries are linked statically. The Windows Breeze executable imports Windows system libraries and `vulkan-1.dll`; the lip-sync DLL imports Windows system libraries. Preserve LLVM/MinGW notices with both artifacts. The portable-build patch removes absolute source paths from diagnostics and uses `$ORIGIN` for Linux shared-library lookup. It follows the unchanged LoRA patch. The optional Windows source patch adds a missing `<cstdlib>` include. Runtime bundles include these source patches.

Build the Windows-named routing pack with `scripts/build.py --platform windows-x86_64`, using the matching game source and Linux Godot 4.5 release engine. The routing pack contains no native DLL. Package the Windows runtime with `scripts/package_runtime.py --platform windows-x86_64`, supplying its executable hash inventory. Finally, `scripts/package_windows.py` takes that archive, the unchanged voice pack, the Windows mod pack and the SHA-verified embedded Python ZIP. It emits the Windows ZIP, file inventory and `WINDOWS-SHA256SUMS`.

Before publishing, run `breeze-test-lora.exe`, `breeze-test-depth.exe`, all companion tests with Windows Python, the installed server with real synthesis, and Windows Godot mod/transport checks. See [WINDOWS.md](WINDOWS.md) for native flatscreen coverage and the untested Windows PCVR scope.
