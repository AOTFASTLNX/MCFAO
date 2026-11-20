import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from test_version import test_version,ipa_filename
import mcfao
import desktop_workbench as w

class TestVersionTests(unittest.TestCase):
    def test_labels_and_optional_default(self):
        self.assertEqual(test_version(None),'')
        self.assertEqual(test_version('  '),'')
        self.assertEqual(ipa_filename(),'NCL-game.ipa')
        self.assertEqual(ipa_filename('LAN-r5-20261117'),'NCL-game-LAN-r5-20261117.ipa')
        for label in ('../escape','bad/name','a\nb','a=b','$(cmd)','-bad','a'*65,12):
            with self.assertRaises(ValueError):test_version(label)

    def test_xcode_setting_is_optional_and_cannot_change_bundle_identifier(self):
        for value in ('','LAN-r5'):
            argv=mcfao.device_xcode(Path('/tmp/stage'),Path('/tmp/assets'),team='',unsigned=True,test_version_label=value)
            self.assertIn('FAOT_TEST_VERSION='+value,argv)
            self.assertIn('PRODUCT_BUNDLE_IDENTIFIER='+mcfao.BUNDLE_IDENTIFIER,argv)
        with self.assertRaises(ValueError):mcfao.device_xcode(Path('/tmp/stage'),Path('/tmp/assets'),team='',test_version_label='a=b')

    def test_existing_export_keeps_original_stage_label(self):
        with tempfile.TemporaryDirectory() as temp:
            build=Path(temp)
            (build/'result.json').write_text(json.dumps(dict(status='UNSIGNED_DEVICE_APP',target='ios-arm64',testVersion='LAN-r5')))
            request=dict(workspace=str(build),loader='vanilla',existingBuild=str(build),unsigned=True,testVersion='LAN-r6')
            with patch.object(w,'workspace_path',return_value=build):w.validate_request(request)
            self.assertEqual(request['testVersion'],'LAN-r5')

    def test_gui_field_reaches_build_cli_and_empty_is_omitted(self):
        for value in ('','LAN-r5'):
            with patch.object(w,'execute') as execute:
                w.compile_build(['python','mcfao.py'],Path('/tmp/job'),dict(loader='vanilla',config='/tmp/config',testVersion=value),Path('/tmp/build'),None,None,lambda **_:None,{})
            args=execute.call_args.args[0]
            self.assertEqual('--test-version' in args,bool(value))
            if value:self.assertEqual(args[args.index('--test-version')+1],value)

    def test_native_subtitle_and_log_names_hide_unset_versions(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'test.m';binary=Path(temp)/'test'
            source.write_text('''#import "test_version.h"
int main(void) { @autoreleasepool {
 for (NSDictionary *info in @[@{}, @{ @"FAOTTestVersion": @"" }, @{ @"FAOTTestVersion": @"$(FAOT_TEST_VERSION)" }, @{ @"FAOTTestVersion": @"../escape" }]) {
  NSString *label=FAOTTestVersionFromInfo(info);
  if (label.length || [FAOTTestVersionSubtitle(label) containsString:@"测试版本"] || ![FAOTTestVersionLogName(label,123) isEqualToString:@"run-123.log"]) return 1;
 }
 NSString *label=FAOTTestVersionFromInfo(@{ @"FAOTTestVersion": @"LAN-r5" });
 if (![FAOTTestVersionSubtitle(label) containsString:@"测试版本：LAN-r5"] || ![FAOTTestVersionLogName(label,123) isEqualToString:@"run-123-LAN-r5.log"]) return 2;
} return 0; }''')
            subprocess.run(['clang','-fobjc-arc','-framework','Foundation','-I',str(root/'ios/C0Harness'),str(source),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)
