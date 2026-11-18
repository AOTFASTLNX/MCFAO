"""Desktop Microsoft/Minecraft ownership verification. Secrets stay in macOS Keychain.

IPC only returns display identity, verification time and the short user login code.
Never pass tokens in process arguments, print service responses or persist them in builds.
"""
from __future__ import annotations

import argparse
import ctypes as c
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
AUTH = 'https://login.microsoftonline.com/consumers/oauth2/v2.0/'
SCOPE = 'XboxLive.signin offline_access'
SERVICE = b'org.fabricaot.desktop.microsoft'
VERIFY_URL = 'https://www.microsoft.com/link'


class AccountError(ValueError):
    pass


class Keychain:
    """Use Security.framework directly: no credential-bearing subprocess arguments."""
    def __init__(self):
        if sys.platform != 'darwin':
            raise AccountError('账号登录需要 macOS 桌面应用。')
        self.lib = c.CDLL('/System/Library/Frameworks/Security.framework/Security')
        self.cf = c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.lib.SecKeychainFindGenericPassword.argtypes = [c.c_void_p, c.c_uint32, c.c_char_p,
            c.c_uint32, c.c_char_p, c.POINTER(c.c_uint32), c.POINTER(c.c_void_p), c.POINTER(c.c_void_p)]
        self.lib.SecKeychainAddGenericPassword.argtypes = [c.c_void_p, c.c_uint32, c.c_char_p,
            c.c_uint32, c.c_char_p, c.c_uint32, c.c_void_p, c.c_void_p]
        self.lib.SecKeychainItemModifyAttributesAndData.argtypes = [c.c_void_p, c.c_void_p, c.c_uint32, c.c_void_p]
        self.lib.SecKeychainItemDelete.argtypes = [c.c_void_p]
        self.lib.SecKeychainItemFreeContent.argtypes = [c.c_void_p, c.c_void_p]
        self.cf.CFRelease.argtypes = [c.c_void_p]

    def _find(self, name):
        key = name.encode()
        length, data, item = c.c_uint32(), c.c_void_p(), c.c_void_p()
        status = self.lib.SecKeychainFindGenericPassword(None, len(SERVICE), SERVICE,
            len(key), key, c.byref(length), c.byref(data), c.byref(item))
        if status == -25300:
            return None, None
        if status != 0:
            raise AccountError('无法访问登录钥匙串，请解锁钥匙串并允许应用访问后重试。')
        try:
            value = json.loads(c.string_at(data, length.value))
        except (ValueError, TypeError):
            self.cf.CFRelease(item)
            raise AccountError('钥匙串中的登录状态无法读取，请检查或移除此应用的损坏登录记录后重试。') from None
        finally:
            self.lib.SecKeychainItemFreeContent(None, data)
        return value, item

    def get(self, name):
        value, item = self._find(name)
        if item:
            self.cf.CFRelease(item)
        return value

    def put(self, name, value):
        _, item = self._find(name)
        try:
            if value is None:
                status = self.lib.SecKeychainItemDelete(item) if item else 0
            else:
                data = json.dumps(value, separators=(',', ':')).encode()
                if item:
                    status = self.lib.SecKeychainItemModifyAttributesAndData(item, None, len(data), data)
                else:
                    key = name.encode()
                    status = self.lib.SecKeychainAddGenericPassword(None, len(SERVICE), SERVICE,
                        len(key), key, len(data), data, None)
            if status != 0:
                raise AccountError('无法安全保存登录状态，请检查钥匙串权限后重试。')
        finally:
            if item:
                self.cf.CFRelease(item)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


ALLOWED_HOSTS = {'login.microsoftonline.com', 'user.auth.xboxlive.com',
                 'xsts.auth.xboxlive.com', 'api.minecraftservices.com'}


def request(url, data=None, bearer=None, form=False):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.port not in (None, 443):
        raise AccountError('登录服务地址无效。')
    headers = {'Accept': 'application/json', 'User-Agent': 'NCL-Builder'}
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    body = None
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        body = (urllib.parse.urlencode(data) if form else json.dumps(data)).encode()
    req = urllib.request.Request(url, data=body, headers=headers)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    except (OSError, urllib.error.URLError):
        raise AccountError('无法连接 Microsoft / Minecraft 登录服务，请检查网络后重试。') from None
    try:
        with response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise AccountError('登录服务响应过大，请稍后重试。')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError()
            return response.code, result
    except (OSError, ValueError):
        raise AccountError('登录服务响应无效，请稍后重试。') from None


