import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from build_glfw_lite import required_symbols,exported_symbols,INPUT_POLL_EXPORTS,validate_input_exports
from graphics_common import bridge_overlays,register_tree
from lwjgl_codegen import descriptor,generate_callbacks,generate_jni,mangle,parse_natives
from bootstrap_toolchain import sha256
from collect_graphics_probe import classify_log
from fetch_stb import verify_sources
from probe_client_graph import verify_split_runtime_input
from stage_game_assets import verified_assets
import hashlib

class NativeBoundaryTests(unittest.TestCase):
    def test_structure_accessors_are_not_glfw_exports(self):
        inventory={"methods":[{"owner":"org/lwjgl/glfw/GLFW","name":"glfwInit"},
            {"owner":"org/lwjgl/glfw/GLFWNativeCocoa","name":"glfwGetCocoaWindow"},
            {"owner":"org/lwjgl/glfw/GLFWVidMode","name":"width"},
            {"owner":"org/lwjgl/glfw/Callbacks","name":"glfwFreeCallbacks"}]}
        self.assertEqual(required_symbols(inventory),{"glfwInit","glfwGetCocoaWindow"}|INPUT_POLL_EXPORTS)
    def test_mod_polling_is_required_without_vanilla_call_sites(self):
        self.assertEqual(required_symbols({"methods":[]}),INPUT_POLL_EXPORTS)
    def test_historical_glfw_without_mouse_polling_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"glfwGetMouseButton"):
            validate_input_exports({"glfwGetKey","glfwGetCursorPos"})
        validate_input_exports(set(INPUT_POLL_EXPORTS))
    def test_mach_o_symbol_prefix_is_removed_once(self):
        self.assertEqual(exported_symbols("_glfwInit\n_Java_a_b\n"),{"glfwInit","Java_a_b"})
    def test_jni_overload_mangling_is_unambiguous(self):
        self.assertEqual(mangle("do_it"),"do_1it")
        self.assertEqual(mangle("[J"),"_3J")
    def test_jni_generator_rejects_object_or_multidimensional_abi(self):
        for value in ["(Ljava/lang/Object;J)V","([[IJ)V","(IJ)Ljava/lang/Object;"]:
            with self.assertRaises(ValueError):descriptor(value)
    def test_jni_generator_requires_explicit_function_address(self):
        with self.assertRaises(ValueError):generate_jni([("invokeV","(II)V")])
    def test_array_pins_are_released_on_call_and_partial_failure(self):
        text=generate_jni([("invokePPV","([I[IJ)V")])
        self.assertIn("GetIntArrayElements",text)
        self.assertIn("if(a1&&!p1)",text)
        self.assertGreaterEqual(text.count("ReleaseIntArrayElements(e,a0,p0,0)"),2)
        self.assertIn("__",text)
        self.assertIn("Missing native function pointer",text)
    def test_javap_native_parser_keeps_overloads(self):
        text="public static native long invokeP(int, long);\n descriptor: (IJ)J\npublic static native long invokeP(long);\n descriptor: (J)J"
        self.assertEqual(parse_natives(text),[("invokeP","(IJ)J"),("invokeP","(J)J")])
    def test_static_callbacks_use_exact_boolean_and_preedit_jni_abi(self):
        text=generate_callbacks(2)
        self.assertIn('"(JZ)V"',text)
        self.assertIn('"(JIJIJII)V"',text)
        self.assertIn("NewGlobalRef",text)
        self.assertIn("NewLocalRef",text)
        for forbidden in ("mprotect(","mmap(","ffi_closure_alloc(","upcallStub("):
            self.assertNotIn(forbidden,text)
    def test_callback_bank_has_a_fixed_capacity(self):
        for size in (0,65):
            with self.assertRaises(ValueError):generate_callbacks(size)
    def test_stb_callback_uses_pointer_pointer_int_and_keeps_java_exception(self):
        text=generate_callbacks(1)
        self.assertIn('"org/lwjgl/stb/STBIWriteCallbackI"',text)
        self.assertIn('"(JJI)V"',text)
        self.assertIn('ExceptionCheck',text)
    def test_partial_or_failed_probe_cannot_be_passed(self):
        facts=classify_log("MINECRAFT_RENDER_SYSTEM_INITIALIZED backend=Metal\n[Metal] DIAGNOSTIC_FRAME_PRESENTED")
        self.assertFalse(all(facts.values()))
        facts=classify_log("MINECRAFT_RENDER_SYSTEM_INITIALIZED backend=Metal\n[Metal] DIAGNOSTIC_FRAME_PRESENTED\nMETAL_INTEGRATION_PROBE_PASS\n[FAOT] run_main returned 0")
        self.assertTrue(all(facts.values()))
    def test_resource_probe_requires_gpu_readback_evidence(self):
        text="MINECRAFT_RENDER_SYSTEM_INITIALIZED backend=Metal\n[Metal] TEXTURE_FRAME_PRESENTED\nMETAL_RESOURCE_PROBE_PASS\n[FAOT] run_main returned 0"
        self.assertFalse(all(classify_log(text,"resources").values()))
        self.assertTrue(all(classify_log(text+"\nMETAL_RESOURCE_ROUNDTRIP_PASS","resources").values()))
    def test_image_probe_requires_real_native_image_completion(self):
        text="MINECRAFT_RENDER_SYSTEM_INITIALIZED backend=Metal\n[Metal] TEXTURE_FRAME_PRESENTED\nMETAL_RESOURCE_PROBE_PASS\nMETAL_RESOURCE_ROUNDTRIP_PASS\n[FAOT] run_main returned 0"
        self.assertFalse(all(classify_log(text,"images").values()))
        self.assertTrue(all(classify_log(text+"\nMINECRAFT_NATIVE_IMAGE_PASS","images").values()))
    def test_draw_probe_requires_pso_and_gpu_pixel_checks(self):
        text='MINECRAFT_RENDER_SYSTEM_INITIALIZED backend=Metal\n[Metal] TEXTURE_FRAME_PRESENTED\nMETAL_DRAW_PROBE_PASS\n[FAOT] run_main returned 0'
        self.assertFalse(all(classify_log(text,'draw').values()))
        self.assertTrue(all(classify_log(text+'\nVANILLA_METAL_PSO_PASS count=87\nMETAL_VANILLA_DRAW_PASS','draw').values()))
    def test_audio_probe_requires_pcm_progression_and_clean_completion(self):
        text='Added "core" for playback\nOPENAL_DEVICE renderer=OpenAL Soft\nOPENAL_PCM_PLAYBACK_PASS bytes=4410 muted=true\nOPENAL_PROBE_PASS'
        self.assertFalse(all(classify_log(text,'audio').values()))
        self.assertTrue(all(classify_log(text+'\n[FAOT] run_main returned 0','audio').values()))

