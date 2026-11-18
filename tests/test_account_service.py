from __future__ import annotations
import copy
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import account_service as auth


class MemoryStore:
    def __init__(self): self.values = {}
    def get(self, key): return copy.deepcopy(self.values.get(key))
    def put(self, key, value): self.values[key] = copy.deepcopy(value)


class AccountsTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.now = 1000
        self.accounts = auth.Accounts(self.store, 'publisher-id', now=lambda: self.now)
        self.profile = dict(id='a' * 32, name='NCLPlayer')

    def valid_responses(self, names=('game_minecraft', 'product_minecraft'), profile=None):
        return [dict(Token='xbox-secret', DisplayClaims={'xui': [{'uhs': 'hash'}]}),
                dict(Token='xsts-secret', DisplayClaims={'xui': [{'uhs': 'hash'}]}),
                dict(access_token='game-secret', expires_in=86400),
                dict(items=[dict(name=name) for name in names]), profile or self.profile]

    def verify(self, **kwargs):
        return self.accounts.verify(dict(access_token='microsoft-secret', refresh_token='refresh-secret'), **kwargs)

    def test_empty_or_local_boolean_does_not_grant_access(self):
        self.assertFalse(self.accounts.status()['verified'])
        with self.assertRaises(auth.AccountError): self.accounts.require()

    def test_only_official_entitlements_and_valid_profile_grant_access(self):
        with patch.object(auth, 'checked', side_effect=self.valid_responses()) as checked:
            public = self.verify()
        self.assertTrue(public['verified'])
        self.assertEqual(public['profile'], self.profile)
        self.assertEqual(public['verifiedUntil'], 4600)
        self.assertNotIn('secret', json.dumps(public))
        self.assertNotIn('token', json.dumps(public).lower())
        self.assertIn('/entitlements/license?requestId=', checked.call_args_list[3].args[0])
        self.assertEqual(checked.call_args_list[3].kwargs['bearer'], 'game-secret')
        self.assertEqual(self.store.get('active')['refreshToken'], 'refresh-secret')

    def test_unowned_or_bedrock_only_account_is_rejected_without_replacing_active(self):
        self.store.put('active', {'profile': self.profile})
        for names in ((), ('game_minecraft_bedrock',), ('random',)):
            with patch.object(auth, 'checked', side_effect=self.valid_responses(names=names)):
                with self.assertRaisesRegex(auth.AccountError, '正版资格'): self.verify()
            self.assertEqual(self.store.get('active'), {'profile': self.profile})

    def test_mismatched_xbox_identity_or_invalid_java_profile_is_rejected(self):
        data = self.valid_responses()
        data[1]['DisplayClaims']['xui'][0]['uhs'] = 'different'
        with patch.object(auth, 'checked', side_effect=data):
            with self.assertRaisesRegex(auth.AccountError, '不一致'): self.verify()
        for profile in (dict(id='invalid', name='Player'), dict(id='a' * 32, name='bad name')):
            with patch.object(auth, 'checked', side_effect=self.valid_responses(profile=profile)):
                with self.assertRaisesRegex(auth.AccountError, '档案无效'): self.verify()
        self.assertIsNone(self.store.get('active'))

    def test_expired_or_different_publisher_session_cannot_be_used(self):
        with patch.object(auth, 'checked', side_effect=self.valid_responses()): self.verify()
        self.now = 4600
        self.assertFalse(self.accounts.status()['verified'])
        self.now = 1000
        self.accounts.ident = 'changed-publisher'
        self.assertFalse(self.accounts.status()['verified'])

    def test_device_code_stays_in_keychain_and_polling_obeys_interval_and_slowdown(self):
        response = dict(device_code='private-device-code', user_code='ABCD1234', expires_in=900, interval=5)
        with patch.object(auth, 'checked', return_value=response): public = self.accounts.begin()
        self.assertNotIn('private-device-code', json.dumps(public))
        with patch.object(auth, 'request') as request:
            self.assertTrue(self.accounts.poll()['pending']); request.assert_not_called()
        self.now += 5
        with patch.object(auth, 'request', return_value=(400, {'error': 'slow_down'})):
            self.assertEqual(self.accounts.poll()['interval'], 10)
        self.assertEqual(self.store.get('pending')['nextPoll'], self.now + 10)

    def test_cancel_or_expiry_keeps_old_account(self):
        self.store.put('active', {'profile': self.profile})
        self.store.put('pending', dict(clientId='publisher-id', expiresAt=1001, nextPoll=1000, interval=5))
        self.accounts.cancel()
        self.assertEqual(self.store.get('active')['profile'], self.profile)
        with self.assertRaisesRegex(auth.AccountError, '取消'): self.accounts.poll()
        self.store.put('pending', dict(clientId='publisher-id', expiresAt=999))
        with self.assertRaisesRegex(auth.AccountError, '过期'): self.accounts.poll()

    def test_switch_requires_explicit_commit_and_can_be_cancelled_after_network_completion(self):
        old = dict(profile=dict(id='b' * 32, name='OldPlayer'))
        self.store.put('active', old)
        pending = dict(clientId='publisher-id', deviceCode='private-device', expiresAt=2000, nextPoll=0, interval=5)
        self.store.put('pending', pending)
        with patch.object(auth, 'request', return_value=(200, dict(access_token='msa-secret', refresh_token='refresh-secret'))), patch.object(auth, 'checked', side_effect=self.valid_responses()):
            self.assertEqual(self.accounts.poll(), {'ready': True})
        self.assertEqual(self.store.get('active'), old)
        self.accounts.cancel()
        with self.assertRaises(auth.AccountError): self.accounts.commit()
        self.assertEqual(self.store.get('active'), old)

    def test_verified_candidate_commits_and_no_secret_crosses_ipc(self):
        candidate = dict(clientId='publisher-id', refreshToken='secret', profile=self.profile, verifiedUntil=2000, verifiedAt=1000)
        self.store.put('pending', dict(clientId='publisher-id', candidate=candidate, expiresAt=1500))
        public = self.accounts.commit()
        self.assertTrue(public['verified'])
        self.assertNotIn('secret', json.dumps(public))
        self.assertIsNone(self.store.get('pending'))

    def test_refresh_revocation_or_network_failure_invalidates_cached_permission(self):
        self.store.put('active', dict(clientId='publisher-id', refreshToken='old', profile=self.profile, verifiedUntil=3000))
        with patch.object(auth, 'checked', side_effect=auth.AccountError('network unavailable')):
            with self.assertRaises(auth.AccountError): self.accounts.refresh(force=True)
        self.assertFalse(self.accounts.status()['verified'])
        self.assertEqual(self.store.get('active')['refreshToken'], 'old')

    def test_refresh_rotation_is_retained_if_subsequent_service_fails(self):
        self.store.put('active', dict(clientId='publisher-id', refreshToken='old', profile=self.profile, verifiedUntil=0))
        with patch.object(auth, 'checked', side_effect=[dict(access_token='access', refresh_token='rotated'), auth.AccountError('Xbox unavailable')]):
            with self.assertRaises(auth.AccountError): self.accounts.require()
        self.assertFalse(self.accounts.status()['verified'])
        self.assertEqual(self.store.get('active')['refreshToken'], 'rotated')

    def test_missing_configuration_defers_verification_without_claiming_ownership(self):
        for operation in ('status', 'begin', 'require'):
            with patch.object(sys, 'argv', ['account_service.py', operation]), patch.object(auth, 'client_id', return_value=''), patch.object(auth, 'Keychain') as keychain, patch.object(sys, 'stdout', new_callable=io.StringIO) as out:
                result = auth.main()
                self.assertEqual(result, 1 if operation == 'begin' else 0)
                self.assertFalse(json.loads(out.getvalue()).get('verified', False))
                keychain.assert_not_called()

    def test_unexpected_provider_errors_never_print_response_or_credentials(self):
        with patch.object(sys, 'argv', ['account_service.py', 'begin']), patch.object(auth, 'client_id', return_value='id'), patch.object(auth, 'Keychain', return_value=self.store), patch.object(auth, 'checked', side_effect=RuntimeError('private-secret-response')), patch.object(sys, 'stdout', new_callable=io.StringIO) as out:
            self.assertEqual(auth.main(), 1)
            self.assertNotIn('private-secret', out.getvalue())

    def test_non_official_origins_and_redirects_are_denied(self):
        for url in ('http://api.minecraftservices.com/test', 'https://evil.example/test', 'https://api.minecraftservices.com:444/test'):
            with self.assertRaises(auth.AccountError): auth.request(url)
        self.assertIsNone(auth.NoRedirect().redirect_request(None, None, None, None, None, None))

    def test_publisher_configuration_rejects_invalid_id(self):
        with patch.dict(os.environ, {'NCL_MICROSOFT_CLIENT_ID': 'arbitrary-id'}):
            with self.assertRaises(auth.AccountError): auth.client_id()


if __name__ == '__main__': unittest.main()