def checked(url, **kwargs):
    step = kwargs.pop('step', '')
    status, data = request(url, **kwargs)
    if status != 200:
        xerr = data.get('XErr')
        if xerr == 2148916233:
            raise AccountError('此 Microsoft 账号尚未建立 Xbox 档案，请先在 Xbox 官网完成设置。')
        if xerr in (2148916236, 2148916237, 2148916238, 2148916229):
            raise AccountError('此账号需要先在 Microsoft / Xbox 完成年龄或家庭权限设置。')
        if status in (401, 403):
            if step == 'xbox':
                raise AccountError('Xbox Live 拒绝了本应用的登录请求（HTTP %d）。'
                                   '这通常表示该 Client ID 未获 Xbox / Minecraft 服务准入。' % status)
            if step == 'minecraft':
                raise AccountError('Minecraft 服务拒绝了本应用的登录请求（HTTP %d）。'
                                   '这通常表示该 Client ID 尚未通过 Minecraft AppID 审核。' % status)
            raise AccountError('登录授权被拒绝或已过期，请重新登录；若持续失败，请检查应用的 Minecraft / Xbox API 授权。')
        if status == 404 and url.endswith('/minecraft/profile'):
            raise AccountError('此账号尚无 Minecraft Java 版档案，请先在 Minecraft 官网完成设置。')
        raise AccountError(f'登录服务暂不可用（HTTP {status}），请稍后重试。')
    return data


def client_id():
    # The publisher's PUBLIC app ID is configuration, never another launcher's ID.
    config = ROOT / 'compiler/microsoft-auth.json'
    value = os.environ.get('NCL_MICROSOFT_CLIENT_ID', '')
    if not value and config.is_file():
        value = json.loads(config.read_text()).get('clientId', '')
    if not value:
        return ''
    if not re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}', value):
        raise AccountError('Microsoft 登录服务配置无效，请联系应用维护者。')
    return value


