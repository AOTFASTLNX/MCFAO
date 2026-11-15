# Local GUI and GL41 builds

The desktop workbench targets Apple Silicon macOS. It requires a local MCFAO checkout, Python 3.11+, Java/GraalVM 25, Xcode with iPhoneOS SDK, and verified locally acquired Minecraft 26.1.2 inputs. Proprietary inputs and generated IPAs remain local.

## GUI workflow

1. Set the MCFAO checkout in Settings. Choose a verified local toolchain JSON as described in `docs/BUILDING.md` and the CLI documentation.
2. Import a `.mrpack` or Prism instance for static preflight. In Builds, use “导入此实例的本地构建文件” to materialize client files into a new task directory. Downloads currently support the public Modrinth CDN with manifest SHA-1/SHA-512 and size checks. Other hosts fail with an explicit reason; use a local Prism instance for those files.
3. Choose Vanilla or Fabric, then GL41/Zink/MoltenVK or the optional native Metal backend. Renderer choice remains explicit pending this integrated build's device acceptance.
4. Choose a fresh output directory and independent test Bundle ID. Fabric requires audited inputs and retains the default-deny transformation sandbox.
5. Start the full build. Actual stage messages, stdout/stderr and failure details come from `tools/mcfao.py build`; this path never uses `--prepare-only`. Cancel stops only the owned process tree, including nested sandbox sessions. Retry preserves verified caches; changed inputs require a fresh output directory.
6. After completion, inspect IPA path, bytes, SHA-256, renderer, loader, source SHA, signature and evidence paths. Open the output directory or export the complete log. An unsigned IPA cannot be installed directly.

Imported Mod names, versions, dependencies and static findings remain metadata evidence. The Fabric/MDAF report button reads the actual current build's conversion, reflection/resource, tracing, semantic and unsupported-mechanism records. No static report or AOT result grants `FUNCTION_PASS`. A full build rejects implicit Mod exclusions and retains the diagnostic report.

Imported configuration, resource packs and options are packaged as a first-launch seed. Device files already present take precedence; accounts and saves are never imported. Ambiguous override path collisions fail rather than silently choosing content. The source instance is not modified.

## Reproducible local validation

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py'
cd desktop
npm ci
npm test
npm run test:e2e
cd src-tauri
cargo test --lib
cd ..
npm run tauri build -- --debug --bundles app
```

Use an ARM64 Rust toolchain. The integration run uses an isolated Rust installation and Cargo target directory beneath `artifacts/integration-20261115/cache`; it does not replace the user's x86_64 toolchain.

The expensive real-AOT Tauri IPC test is intentionally separate from unit tests:

```sh
MCFAO_TEST_CONFIG=/absolute/path/to/config-gl41.json \
MCFAO_TEST_OUTPUT=/absolute/path/to/fresh-output \
cargo test --lib actual_local_aot_through_tauri_ipc -- --ignored --nocapture
```

This invokes the real build through Tauri's command interface with a mock window runtime. It validates IPC-to-AOT-to-IPA behavior, while native window interaction and physical gameplay have separate acceptance records.