class BridgeInputTests(unittest.TestCase):
    def test_asset_staging_rejects_modified_objects_and_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=b'owned fixture';digest=hashlib.sha1(data).hexdigest()
            obj=root/'objects'/digest[:2]/digest;obj.parent.mkdir(parents=True);obj.write_bytes(data)
            index=root/'indexes/30.json';index.parent.mkdir();index.write_text(json.dumps({'objects':{'fixture':{'hash':digest,'size':len(data)}}}))
            metadata={'id':'26.1.2','assetIndex':{'id':'30','size':index.stat().st_size,'sha1':hashlib.sha1(index.read_bytes()).hexdigest()}}
            self.assertEqual(len(verified_assets(root,metadata)[2]),1)
            obj.write_bytes(b'wrong fixture')
            with self.assertRaisesRegex(ValueError,'invalid asset'):verified_assets(root,metadata)
            index.write_text('{}')
            with self.assertRaisesRegex(ValueError,'index fingerprint'):verified_assets(root,metadata)
    def test_injected_client_requires_unchanged_split_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);split=root/'split';split.mkdir();original=split/'client.jar';original.write_bytes(b'fixture')
            (split/'result.json').write_text(json.dumps({'status':'SPLIT','outputJarSHA256':sha256(original),'classes':[{'methodsSplit':1,'finalFieldsUnfinalised':3}]}))
            injected=root/'injected';injected.mkdir();jar=injected/'client.jar';jar.write_bytes(b'injected fixture')
            record={'status':'BACKEND_INJECTED','outputJarSHA256':sha256(jar),'client':str(original),'clientSHA256':sha256(original),'splitRuntimeValidation':verify_split_runtime_input(original)}
            (injected/'result.json').write_text(json.dumps(record))
            self.assertEqual(verify_split_runtime_input(jar)['split']['finalFieldsUnfinalised'],3)
            original.write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError,'fingerprint changed'):verify_split_runtime_input(jar)
    def test_old_split_client_is_rejected_before_target_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);jar=root/'client.jar';jar.write_bytes(b'first-party fixture')
            record={'status':'SPLIT','outputJarSHA256':sha256(jar),'classes':[{'methodsSplit':1}]}
            (root/'result.json').write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,'final-field relocation'):verify_split_runtime_input(jar)
            record['classes'][0]['finalFieldsUnfinalised']=2;(root/'result.json').write_text(json.dumps(record))
            self.assertEqual(verify_split_runtime_input(jar)['finalFieldsUnfinalised'],2)
    def test_image_header_checksum_is_required(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);file=directory/'stb_image.h';file.write_text('fixed upstream fixture')
            lock={'files':{'stb_image.h':{'sha256':sha256(file)}}}
            self.assertEqual(verify_sources(directory,lock),directory)
            file.write_text('modified')
            with self.assertRaisesRegex(ValueError,'modified pinned STB'):verify_sources(directory,lock)
    def test_optional_stb_overlay_is_verified_when_listed(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp).resolve();paths=[p/name for name in ['lwjgl-ios.jar','lwjgl-glfw-ios.jar','lwjgl-stb-ios.jar']]
            for f in paths:f.write_bytes(b'verified bytes')
            (p/'result.json').write_text(json.dumps({'status':'STATIC_JNI_BRIDGE_BUILT','overlaysSHA256':{str(f):sha256(f) for f in paths}}))
            self.assertEqual(bridge_overlays(p),paths)
            paths[2].write_bytes(b'modified')
            with self.assertRaises(ValueError):bridge_overlays(p)
    def test_missing_or_failed_bridge_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/"result.json").write_text('{"status":"BLOCKED"}')
            with self.assertRaises(ValueError):bridge_overlays(p)
    def test_jar_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp).resolve();paths=[p/"lwjgl-ios.jar",p/"lwjgl-glfw-ios.jar"]
            for f in paths:f.write_bytes(b"verified bytes")
            (p/"result.json").write_text(json.dumps({"status":"STATIC_JNI_BRIDGE_BUILT","overlaysSHA256":{str(f):sha256(f) for f in paths}}))
            self.assertEqual(bridge_overlays(p),paths)
            paths[0].write_bytes(b"modified bytes")
            with self.assertRaises(ValueError):bridge_overlays(p)
    def test_registry_failure_is_not_reported_as_success(self):
        with patch.dict(os.environ,{},clear=True),patch("graphics_common.subprocess.run") as run:
            run.return_value.returncode=1;run.return_value.stderr="database unavailable"
            with self.assertRaisesRegex(RuntimeError,"Central AAR registration failed"):
                register_tree(Path("/private/tmp/test-graphics"),["build"])
    def test_private_registry_override_is_refused(self):
        with patch.dict(os.environ,{"AAR_HOME":"/private/tmp/private-registry"}):
            with self.assertRaisesRegex(RuntimeError,"central registry"):
                register_tree(Path("/private/tmp/test-graphics"),["build"])
    def test_missing_registry_retains_pending_request(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True), patch("graphics_common.subprocess.run", side_effect=FileNotFoundError):
            result = register_tree(Path(temp), ["build"])
            self.assertEqual(result["status"], "REGISTRATION_PENDING")
            self.assertEqual(json.loads((Path(temp) / "registration-pending.json").read_text()), result)
            self.assertIn("register", result["argv"])

if __name__=="__main__":unittest.main()