class Accounts:
    def __init__(self, store, ident, now=time.time):
        self.store, self.ident, self.now = store, ident, now

    def status(self):
        session = self.store.get('active')
        profile = session.get('profile') if session else None
        verified = bool(profile and session.get('clientId') == self.ident and
                        self.now() < session.get('verifiedUntil', 0))
        return dict(configured=bool(self.ident), profile=profile, verified=verified,
                    verifiedAt=session.get('verifiedAt') if session else None,
                    verifiedUntil=session.get('verifiedUntil') if verified else None)

    def begin(self):
        if not self.ident:
            raise AccountError('登录服务待配置，请联系应用维护者。')
        data = checked(AUTH + 'devicecode', data={'client_id': self.ident, 'scope': SCOPE}, form=True)
        pending = dict(clientId=self.ident, deviceCode=data['device_code'], userCode=data['user_code'],
                       expiresAt=self.now() + min(int(data['expires_in']), 1800),
                       interval=max(5, int(data.get('interval', 5))))
        pending['nextPoll'] = self.now() + pending['interval']
        self.store.put('pending', pending)
        return dict(userCode=pending['userCode'], verificationUrl=VERIFY_URL,
                    expiresAt=pending['expiresAt'], interval=pending['interval'])

    def verify(self, microsoft, old_refresh='', persist=True):
        user = checked('https://user.auth.xboxlive.com/user/authenticate', step='xbox', data={
            'Properties': {'AuthMethod': 'RPS', 'SiteName': 'user.auth.xboxlive.com',
                           'RpsTicket': 'd=' + microsoft['access_token']},
            'RelyingParty': 'http://auth.xboxlive.com', 'TokenType': 'JWT'})
        xsts = checked('https://xsts.auth.xboxlive.com/xsts/authorize', step='xbox', data={
            'Properties': {'SandboxId': 'RETAIL', 'UserTokens': [user['Token']]},
            'RelyingParty': 'rp://api.minecraftservices.com/', 'TokenType': 'JWT'})
        uhs = user['DisplayClaims']['xui'][0]['uhs']
        if not uhs or uhs != xsts['DisplayClaims']['xui'][0]['uhs']:
            raise AccountError('账号身份校验不一致，请重新登录。')
        game = checked('https://api.minecraftservices.com/authentication/login_with_xbox', step='minecraft', data={
            'identityToken': 'XBL3.0 x=' + uhs + ';' + xsts['Token']})
        token = game['access_token']
        entitlements = checked('https://api.minecraftservices.com/entitlements/license?requestId=' + str(uuid.uuid4()), bearer=token)
        names = {item.get('name') for item in entitlements.get('items', []) if isinstance(item, dict)}
        if not {'game_minecraft', 'product_minecraft'} & names:
            raise AccountError('未验证到 Minecraft Java Edition 正版资格。请使用拥有 Java 版的账号登录。')
        profile = checked('https://api.minecraftservices.com/minecraft/profile', bearer=token)
        if not re.fullmatch(r'[a-fA-F0-9]{32}', profile.get('id', '')) or not re.fullmatch(r'[A-Za-z0-9_]{1,16}', profile.get('name', '')):
            raise AccountError('Minecraft Java 版档案无效，请先在官网完成档案设置。')
        refresh = microsoft.get('refresh_token') or old_refresh
        if not refresh:
            raise AccountError('未取得持久登录授权，请重新登录。')
        now = self.now()
        session = dict(clientId=self.ident, refreshToken=refresh,
                       profile={key: profile[key] for key in ('id', 'name')},
                       verifiedAt=now, verifiedUntil=now + max(0, min(3600, int(game['expires_in']) - 60)))
        if persist:
            self.store.put('active', session)
            return self.status()
        return session

    def poll(self):
        pending = self.store.get('pending')
        if not pending or pending.get('clientId') != self.ident or self.now() >= pending['expiresAt']:
            self.cancel()
            raise AccountError('登录已取消或验证码已过期，请重新登录。')
        if pending.get('candidate'):
            return dict(ready=True)
        if self.now() < pending['nextPoll']:
            return dict(pending=True, interval=pending['interval'])
        pending['nextPoll'] = self.now() + pending['interval']
        self.store.put('pending', pending)
        status, data = request(AUTH + 'token', data={
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
            'client_id': self.ident, 'device_code': pending['deviceCode']}, form=True)
        error = data.get('error')
        if error in ('authorization_pending', 'slow_down'):
            if error == 'slow_down':
                pending['interval'] += 5
                pending['nextPoll'] = self.now() + pending['interval']
                self.store.put('pending', pending)
            return dict(pending=True, interval=pending['interval'])
        if status != 200:
            self.cancel()
            raise AccountError('登录未获授权或验证码已失效，请重新登录。')
        try:
            candidate = self.verify(data, persist=False)
        except Exception:
            self.cancel()
            raise
        # A separate commit lets a cancellation during the in-flight HTTP calls
        # discard the candidate without replacing the user's current account.
        pending['candidate'] = candidate
        self.store.put('pending', pending)
        return dict(ready=True)

    def commit(self):
        pending = self.store.get('pending')
        if (not pending or pending.get('clientId') != self.ident or
                self.now() >= pending['expiresAt'] or not pending.get('candidate') or
                self.now() >= pending['candidate']['verifiedUntil']):
            raise AccountError('登录状态已失效，请重新登录。')
        self.store.put('active', pending['candidate'])
        self.store.put('pending', None)
        return self.status()

    def cancel(self):
        self.store.put('pending', None)
        return self.status()

    def refresh(self, force=False):
        session = self.store.get('active')
        if not session or session.get('clientId') != self.ident:
            return self.status()
        if not force and self.status()['verified']:
            return self.status()
        # Invalidate the cached permission before a network recheck. Network / revoked
        # ownership failures preserve the identity and refresh token, never permission.
        session['verifiedUntil'] = 0
        self.store.put('active', session)
        data = checked(AUTH + 'token', data={'client_id': self.ident, 'scope': SCOPE,
            'grant_type': 'refresh_token', 'refresh_token': session['refreshToken']}, form=True)
        # Persist rotation immediately, even if a subsequent Xbox request fails.
        session['refreshToken'] = data.get('refresh_token') or session['refreshToken']
        self.store.put('active', session)
        return self.verify(data, session['refreshToken'])

    def require(self):
        result = self.refresh()
        if not result['verified']:
            raise AccountError('请先登录并验证 Minecraft Java Edition 正版资格。')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'begin', 'poll', 'commit', 'cancel', 'refresh', 'require'))
    args = parser.parse_args()
    try:
        ident = client_id()
        if not ident:
            if args.action in ('status', 'refresh', 'cancel', 'require'):
                print(json.dumps(dict(configured=False, profile=None, verified=False, verificationDeferred=True)))
                return 0
            raise AccountError('登录服务待配置，请联系应用维护者。')
        accounts = Accounts(Keychain(), ident)
        result = accounts.refresh(force=True) if args.action == 'refresh' else getattr(accounts, args.action)()
        print(json.dumps(result, ensure_ascii=False))
    except AccountError as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1
    except Exception:
        # Provider bodies, exceptions and tokens must never reach IPC or stderr.
        print(json.dumps({'error': '登录状态处理失败，请重新登录或稍后重试。'}, ensure_ascii=False))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
